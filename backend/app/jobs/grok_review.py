from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SYSTEM = """You are Grok reviewing a personal unusual-options paper-trading bot.
The user is not a professional trader. Write in plain English.
Use ONLY the JSON data. Do not invent fills, news, or win rates.
Be honest when the sample is too small or the results are from a replay fixture.
Return a JSON object with keys:
headline (string),
summary (string, 2-4 sentences),
findings (array of strings),
changes (array of concrete strategy changes, each starting with a verb),
risks (array of strings).
"""


def pack_dataset(report: dict, extra_signals: list[dict] | None = None) -> dict:
    trades = report.get("trades") or []
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample": {
            "trades": report.get("overall", {}).get("n", 0),
            "open": report.get("open_count"),
            "closed": report.get("closed_count"),
            "win_rate": report.get("overall", {}).get("win_rate"),
            "total_pnl": report.get("overall", {}).get("total_pnl"),
            "expectancy": report.get("overall", {}).get("expectancy"),
        },
        "by_kind": report.get("by_kind"),
        "by_side": report.get("by_side"),
        "by_score": report.get("by_score"),
        "by_tag": report.get("by_tag"),
        "rule_lessons": report.get("lessons"),
        "trades": trades,
        "alert_outcomes": extra_signals or report.get("alert_outcomes") or [],
    }


def write_local_review(data: dict) -> dict:
    sample = data.get("sample") or {}
    n = int(sample.get("trades") or 0)
    wr = sample.get("win_rate")
    pnl = sample.get("total_pnl") or 0
    exp = sample.get("expectancy") or 0
    kinds = data.get("by_kind") or {}
    sides = data.get("by_side") or {}
    outcomes = data.get("alert_outcomes") or []
    trades = data.get("trades") or []

    good = [o for o in outcomes if o.get("quality") == "good_signal"]
    poor = [o for o in outcomes if o.get("quality") == "poor_signal"]
    not_trade = [o for o in outcomes if o.get("quality") == "not_a_trade"]
    followed = [o for o in outcomes if o.get("verdict") == "followed"]
    faded = [o for o in outcomes if o.get("verdict") == "faded_price"]

    findings: list[str] = []
    changes: list[str] = []
    risks: list[str] = []

    if n == 0:
        return {
            "source": "local",
            "headline": "No paper trades for Grok to review yet",
            "summary": (
                "The auto-trader has not booked any paper fills. Leave it on for a few live or replay cycles, "
                "then run this review again."
            ),
            "findings": [],
            "changes": ["Keep auto-trading on and come back after at least 15–20 fills."],
            "risks": ["Any advice before that is storytelling, not statistics."],
        }

    findings.append(
        f"The book has {n} paper trade(s): {sample.get('closed') or 0} locked, {sample.get('open') or 0} still open. "
        f"Combined P&L is ${pnl:.0f} (average ${exp:.0f} per trade). Win rate is {wr}%."
    )
    if n < 15:
        findings.append(
            f"That is a tiny sample. A 100% win rate on {n} trades — especially from the replay tape — does not mean "
            "the strategy works in a live market."
        )
        risks.append("Do not raise size or loosen filters because replay looked clean.")

    opt = kinds.get("option") or {}
    stk = kinds.get("stock") or {}
    if opt.get("n") and stk.get("n"):
        findings.append(
            f"Options made ${opt.get('total_pnl', 0):.0f} across {opt.get('n')} fills "
            f"(${opt.get('expectancy', 0):.0f} each). Stock made ${stk.get('total_pnl', 0):.0f} "
            f"across {stk.get('n')} fills (${stk.get('expectancy', 0):.0f} each)."
        )
        if (opt.get("expectancy") or 0) > (stk.get("expectancy") or 0) + 10:
            changes.append(
                "Keep buying the unusual option itself. Using leftover cash for one share of stock is fine for learning, "
                "but it is not where the edge (if any) showed up."
            )
        elif (stk.get("expectancy") or 0) > (opt.get("expectancy") or 0) + 10:
            changes.append(
                "Treat the option print as the signal and prefer the stock as the vehicle. Options decay; leftover-share "
                "P&L was better here."
            )

    if not sides.get("put"):
        findings.append(
            "Every fill so far is on the call/long side. The bot has not yet stress-tested unusual puts. "
            "You do not know if the hedge filter is saving you or blocking real shorts."
        )
        changes.append(
            "Do not loosen the put/hedge skip list until you have a dozen put outcomes on the alert journal, "
            "even if those were skipped rather than traded."
        )
    elif (sides.get("put") or {}).get("total_pnl", 0) < 0:
        changes.append("Keep skipping likely hedges. Put trades lost money.")

    if good or poor:
        findings.append(
            f"On the alert journal (not just fills): {len(followed)} alerts were followed by a stock move in the "
            f"expected direction, {len(faded)} went the wrong way, {len(not_trade)} were marked not a directional bet."
        )
    if poor:
        names = ", ".join(sorted({p.get("symbol") or "?" for p in poor})[:6])
        findings.append(
            f"These names moved against the options bet: {names}. Copying every high score would have hurt on those."
        )
        changes.append(
            "After a 'poor_signal' on a name, require a second unusual day (multi-day tag) before auto-buying that name again."
        )
    if good:
        names = ", ".join(sorted({g.get("symbol") or "?" for g in good})[:6])
        findings.append(f"Flow lined up with the stock on: {names}. Those are the pattern to keep.")
        if any("multi_day" in (t.get("tags") or []) for t in trades if t.get("pnl", 0) > 0):
            changes.append("Bias auto-buys toward the multi-day tag when cash is tight — spend the $1,000 on repeats, not one-print spikes.")

    closed = [t for t in trades if t.get("status") != "open"]
    tps = [t for t in closed if t.get("close_reason") and "take-profit" in str(t.get("close_reason"))]
    if tps:
        findings.append(
            f"{len(tps)} locked winner(s) came from the automatic take-profit. The exit rules are doing real work — "
            "do not switch back to holding until expiry."
        )

    if outcomes:
        mixed = [o for o in outcomes if o.get("quality") == "mixed"]
        if mixed:
            findings.append(
                f"{len(mixed)} alert(s) followed the stock but also had news or messy open-interest. "
                "Those are weaker than a quiet, one-sided, multi-day build."
            )
            changes.append("Prefer alerts with no earnings in 5 days and a confirmed OI rise. Downgrade news-day flow.")

    if not changes:
        changes.append("Keep the current skip list (hedge, 0-day, roll, lottery, two-sided) and the 80+ score gate.")
        changes.append("Let the book reach 20+ locked trades before changing take-profit or stop numbers.")

    risks.extend(
        [
            "Replay later-prices are scripted. Live Yahoo is delayed and can miss the real move.",
            "Paper fills have no slippage, no bid/ask hit, and no assignment risk.",
            "A $1,000 book can only hold one option at a time — results are path-dependent.",
        ]
    )

    headline = (
        f"Small sample, ${pnl:.0f} paper P&L — treat this as a lab notebook, not a proven edge"
        if n < 15
        else f"Book P&L ${pnl:.0f} on {n} trades — here is what to change"
    )
    summary = (
        f"Grok read all {n} paper fill(s) and {len(outcomes)} scored alert(s). "
        f"Locked-plus-open P&L is ${pnl:.0f} with a {wr}% win rate. "
        "The useful lesson is not the win rate — it is which tags and sides produced follow-through, "
        "and which alerts would have been bad buys if the bot had taken them."
    )

    return {
        "source": "local",
        "headline": headline,
        "summary": summary,
        "findings": findings,
        "changes": changes,
        "risks": risks,
    }


def _call_xai(data: dict) -> dict | None:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        return None
    try:
        resp = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("XAI_MODEL", "grok-4.5"),
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": "Review this paper-trading book and unusual-options journal:\n"
                        + json.dumps(data, default=str)[:24000],
                    },
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
        else:
            parsed = {"headline": "Grok review", "summary": text, "findings": [], "changes": [], "risks": []}
        parsed["source"] = os.environ.get("XAI_MODEL", "grok-4.5")
        return parsed
    except Exception as exc:
        log.warning("xAI Grok review failed: %s", exc)
        return None


def build_alert_outcomes(session: Session) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT underlying, call_put, direction, score, status, actionable,
                   outcome_verdict, outcome_quality, outcome_return_pct, outcome_plain, tags
            FROM signals
            WHERE outcome_verdict IS NOT NULL
            ORDER BY score DESC
            """
        )
    ).mappings().all()
    out = []
    for r in rows:
        out.append(
            {
                "symbol": r["underlying"],
                "side": r["call_put"],
                "direction": r["direction"],
                "score": r["score"],
                "occ": r["status"],
                "actionable": r["actionable"],
                "verdict": r["outcome_verdict"],
                "quality": r["outcome_quality"],
                "stock_return": r["outcome_return_pct"],
                "plain": r["outcome_plain"],
                "tags": list(r["tags"] or []),
            }
        )
    return out


def run_grok_review(session: Session, report: dict) -> dict:
    outcomes = build_alert_outcomes(session)
    report = {**report, "alert_outcomes": outcomes}
    data = pack_dataset(report, outcomes)
    local = write_local_review(data)
    remote = _call_xai(data)
    review = remote or local
    if remote is None:
        review["source"] = "local"
        review["note"] = (
            "No XAI_API_KEY in the API container. This review is Grok's local pass over your book. "
            "Add XAI_API_KEY to .env and restart to use grok-4.5."
        )
    review["sample"] = data["sample"]
    return save_review(session, review)


def build_premium_prompt(data: dict) -> str:
    """Prompt to paste into grok.x.com / X Grok (Premium). No API key required."""
    blob = json.dumps(data, default=str, indent=2)
    if len(blob) > 20000:
        blob = blob[:20000] + "\n…(truncated)"
    return f"""You are reviewing my personal unusual-options paper-trading bot. I am not a professional trader.

Rules:
- Use ONLY the JSON below. Do not invent fills, news, or win rates.
- Be honest if the sample is tiny or this is replay/fixture data.
- Write in plain English.

Please cover:
1. A one-line headline.
2. A short summary (2–4 sentences).
3. What the book actually shows (findings).
4. Concrete strategy changes (start each with a verb).
5. Ways I could fool myself.

If you can, end with a JSON object:
{{"headline":"...","summary":"...","findings":["..."],"changes":["..."],"risks":["..."]}}

DATA:
{blob}
"""


def save_review(session: Session, review: dict) -> dict:
    review = {**review, "generated_at": datetime.now(timezone.utc).isoformat()}
    session.execute(
        text(
            """
            INSERT INTO settings (key, value) VALUES ('paper_grok_review', CAST(:v AS jsonb))
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {"v": json.dumps(review, default=str)},
    )
    session.commit()
    return review


def import_pasted_review(session: Session, raw: str) -> dict:
    text_in = (raw or "").strip()
    parsed: dict | None = None
    start, end = text_in.find("{"), text_in.rfind("}")
    if start >= 0 and end > start:
        try:
            maybe = json.loads(text_in[start : end + 1])
            if isinstance(maybe, dict) and (maybe.get("summary") or maybe.get("headline") or maybe.get("findings")):
                parsed = maybe
        except json.JSONDecodeError:
            parsed = None
    if parsed:
        review = {
            "source": "x-premium",
            "headline": parsed.get("headline") or "Grok review (from X Premium)",
            "summary": parsed.get("summary") or "",
            "findings": parsed.get("findings") or [],
            "changes": parsed.get("changes") or [],
            "risks": parsed.get("risks") or [],
            "note": "Imported from a Grok reply you pasted (X Premium / grok.x.com).",
        }
    else:
        review = {
            "source": "x-premium",
            "headline": "Grok review (from X Premium)",
            "summary": text_in,
            "findings": [],
            "changes": [],
            "risks": [],
            "note": "Imported as free text from grok.x.com. Next time, ask Grok to include the JSON block at the end.",
        }
    return save_review(session, review)


def load_grok_review(session: Session) -> dict | None:
    row = session.execute(text("SELECT value FROM settings WHERE key = 'paper_grok_review'")).scalar()
    if not row:
        return None
    if isinstance(row, str):
        return json.loads(row)
    return dict(row)
