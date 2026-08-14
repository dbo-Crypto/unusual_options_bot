from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.jobs.paper import _multiplier


def _trade_pnl(p: dict) -> float:
    if p.get("status") != "open":
        return float(p.get("realized_pnl") or 0)
    mark = p.get("mark_price")
    if mark is None:
        mark = p.get("entry_price") or 0
    return float(p["qty"]) * (float(mark) - float(p["entry_price"])) * _multiplier(p["kind"])


def _bucket(trades: list[dict]) -> dict:
    pnls = [_trade_pnl(t) for t in trades]
    wins = [x for x in pnls if x > 1]
    losses = [x for x in pnls if x < -1]
    n = len(trades)
    win_rate = (len(wins) / n * 100) if n else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    total = sum(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss else (None if not wins else 99)
    expectancy = total / n if n else 0
    return {
        "n": n,
        "winners": len(wins),
        "losers": len(losses),
        "flat": n - len(wins) - len(losses),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "total_pnl": round(total, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
    }


def analyze_trades(session: Session) -> dict:
    rows = session.execute(
        text(
            """
            SELECT p.*, s.tags AS signal_tags, s.score AS signal_score, s.direction, s.suggested_action,
                   s.outcome_verdict, s.outcome_quality, s.outcome_return_pct
            FROM paper_positions p
            LEFT JOIN signals s ON s.id = p.signal_id
            ORDER BY p.opened_at DESC
            """
        )
    ).mappings().all()
    trades = []
    for r in rows:
        d = dict(r)
        tags = list(d.get("tags") or d.get("signal_tags") or [])
        d["tags"] = tags
        d["score"] = d.get("score") if d.get("score") is not None else d.get("signal_score")
        d["pnl"] = _trade_pnl(d)
        trades.append(d)

    by_kind: dict[str, list] = defaultdict(list)
    by_side: dict[str, list] = defaultdict(list)
    by_origin: dict[str, list] = defaultdict(list)
    by_tag: dict[str, list] = defaultdict(list)
    by_score: dict[str, list] = defaultdict(list)
    for t in trades:
        by_kind[t["kind"]].append(t)
        side = "call" if t.get("call_put") == "C" else ("put" if t.get("call_put") == "P" else t["kind"])
        by_side[side].append(t)
        by_origin[t.get("origin") or "manual"].append(t)
        for tag in t.get("tags") or []:
            by_tag[tag].append(t)
        sc = t.get("score") or 0
        if sc >= 90:
            by_score["90+"].append(t)
        elif sc >= 80:
            by_score["80–89"].append(t)
        else:
            by_score["under 80"].append(t)

    overall = _bucket(trades)
    kind_b = {k: _bucket(v) for k, v in sorted(by_kind.items())}
    side_b = {k: _bucket(v) for k, v in sorted(by_side.items())}
    origin_b = {k: _bucket(v) for k, v in sorted(by_origin.items())}
    score_b = {k: _bucket(v) for k, v in sorted(by_score.items())}
    tag_b = {
        k: _bucket(v)
        for k, v in sorted(by_tag.items(), key=lambda kv: -abs(_bucket(kv[1])["total_pnl"]))
        if _bucket(v)["n"] >= 1
    }
    lessons = _lessons(overall, kind_b, side_b, tag_b, score_b, origin_b, trades)
    from app.jobs.grok_review import load_grok_review

    return {
        "overall": overall,
        "open_count": sum(1 for t in trades if t["status"] == "open"),
        "closed_count": sum(1 for t in trades if t["status"] != "open"),
        "by_kind": kind_b,
        "by_side": side_b,
        "by_origin": origin_b,
        "by_score": score_b,
        "by_tag": tag_b,
        "lessons": lessons,
        "trades": [
            {
                "id": str(t["id"]),
                "symbol": t["symbol"],
                "company_name": t.get("company_name"),
                "kind": t["kind"],
                "origin": t.get("origin") or "manual",
                "score": t.get("score"),
                "tags": t.get("tags") or [],
                "pnl": round(t["pnl"], 2),
                "status": t["status"],
                "result": t.get("result")
                or ("winner" if t["pnl"] > 1 else "loser" if t["pnl"] < -1 else "flat"),
                "close_reason": t.get("close_reason"),
                "outcome_quality": t.get("outcome_quality"),
                "outcome_verdict": t.get("outcome_verdict"),
            }
            for t in trades
        ],
        "grok": load_grok_review(session),
    }


def _lessons(overall, by_kind, by_side, by_tag, by_score, by_origin, trades) -> list[str]:
    out: list[str] = []
    n = overall["n"]
    if n == 0:
        return [
            "No paper trades yet. Leave auto-trading on and wait for the next scan, or reset the account and click “Run auto-trader now”."
        ]
    if n < 8:
        out.append(
            f"You only have {n} paper trade{'s' if n != 1 else ''}. Treat every conclusion as a hint, not a proof. "
            "A real read needs a few dozen trades."
        )
    if overall["win_rate"] < 40 and n >= 4:
        out.append(
            f"Win rate is {overall['win_rate']:.0f}%. The detector is finding unusual activity, but copying it is losing more often than it wins. "
            "Tighten the gate: only auto-trade score 85+ and require the multi-day tag."
        )
    elif overall["win_rate"] >= 55 and n >= 4:
        out.append(
            f"Win rate is {overall['win_rate']:.0f}%. The current filters are at least not random. Keep skipping hedges, 0-day options, and two-sided earnings flow."
        )
    if overall["expectancy"] < 0 and n >= 3:
        out.append(
            f"Average trade is ${overall['expectancy']:.0f}. Even when you win, losers may be larger. Cut option losers faster (for example if the option loses 50% of its premium)."
        )
    opt = by_kind.get("option")
    stk = by_kind.get("stock")
    if opt and stk and opt["n"] and stk["n"]:
        if stk["expectancy"] > opt["expectancy"] + 5:
            out.append(
                "Following the stock made more money than buying the unusual option. Options decay. "
                "Consider auto-buying the stock and only using the option as the *signal*, not the vehicle."
            )
        elif opt["expectancy"] > stk["expectancy"] + 5:
            out.append(
                "The unusual option itself made more than the stock. That is the point of following flow — keep buying the contract that lit up, not a random share count."
            )
    puts = by_side.get("put")
    if puts and puts["n"] >= 2 and puts["total_pnl"] < 0:
        out.append(
            "Put trades are losing money. Many puts are insurance, not a bet the stock will fall. Keep the hedge filter strict."
        )
    multi = by_tag.get("multi_day")
    one = [t for t in trades if "multi_day" not in (t.get("tags") or [])]
    if multi and multi["n"] >= 2 and one:
        one_b = _bucket(one)
        if multi["expectancy"] > one_b["expectancy"] + 5:
            out.append(
                "Trades that repeated for several days beat one-day spikes. Prefer auto-trading only when the “multi-day” tag is present."
            )
    hi = by_score.get("90+")
    lo = by_score.get("under 80")
    if hi and lo and hi["n"] and lo["n"] and hi["expectancy"] > lo["expectancy"] + 5:
        out.append("Scores of 90+ did better than weaker alerts. Raise the auto-trade minimum score.")
    elif lo and lo["n"] >= 2 and lo["total_pnl"] < 0:
        out.append("Alerts under score 80 are dragging results down. Do not auto-trade those.")
    if not out:
        out.append(
            "No strong pattern yet. Keep auto-trading the high-score, one-sided, non-hedge names and come back after more closes."
        )
    return out
