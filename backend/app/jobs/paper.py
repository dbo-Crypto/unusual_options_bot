from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from math import floor

from sqlalchemy import text
from sqlalchemy.orm import Session

STARTING_CASH = 1000.0
MAX_FRACTION = 0.45  # leave room for a second trade on a $1k account


def seed_account(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_account (id, cash, starting_cash, updated_at)
            SELECT 1, :cash, :cash, NOW()
            WHERE NOT EXISTS (SELECT 1 FROM paper_account)
            """
        ),
        {"cash": STARTING_CASH},
    )
    session.commit()


def get_account(session: Session) -> dict:
    seed_account(session)
    acc = session.execute(text("SELECT * FROM paper_account WHERE id = 1")).mappings().first()
    positions = session.execute(
        text("SELECT * FROM paper_positions ORDER BY opened_at DESC")
    ).mappings().all()
    open_pos = [p for p in positions if p["status"] == "open"]
    closed = [p for p in positions if p["status"] != "open"]
    unreal = sum(_unrealized(p) for p in open_pos)
    realized = sum(float(p["realized_pnl"] or 0) for p in closed)
    equity = float(acc["cash"]) + sum(_mark_value(p) for p in open_pos)
    winners = sum(1 for p in closed if (p["realized_pnl"] or 0) > 0)
    losers = sum(1 for p in closed if (p["realized_pnl"] or 0) < 0)
    return {
        "cash": float(acc["cash"]),
        "starting_cash": float(acc["starting_cash"]),
        "equity": round(equity, 2),
        "unrealized_pnl": round(unreal, 2),
        "realized_pnl": round(realized, 2),
        "total_pnl": round(equity - float(acc["starting_cash"]), 2),
        "open_count": len(open_pos),
        "winners": winners,
        "losers": losers,
        "flat": sum(1 for p in closed if (p["realized_pnl"] or 0) == 0),
        "worker_state": acc.get("worker_state") or "running",
        "killed": bool(acc.get("killed")),
        "last_error": acc.get("last_error"),
        "positions": [dict(p) for p in positions],
    }


def _multiplier(kind: str) -> int:
    return 100 if kind == "option" else 1


def _mark_value(p) -> float:
    mark = p["mark_price"] if p["mark_price"] is not None else p["entry_price"]
    return float(p["qty"]) * float(mark) * _multiplier(p["kind"])


def _unrealized(p) -> float:
    return _mark_value(p) - float(p["qty"]) * float(p["entry_price"]) * _multiplier(p["kind"])


def quote_order(session: Session, signal_id: str, kind: str) -> dict:
    sig = session.execute(
        text("SELECT * FROM signals WHERE id = CAST(:id AS uuid)"), {"id": signal_id}
    ).mappings().first()
    if not sig:
        return {"ok": False, "error": "Alert not found"}
    acc = session.execute(text("SELECT cash FROM paper_account WHERE id = 1")).first()
    cash = float(acc[0]) if acc else STARTING_CASH
    und = session.execute(
        text("SELECT name, last_spot FROM underlyings WHERE symbol = :s"), {"s": sig["underlying"]}
    ).mappings().first()
    # Entry uses the price at the alert, not the later mark.
    spot = sig.get("spot") or (und["last_spot"] if und else None)
    last = sig.get("last_price")
    if last is None:
        snap = session.execute(
            text("SELECT last_price, bid, ask FROM snapshots WHERE occ_symbol = :o ORDER BY time DESC LIMIT 1"),
            {"o": sig["occ_symbol"]},
        ).mappings().first()
        if snap:
            last = snap["last_price"]
            if last is None and snap["bid"] and snap["ask"]:
                last = (snap["bid"] + snap["ask"]) / 2
    if kind == "stock":
        if not spot or spot <= 0:
            return {"ok": False, "error": "No stock price available"}
        unit = float(spot)
        mult = 1
        budget = cash * MAX_FRACTION
        qty = max(1, floor(budget / unit)) if unit <= budget else (1 if unit <= cash else 0)
    else:
        if not last or last <= 0:
            return {"ok": False, "error": "No option price available"}
        unit = float(last)
        mult = 100
        cost1 = unit * 100
        qty = 1 if cost1 <= cash else 0
    cost = qty * unit * mult
    warning = None
    tags = set(sig.get("tags") or [])
    if sig.get("actionable") is False or tags & {"possible_hedge", "two_sided", "roll", "lottery", "0dte"}:
        warning = sig.get("plain_english") or "This alert is probably not a clean directional bet."
    if kind == "option" and cost > cash * 0.5 and qty:
        warning = (warning + " " if warning else "") + "One option contract uses most of the $1,000 account."
    if qty == 0:
        return {
            "ok": False,
            "error": f"Not enough cash (${cash:.2f}) to buy this {kind}.",
            "cash": cash,
            "unit_price": unit,
            "multiplier": mult,
            "cost": unit * mult,
        }
    return {
        "ok": True,
        "kind": kind,
        "symbol": sig["underlying"],
        "company_name": sig.get("company_name") or (und["name"] if und else None),
        "occ_symbol": sig["occ_symbol"] if kind == "option" else None,
        "qty": qty,
        "unit_price": unit,
        "multiplier": mult,
        "cost": round(cost, 2),
        "cash": cash,
        "cash_after": round(cash - cost, 2),
        "spot": spot,
        "warning": warning,
        "actionable": bool(sig.get("actionable", True)),
        "plain_english": sig.get("plain_english"),
        "expiry": sig["expiry"],
        "strike": sig["strike"],
        "call_put": sig["call_put"],
    }


def place_order(session: Session, signal_id: str, kind: str, qty: int | None = None, origin: str = "manual") -> dict:
    q = quote_order(session, signal_id, kind)
    if not q.get("ok"):
        return q
    qty = qty or int(q["qty"])
    if qty < 1:
        return {"ok": False, "error": "Quantity must be at least 1"}
    cost = qty * float(q["unit_price"]) * int(q["multiplier"])
    cash = float(q["cash"])
    if cost > cash + 1e-6:
        return {"ok": False, "error": f"Need ${cost:.2f}, only ${cash:.2f} cash"}
    sig = session.execute(
        text("SELECT score, tags FROM signals WHERE id = CAST(:id AS uuid)"), {"id": signal_id}
    ).mappings().first()
    pid = str(uuid.uuid4())
    session.execute(text("UPDATE paper_account SET cash = cash - :c, updated_at = NOW() WHERE id = 1"), {"c": cost})
    session.execute(
        text(
            """
            INSERT INTO paper_positions (
                id, signal_id, kind, symbol, company_name, occ_symbol, expiry, strike, call_put,
                qty, entry_price, entry_spot, mark_price, mark_spot, opened_at, status, thesis,
                origin, score, tags
            ) VALUES (
                CAST(:id AS uuid), CAST(:sid AS uuid), :kind, :sym, :name, :occ, :exp, :strike, :cp,
                :qty, :px, :spot, :px, :spot, NOW(), 'open', :thesis,
                :origin, :score, :tags
            )
            """
        ),
        {
            "id": pid,
            "sid": signal_id,
            "kind": kind,
            "sym": q["symbol"],
            "name": q.get("company_name"),
            "occ": q.get("occ_symbol"),
            "exp": q.get("expiry"),
            "strike": q.get("strike"),
            "cp": q.get("call_put"),
            "qty": qty,
            "px": q["unit_price"],
            "spot": q.get("spot"),
            "thesis": q.get("plain_english"),
            "origin": origin,
            "score": sig["score"] if sig else None,
            "tags": list(sig["tags"] or []) if sig else [],
        },
    )
    session.commit()
    mark_positions(session)
    return {"ok": True, "id": pid, "cost": cost, "qty": qty, "kind": kind, "origin": origin}


def close_position(session: Session, position_id: str, reason: str | None = None) -> dict:
    p = session.execute(
        text("SELECT * FROM paper_positions WHERE id = CAST(:id AS uuid)"), {"id": position_id}
    ).mappings().first()
    if not p or p["status"] != "open":
        return {"ok": False, "error": "No open position"}
    mark = p["mark_price"] if p["mark_price"] is not None else p["entry_price"]
    proceeds = float(p["qty"]) * float(mark) * _multiplier(p["kind"])
    cost = float(p["qty"]) * float(p["entry_price"]) * _multiplier(p["kind"])
    pnl = proceeds - cost
    session.execute(text("UPDATE paper_account SET cash = cash + :p, updated_at = NOW() WHERE id = 1"), {"p": proceeds})
    result = "winner" if pnl > 1 else ("loser" if pnl < -1 else "flat")
    session.execute(
        text(
            """
            UPDATE paper_positions
            SET status = 'closed', closed_at = NOW(), close_price = :px, realized_pnl = :pnl, result = :res,
                close_reason = :why
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": position_id, "px": mark, "pnl": pnl, "res": result, "why": reason or "closed"},
    )
    session.commit()
    return {"ok": True, "proceeds": proceeds, "pnl": round(pnl, 2), "result": result, "reason": reason}


def reset_account(session: Session, wipe_history: bool = False) -> dict:
    if wipe_history:
        session.execute(text("DELETE FROM paper_positions"))
        session.execute(text("DELETE FROM paper_auto_log"))
    else:
        session.execute(text("DELETE FROM paper_positions WHERE status = 'open'"))
    session.execute(
        text("UPDATE paper_account SET cash = starting_cash, updated_at = NOW() WHERE id = 1")
    )
    session.commit()
    return get_account(session)


def mark_positions(session: Session, asof: date | None = None) -> int:
    """Refresh marks from latest snapshots / spots. Expire options past expiry."""
    asof = asof or datetime.now(timezone.utc).date()
    rows = session.execute(text("SELECT * FROM paper_positions WHERE status = 'open'")).mappings().all()
    n = 0
    for p in rows:
        mark = None
        spot = None
        und = session.execute(
            text("SELECT last_spot FROM underlyings WHERE symbol = :s"), {"s": p["symbol"]}
        ).first()
        if und:
            spot = und[0]
        if p["kind"] == "stock":
            mark = spot
        else:
            snap = None
            if p["occ_symbol"]:
                snap = session.execute(
                    text(
                        """
                        SELECT last_price, bid, ask, spot FROM snapshots
                        WHERE occ_symbol = :o ORDER BY time DESC LIMIT 1
                        """
                    ),
                    {"o": p["occ_symbol"]},
                ).mappings().first()
            if snap:
                mark = snap["last_price"]
                if mark is None and snap["bid"] and snap["ask"]:
                    mark = (snap["bid"] + snap["ask"]) / 2
                spot = snap["spot"] or spot
            # expire
            if p["expiry"] and p["expiry"] < asof:
                intrinsic = 0.0
                if spot is not None and p["strike"] is not None:
                    if p["call_put"] == "C":
                        intrinsic = max(0.0, float(spot) - float(p["strike"]))
                    else:
                        intrinsic = max(0.0, float(p["strike"]) - float(spot))
                mark = intrinsic
                session.execute(
                    text("UPDATE paper_positions SET mark_price = :m, mark_spot = :s WHERE id = :id"),
                    {"m": mark, "s": spot, "id": p["id"]},
                )
                close_position(session, str(p["id"]))
                session.execute(
                    text("UPDATE paper_positions SET status = 'expired' WHERE id = CAST(:id AS uuid)"),
                    {"id": str(p["id"])},
                )
                session.commit()
                n += 1
                continue
        if mark is not None:
            session.execute(
                text("UPDATE paper_positions SET mark_price = :m, mark_spot = :s WHERE id = :id"),
                {"m": mark, "s": spot, "id": p["id"]},
            )
            n += 1
    session.commit()
    return n
