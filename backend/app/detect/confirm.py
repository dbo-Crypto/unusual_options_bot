from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfirmInput:
    call_put: str
    spot_change_pct: float | None
    oi_change: int | None
    prior_oi: int | None
    direction: str


def confirm_signal(inp: ConfirmInput) -> tuple[str, str]:
    """
    Return (status, note) using next-day official OI.
    status: confirmed | faded | hedge | live
    """
    if inp.oi_change is None:
        return "live", "No official OI update yet"

    rising = inp.oi_change > max(50, int((inp.prior_oi or 0) * 0.02))
    falling = inp.oi_change < -max(50, int((inp.prior_oi or 0) * 0.02))
    spot = inp.spot_change_pct or 0.0

    if inp.call_put == "P" and spot > 0.3 and rising:
        return "hedge", "Puts opened on a rising stock — treat as a hedge"
    if inp.call_put == "C" and rising:
        if spot > 0:
            return "confirmed", "New call OI with follow-through — strongest bullish confirmation"
        return "confirmed", "New call OI while the stock was down — dip accumulation"
    if inp.call_put == "P" and rising:
        return "confirmed", "New put OI with follow-through — strongest bearish confirmation"
    if falling:
        return "faded", "OI fell — yesterday's volume was covering or closing, not a new position"
    return "faded", "High volume, OI roughly unchanged — likely day-traded away"
