from __future__ import annotations

from dataclasses import dataclass, field


FOLLOW_PCT = 0.015  # 1.5% stock move counts as a real move


@dataclass
class Outcome:
    verdict: str  # pending | followed | faded_price | little_move | not_directional
    quality: str  # too_soon | good_signal | poor_signal | not_a_trade | mixed
    return_pct: float | None
    later_spot: float | None
    plain: str
    news: list[dict] = field(default_factory=list)


def expected_direction(direction: str | None, call_put: str | None) -> int:
    """+1 stock should rise, -1 should fall, 0 = not a directional bet."""
    if direction in ("hedge", "vol"):
        return 0
    if direction == "bearish" or call_put == "P":
        return -1
    if direction == "bullish" or call_put == "C":
        return 1
    return 0


def judge_outcome(
    *,
    direction: str | None,
    call_put: str | None,
    entry_spot: float | None,
    later_spot: float | None,
    occ_status: str | None = None,
    actionable: bool = True,
    news: list[dict] | None = None,
    earnings_days: int | None = None,
) -> Outcome:
    news = news or []
    exp = expected_direction(direction, call_put)
    want = "up" if exp > 0 else "down" if exp < 0 else "neither way"

    if not actionable or exp == 0:
        extra = ""
        if news:
            extra = " There was news, which often explains insurance or volatility buying."
        if occ_status == "hedge":
            extra = " Official open interest looks like a hedge."
        return Outcome(
            verdict="not_directional",
            quality="not_a_trade",
            return_pct=None if not entry_spot or not later_spot else (later_spot - entry_spot) / entry_spot,
            later_spot=later_spot,
            plain=(
                "This was not a clean buy-or-sell signal. It looks like a hedge, a two-sided volatility trade, "
                "or noise — copying it as a directional bet would be reading it backwards."
                + extra
            ),
            news=news,
        )

    if entry_spot is None or later_spot is None or entry_spot <= 0:
        return Outcome(
            verdict="pending",
            quality="too_soon",
            return_pct=None,
            later_spot=later_spot,
            plain=(
                "Too soon to judge. We need a later stock price (next scan in live mode, or the replay “what happened next” print) "
                "to see if the market agreed with this flow."
            ),
            news=news,
        )

    ret = (later_spot - entry_spot) / entry_spot
    signed = ret * exp
    news_bit = ""
    if news:
        titles = "; ".join(n.get("title") or n.get("headline") or "" for n in news[:2])
        news_bit = f" Nearby headline(s): {titles}."
    elif earnings_days is not None and 0 <= earnings_days <= 5:
        news_bit = f" Earnings are about {earnings_days} day(s) away — that alone can cause unusual options volume."

    if signed >= FOLLOW_PCT:
        quality = "good_signal"
        if news or (earnings_days is not None and 0 <= earnings_days <= 5):
            quality = "mixed"
        occ = ""
        if occ_status == "confirmed":
            occ = " Official open interest also rose, so someone stayed in."
        elif occ_status == "faded":
            occ = " But official open interest did not rise — the stock moved, yet the options may have been day-traded."
            quality = "mixed"
        return Outcome(
            verdict="followed",
            quality=quality,
            return_pct=ret,
            later_spot=later_spot,
            plain=(
                f"The stock moved {want} ({ret:+.1%}). That matches the options bet, so this would have been a useful "
                f"directional hint."
                + occ
                + news_bit
            ),
            news=news,
        )

    if signed <= -FOLLOW_PCT:
        return Outcome(
            verdict="faded_price",
            quality="poor_signal",
            return_pct=ret,
            later_spot=later_spot,
            plain=(
                f"The stock went the other way ({ret:+.1%}). The unusual flow did not predict this move — "
                f"a bad signal this time."
                + news_bit
            ),
            news=news,
        )

    return Outcome(
        verdict="little_move",
        quality="mixed",
        return_pct=ret,
        later_spot=later_spot,
        plain=(
            f"The stock barely moved ({ret:+.1%}). The options were unusual, but the market did not follow through "
            f"(yet). Unusual flow is often early — or just noise."
            + news_bit
        ),
        news=news,
    )
