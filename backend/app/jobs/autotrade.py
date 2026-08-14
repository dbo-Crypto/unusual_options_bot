from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.jobs.paper import close_position, place_order, seed_account

log = logging.getLogger(__name__)

DEFAULT_AUTO = {
    "enabled": True,
    "min_score": 80,
    "option_take_profit": 0.30,  # +30% on the option premium
    "option_stop_loss": 0.40,  # -40%
    "stock_take_profit": 0.05,  # +5%
    "stock_stop_loss": 0.04,  # -4%
}

SKIP_TAGS = {"possible_hedge", "two_sided", "roll", "lottery", "0dte"}


def get_auto_settings(session: Session) -> dict:
    row = session.execute(text("SELECT value FROM settings WHERE key = 'paper_auto'")).scalar()
    if not row:
        return dict(DEFAULT_AUTO)
    if isinstance(row, str):
        row = json.loads(row)
    return {**DEFAULT_AUTO, **(row or {})}


def save_auto_settings(session: Session, value: dict) -> dict:
    merged = {**DEFAULT_AUTO, **value}
    session.execute(
        text(
            """
            INSERT INTO settings (key, value) VALUES ('paper_auto', CAST(:v AS jsonb))
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {"v": json.dumps(merged)},
    )
    session.commit()
    return merged


def _already_open(session: Session, symbol: str, kind: str, occ: str | None) -> bool:
    if kind == "option" and occ:
        row = session.execute(
            text(
                """
                SELECT 1 FROM paper_positions
                WHERE status = 'open' AND kind = 'option' AND occ_symbol = :occ
                LIMIT 1
                """
            ),
            {"occ": occ},
        ).first()
        return bool(row)
    row = session.execute(
        text(
            """
            SELECT 1 FROM paper_positions
            WHERE status = 'open' AND kind = :k AND symbol = :s
            LIMIT 1
            """
        ),
        {"k": kind, "s": symbol},
    ).first()
    return bool(row)


def _log(session: Session, signal_id: str | None, action: str, reason: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_auto_log (id, signal_id, action, reason, created_at)
            VALUES (CAST(:id AS uuid), CAST(:sid AS uuid), :action, :reason, NOW())
            """
        )
        if signal_id
        else text(
            """
            INSERT INTO paper_auto_log (id, signal_id, action, reason, created_at)
            VALUES (CAST(:id AS uuid), NULL, :action, :reason, NOW())
            """
        ),
        {"id": str(uuid.uuid4()), "sid": signal_id, "action": action, "reason": reason},
    )


def decide_exit(
    *,
    kind: str,
    call_put: str | None,
    entry: float,
    mark: float | None,
    entry_spot: float | None,
    mark_spot: float | None,
    signal_status: str | None,
    opposite_flow: bool,
    cfg: dict | None = None,
) -> str | None:
    """Return a close reason, or None to hold."""
    cfg = {**DEFAULT_AUTO, **(cfg or {})}
    if mark is None or not entry:
        return None
    if kind == "option":
        chg = (mark / entry) - 1.0
        if chg >= cfg["option_take_profit"]:
            return f"take-profit: option gained {chg:.0%} (target {cfg['option_take_profit']:.0%})"
        if chg <= -cfg["option_stop_loss"]:
            return f"stop-loss: option lost {abs(chg):.0%} (limit {cfg['option_stop_loss']:.0%})"
    else:
        if entry_spot and mark_spot:
            chg = (mark_spot / entry_spot) - 1.0
            if chg >= cfg["stock_take_profit"]:
                return f"take-profit: stock gained {chg:.0%} (target {cfg['stock_take_profit']:.0%})"
            if chg <= -cfg["stock_stop_loss"]:
                return f"stop-loss: stock lost {abs(chg):.0%} (limit {cfg['stock_stop_loss']:.0%})"
    if signal_status in ("faded", "hedge"):
        return f"thesis dead: official OCC tagged the alert {signal_status}"
    if opposite_flow:
        side = "puts" if call_put == "C" or kind == "stock" else "calls"
        return f"opposite flow: unusual {side} showed up against this position"
    return None


def auto_trade(session: Session) -> dict:
    """Buy calls and puts automatically; sell when rules fire. Fully hands-off."""
    seed_account(session)
    cfg = get_auto_settings(session)
    report: dict = {"enabled": cfg["enabled"], "bought": [], "sold": [], "skipped": []}
    if not cfg["enabled"]:
        report["skipped"].append({"reason": "Auto-trading is turned off"})
        return report

    rows = session.execute(
        text(
            """
            SELECT * FROM signals
            WHERE status = 'live' AND score >= :min
            ORDER BY score DESC, created_at DESC
            """
        ),
        {"min": cfg["min_score"]},
    ).mappings().all()

    bought_stock_already = False
    for sig in rows:
        tags = set(sig.get("tags") or [])
        sid = str(sig["id"])
        name = sig.get("company_name") or sig["underlying"]
        cp = sig.get("call_put")
        if sig.get("actionable") is False or tags & SKIP_TAGS:
            reason = "Skipped — hedge, roll, lottery, 0-day, or two-sided vol trade"
            report["skipped"].append({"signal_id": sid, "symbol": sig["underlying"], "reason": reason})
            _log(session, sid, "skipped", reason)
            continue
        if sig.get("suggested_action") == "skip":
            reason = "Skipped — detector said this is not a directional bet"
            report["skipped"].append({"signal_id": sid, "symbol": sig["underlying"], "reason": reason})
            _log(session, sid, "skipped", reason)
            continue

        # Bearish put flow: dump any long stock the bot bought on this name.
        if cp == "P" and sig.get("direction") in ("bearish",):
            for pos in session.execute(
                text("SELECT id FROM paper_positions WHERE status = 'open' AND kind = 'stock' AND symbol = :s"),
                {"s": sig["underlying"]},
            ).scalars().all():
                closed = close_position(session, str(pos), reason="auto-sell stock: unusual put flow against the long")
                if closed.get("ok"):
                    report["sold"].append({"id": str(pos), "symbol": sig["underlying"], "kind": "stock", "reason": closed.get("reason")})
                    _log(session, sid, "sold_stock", "Unusual put flow — sold the long stock")

        if not _already_open(session, sig["underlying"], "option", sig["occ_symbol"]):
            result = place_order(session, sid, "option", origin="auto")
            if result.get("ok"):
                report["bought"].append(
                    {
                        "signal_id": sid,
                        "symbol": sig["underlying"],
                        "company_name": name,
                        "kind": "option",
                        "side": "call" if cp == "C" else "put",
                        "qty": result["qty"],
                        "cost": result["cost"],
                        "score": sig["score"],
                    }
                )
                _log(
                    session,
                    sid,
                    "bought_call" if cp == "C" else "bought_put",
                    f"Auto-bought the unusual {'call' if cp == 'C' else 'put'} (score {sig['score']})",
                )
            else:
                report["skipped"].append(
                    {"signal_id": sid, "symbol": sig["underlying"], "reason": result.get("error") or "option order failed"}
                )
                _log(session, sid, "skipped", result.get("error") or "option order failed")

        # Follow a bullish call with leftover stock, once per cycle.
        if (
            not bought_stock_already
            and cp == "C"
            and sig.get("direction") == "bullish"
            and not _already_open(session, sig["underlying"], "stock", None)
        ):
            result = place_order(session, sid, "stock", origin="auto")
            if result.get("ok"):
                bought_stock_already = True
                report["bought"].append(
                    {
                        "signal_id": sid,
                        "symbol": sig["underlying"],
                        "company_name": name,
                        "kind": "stock",
                        "side": "long",
                        "qty": result["qty"],
                        "cost": result["cost"],
                        "score": sig["score"],
                    }
                )
                _log(session, sid, "bought_stock", f"Auto-bought shares with leftover cash (score {sig['score']})")

    session.commit()
    log.info("auto-trade bought %s skipped %s", len(report["bought"]), len(report["skipped"]))
    return report


def auto_close(session: Session, cfg: dict | None = None) -> list[dict]:
    cfg = {**DEFAULT_AUTO, **(cfg or {})}
    sold: list[dict] = []
    rows = session.execute(text("SELECT * FROM paper_positions WHERE status = 'open'")).mappings().all()
    for p in rows:
        sig = None
        if p.get("signal_id"):
            sig = session.execute(
                text("SELECT status, call_put, underlying FROM signals WHERE id = :id"),
                {"id": p["signal_id"]},
            ).mappings().first()
        opposite = False
        symbol = p["symbol"]
        if p["kind"] == "stock" or p.get("call_put") == "C":
            opposite = bool(
                session.execute(
                    text(
                        """
                        SELECT 1 FROM signals
                        WHERE underlying = :s AND status = 'live' AND call_put = 'P'
                          AND score >= :min AND COALESCE(actionable, TRUE) = TRUE
                          AND NOT (tags && CAST(:skip AS text[]))
                        LIMIT 1
                        """
                    ),
                    {"s": symbol, "min": cfg["min_score"], "skip": list(SKIP_TAGS)},
                ).first()
            )
        elif p.get("call_put") == "P":
            opposite = bool(
                session.execute(
                    text(
                        """
                        SELECT 1 FROM signals
                        WHERE underlying = :s AND status = 'live' AND call_put = 'C'
                          AND score >= :min AND COALESCE(actionable, TRUE) = TRUE
                          AND NOT (tags && CAST(:skip AS text[]))
                        LIMIT 1
                        """
                    ),
                    {"s": symbol, "min": cfg["min_score"], "skip": list(SKIP_TAGS)},
                ).first()
            )
        reason = decide_exit(
            kind=p["kind"],
            call_put=p.get("call_put"),
            entry=float(p["entry_price"] or 0),
            mark=p.get("mark_price"),
            entry_spot=p.get("entry_spot"),
            mark_spot=p.get("mark_spot"),
            signal_status=sig["status"] if sig else None,
            opposite_flow=opposite,
            cfg=cfg,
        )
        if not reason:
            continue
        closed = close_position(session, str(p["id"]), reason=reason)
        if closed.get("ok"):
            sold.append(
                {
                    "id": str(p["id"]),
                    "symbol": symbol,
                    "kind": p["kind"],
                    "reason": reason,
                    "pnl": closed.get("pnl"),
                    "result": closed.get("result"),
                }
            )
            _log(session, str(p["signal_id"]) if p.get("signal_id") else None, "sold", reason)
    return sold
