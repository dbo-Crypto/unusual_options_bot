from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.detect.score import ScoreResult, dte, moneyness
from app.providers.base import ContractSnapshot


COMPANY_FALLBACK = {
    "NVDA": "NVIDIA",
    "AMD": "Advanced Micro Devices",
    "AVGO": "Broadcom",
    "SMH": "the VanEck Semiconductor ETF",
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "SPY": "the S&P 500 ETF (SPY)",
    "MSFT": "Microsoft",
    "SMR": "NuScale Power",
    "PLTR": "Palantir",
    "QQQ": "the Nasdaq-100 ETF (QQQ)",
    "IWM": "the Russell 2000 ETF (IWM)",
    "META": "Meta",
    "AMZN": "Amazon",
    "GOOGL": "Alphabet",
    "TSM": "Taiwan Semiconductor",
}


def company_label(symbol: str, name: str | None = None) -> str:
    if name:
        short = name.replace("Corporation", "").replace("Inc.", "").replace("Inc", "").strip(" ,")
        return f"{short} ({symbol})"
    fallback = COMPANY_FALLBACK.get(symbol.upper())
    if fallback:
        return f"{fallback} ({symbol})" if "(" not in fallback else fallback
    return symbol


def _money(n: float | None) -> str:
    if n is None:
        return "an unknown amount"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f} million"
    if n >= 1_000:
        return f"${n / 1_000:.0f} thousand"
    return f"${n:,.0f}"


def _expiry_words(expiry: date | None, asof: date | None) -> str:
    if not expiry:
        return "this option"
    label = expiry.strftime("%B %-d") if hasattr(expiry, "strftime") else str(expiry)
    # %-d is POSIX; fall back if needed
    try:
        label = expiry.strftime("%B ") + str(expiry.day)
    except Exception:
        label = str(expiry)
    days = (expiry - asof).days if asof else None
    if days is None:
        return f"the {label} option"
    if days <= 0:
        return f"the option that expires today ({label})"
    if days == 1:
        return f"the option that expires tomorrow ({label})"
    return f"the option that expires {label} (in {days} days)"


def _bet_sentence(snap: ContractSnapshot, tags: list[str]) -> str:
    strike = f"${snap.strike:g}"
    if snap.call_put == "C":
        if "possible_hedge" in tags:
            return f"these are call options at {strike} — a bet the stock goes up"
        return (
            f"traders piled into the {strike} call. A call is a ticket that pays if the stock "
            f"rises above {strike} before it expires"
        )
    if "possible_hedge" in tags:
        return (
            f"these are put options at {strike}. A put pays if the stock falls, but on a rising stock "
            f"this is often just insurance — like buying home insurance, not betting the house burns down"
        )
    return (
        f"traders piled into the {strike} put. A put is a ticket that pays if the stock "
        f"falls below {strike} before it expires"
    )


@dataclass
class Explanation:
    company_name: str
    headline: str
    plain_english: str
    actionable: bool
    suggested_action: str
    caution: str | None


def explain_signal(
    snap: ContractSnapshot,
    result: ScoreResult,
    company_name: str | None = None,
    asof: date | None = None,
) -> Explanation:
    tags = result.tags
    asof = asof or (snap.asof.date() if snap.asof else None)
    who = company_label(snap.underlying, company_name)
    expiry = _expiry_words(snap.expiry, asof)
    days = dte(snap, asof)
    mny = moneyness(snap)

    parts: list[str] = []
    parts.append(f"{who} just showed unusual options activity on {expiry}.")
    bet = _bet_sentence(snap, tags)
    parts.append(bet[0].upper() + bet[1:] + ".")

    if result.vol_oi and result.vol_oi >= 2 and snap.open_interest:
        parts.append(
            f"Today's trading volume is about {result.vol_oi:.1f}× the number of contracts that were already open "
            f"({(snap.volume or 0):,} traded vs {snap.open_interest:,} previously open). "
            f"When volume dwarfs open interest, it usually means someone is opening a new position, "
            f"not just closing an old one."
        )
    elif snap.volume:
        parts.append(f"About {snap.volume:,} contracts traded today, which is a lot for this specific strike.")

    if result.est_premium and result.est_premium >= 50_000:
        parts.append(
            f"The estimated money spent on this one contract is {_money(result.est_premium)}. "
            f"That is a lot of cash to put on a single expiration and strike — retail traders rarely do that alone."
        )

    if "multi_day" in tags:
        parts.append(
            "This same contract has been lighting up for several days and official open interest has been rising. "
            "That is stronger than a one-day spike: someone came back and added."
        )
    if "sector" in tags:
        parts.append(
            "Other companies in the same industry are showing the same kind of activity. "
            "A whole sector lighting up is harder to dismiss as one fund's random trade."
        )
    if "divergence" in tags:
        parts.append(
            "The stock itself is down or flat while people buy calls. That can mean someone is buying the dip "
            "instead of chasing a rally."
        )
    if "accelerating" in tags:
        parts.append("Volume is already ahead of yesterday's full-day total — the activity is speeding up, not fading.")
    if "iv_shock" in tags:
        parts.append(
            "The option got more expensive (implied volatility jumped). Buyers were willing to pay up, "
            "not just pick off a cheap leftover quote."
        )

    caution = None
    actionable = True
    suggested = "watch"

    if "two_sided" in tags:
        actionable = False
        caution = (
            "Calls and puts are both busy. That often means someone is betting on a big move in either direction "
            "(a volatility trade), not that they know which way the stock goes."
        )
        suggested = "skip"
    elif "possible_hedge" in tags or result.direction == "hedge":
        actionable = False
        caution = (
            "This looks like insurance, not a bet the stock will crash. Copying it as a short would be reading it backwards."
        )
        suggested = "skip"
    elif "roll" in tags:
        actionable = False
        caution = (
            "This looks like a roll — moving an existing position to a later date. "
            "That is maintenance, not a brand-new idea."
        )
        suggested = "skip"
    elif "lottery" in tags:
        actionable = False
        caution = (
            "This is a cheap, far-out-of-the-money, short-dated option. Those are lottery tickets. "
            "They are usually retail speculation and expire worthless."
        )
        suggested = "skip"
    elif "0dte" in tags and (days or 0) <= 0:
        actionable = False
        caution = (
            "This expires today. Most of that volume is day-trading and market-maker hedging, not a secret about next week."
        )
        suggested = "skip"
    elif "earnings" in tags and "two_sided" in tags:
        actionable = False
        caution = "Earnings are close. Options always get busy then. Treat this as noise unless the flow is clearly one-sided."
        suggested = "skip"
    elif snap.call_put == "C" and result.direction == "bullish":
        suggested = "consider_long"
        if mny is not None and mny > 0.08:
            parts.append(
                f"The strike is above today's stock price (${snap.spot:g} now, bet needs ${snap.strike:g}). "
                f"The stock has to rally for this call to finish in the money."
            )
        else:
            parts.append(
                f"The strike is close to the current stock price (${snap.spot:g}). "
                f"That is a more precise, less lottery-like bet than a far-away strike."
            )
    elif snap.call_put == "P" and result.direction == "bearish":
        suggested = "consider_short"
        parts.append(
            f"Someone is paying for downside below ${snap.strike:g} while the stock is around ${snap.spot:g}."
        )

    if "earnings" in tags and caution is None:
        parts.append(
            "Earnings are nearby, so some of this could just be people hedging a known event. "
            "The next official open-interest update will tell us if positions stayed open."
        )

    parts.append(
        "This is not a crystal ball. Big options trades are often hedges, and even clean signals fail often. "
        "The next morning's official open-interest file is the fact-check: if open interest rose, someone actually stayed in."
    )
    if caution:
        parts.append(caution)

    headline = f"{who}: unusual {'call' if snap.call_put == 'C' else 'put'} activity"
    if result.score >= 80:
        headline += " (high conviction)"
    elif not actionable:
        headline += " (probably not a directional bet)"

    return Explanation(
        company_name=who,
        headline=headline,
        plain_english=" ".join(parts),
        actionable=actionable,
        suggested_action=suggested,
        caution=caution,
    )
