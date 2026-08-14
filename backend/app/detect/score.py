from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import exp

from app.providers.base import ContractSnapshot
from app.universe import ZERO_DTE_UNDERLYINGS

DEFAULT_WEIGHTS: dict[str, float] = {
    "voi": 0.32,
    "vol": 0.22,
    "prem": 0.22,
    "iv": 0.08,
    "accel": 0.10,
    "persist": 0.12,
    "sector": 0.06,
}

DEFAULT_PENALTIES: dict[str, float] = {
    "dte0": 0.35,
    "earnings": 0.20,
    "twosided": 0.25,
    "roll": 0.30,
    "lottery": 0.25,
    "wide_spread": 0.15,
}


@dataclass
class Baseline:
    avg_volume_20d: float | None = None
    p50_premium: float | None = None
    p90_premium: float | None = None
    p99_premium: float | None = None
    avg_iv: float | None = None
    und_p90_premium: float | None = None
    und_p99_premium: float | None = None
    sessions_count: int = 0


@dataclass
class UnderlyingFlow:
    call_premium: float = 0.0
    put_premium: float = 0.0
    call_volume: int = 0
    put_volume: int = 0
    sector_peers_unusual: int = 0
    spot_change_pct: float | None = None
    earnings_days: int | None = None

    @property
    def total_premium(self) -> float:
        return self.call_premium + self.put_premium

    @property
    def call_share(self) -> float:
        tot = self.total_premium
        if tot <= 0:
            return 0.5
        return self.call_premium / tot


@dataclass
class PriorSession:
    session_date: date
    volume: int = 0
    open_interest: int = 0
    unusual: bool = False


@dataclass
class ScoreResult:
    score: float
    direction: str
    tags: list[str] = field(default_factory=list)
    reasons: list[dict] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    vol_oi: float | None = None
    est_premium: float | None = None
    iv_delta: float | None = None


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _sat(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """Smooth 0-1 saturation around a midpoint."""
    return _clip(1.0 / (1.0 + exp(-steepness * (value - midpoint))))


def moneyness(snap: ContractSnapshot) -> float | None:
    if not snap.spot or snap.spot <= 0:
        return None
    if snap.call_put == "C":
        return (snap.strike - snap.spot) / snap.spot
    return (snap.spot - snap.strike) / snap.spot


def dte(snap: ContractSnapshot, asof: date | None = None) -> int | None:
    if not snap.expiry:
        return None
    asof = asof or (snap.asof.date() if snap.asof else date.today())
    return (snap.expiry - asof).days


def score_contract(
    snap: ContractSnapshot,
    baseline: Baseline,
    flow: UnderlyingFlow,
    prior: list[PriorSession] | None = None,
    yesterday_volume: int | None = None,
    weights: dict[str, float] | None = None,
    penalties: dict[str, float] | None = None,
    asof: date | None = None,
) -> ScoreResult:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    penalties = {**DEFAULT_PENALTIES, **(penalties or {})}
    prior = prior or []
    tags: list[str] = []
    reasons: list[dict] = []
    components: dict[str, float] = {}

    vol = snap.volume or 0
    oi = snap.open_interest or 0
    vol_oi = (vol / oi) if oi > 0 else (float(vol) if vol else None)
    premium = snap.est_premium
    days = dte(snap, asof)
    mny = moneyness(snap)
    spread = snap.spread_pct
    iv_delta = None
    if snap.iv is not None and baseline.avg_iv:
        iv_delta = snap.iv - baseline.avg_iv

    # --- subscores ---
    voi_score = 0.0
    if vol_oi is not None:
        voi_score = _clip((vol_oi - 0.5) / 5.5)
        if vol_oi >= 2:
            tags.append("vol_gt_oi")
        if vol_oi >= 5:
            tags.append("vol_oi_extreme")
            reasons.append({"code": "voi", "text": f"vol/OI {vol_oi:.1f} (prior OI {oi:,})"})
    components["voi"] = voi_score

    vol_score = 0.0
    if baseline.avg_volume_20d and baseline.avg_volume_20d > 0:
        ratio = vol / baseline.avg_volume_20d
        vol_score = _clip((ratio - 1.0) / 6.0)
        if ratio >= 5:
            tags.append("vol_vs_avg")
            reasons.append({"code": "vol", "text": f"volume {ratio:.1f}× 20-day average"})
        elif ratio >= 3:
            reasons.append({"code": "vol", "text": f"volume {ratio:.1f}× 20-day average"})
    elif vol >= 2000:
        vol_score = _clip(vol / 15000.0)
    components["vol"] = vol_score

    prem_score = 0.0
    if premium is not None:
        ref99 = baseline.p99_premium or baseline.und_p99_premium
        ref90 = baseline.p90_premium or baseline.und_p90_premium
        if ref99 and ref99 > 0:
            prem_score = _clip(premium / ref99)
        elif ref90 and ref90 > 0:
            prem_score = _clip(premium / (ref90 * 1.5))
        else:
            # no history: soft log-ish scale, $25k = 0.25, $1M = ~0.85
            prem_score = _clip((premium / 25000.0) / (1.0 + premium / 1_000_000.0) * 0.35 + _sat(premium / 250_000.0, 1.0, 1.2))
        if premium >= 250_000:
            tags.append("size")
            reasons.append({"code": "prem", "text": f"est. premium ${premium:,.0f}"})
    components["prem"] = prem_score

    iv_score = 0.0
    if iv_delta is not None and iv_delta > 0:
        iv_score = _clip(iv_delta / 0.15)
        if iv_delta >= 0.05:
            tags.append("iv_shock")
            reasons.append({"code": "iv", "text": f"IV {iv_delta*100:+.1f} pts vs baseline"})
    components["iv"] = iv_score

    accel_score = 0.0
    if yesterday_volume and yesterday_volume > 0 and vol > yesterday_volume:
        accel_score = _clip((vol / yesterday_volume - 1.0) / 2.0)
        if vol > yesterday_volume:
            tags.append("accelerating")
            reasons.append({"code": "accel", "text": f"today's volume already {vol/yesterday_volume:.1f}× yesterday"})
    components["accel"] = accel_score

    persist_score = 0.0
    unusual_days = sum(1 for p in prior if p.unusual)
    oi_rising = False
    if len(prior) >= 2 and prior[0].open_interest and prior[-1].open_interest:
        oi_rising = prior[-1].open_interest > prior[0].open_interest
    if unusual_days >= 2 and oi_rising:
        persist_score = _clip(0.45 + 0.2 * unusual_days)
        tags.append("multi_day")
        reasons.append({"code": "persist", "text": f"{unusual_days} sessions unusual with rising OI"})
    elif unusual_days >= 2:
        persist_score = 0.35
        tags.append("repeat")
    components["persist"] = persist_score

    sector_score = 0.0
    if flow.sector_peers_unusual >= 2:
        sector_score = _clip(0.35 * flow.sector_peers_unusual)
        tags.append("sector")
        reasons.append({"code": "sector", "text": f"{flow.sector_peers_unusual} sector peers also unusual"})
    components["sector"] = sector_score

    raw = sum(weights[k] * components.get(k, 0.0) for k in weights)

    # --- penalties / tags ---
    penalty = 0.0
    is_0dte = days is not None and days <= 0 and snap.underlying.upper() in ZERO_DTE_UNDERLYINGS
    if days is not None and days <= 0:
        tags.append("0dte")
        if is_0dte or (premium or 0) < 1_000_000:
            penalty += penalties["dte0"]

    one_sided = False
    if flow.total_premium > 0:
        share = flow.call_share
        if share >= 0.72 or share <= 0.28:
            one_sided = True
            tags.append("one_sided")
        elif 0.40 <= share <= 0.60:
            tags.append("two_sided")
            penalty += penalties["twosided"]
            reasons.append({"code": "twosided", "text": "call and put premium both heavy — likely a vol trade"})

    if flow.earnings_days is not None and 0 <= flow.earnings_days <= 5:
        tags.append("earnings")
        if not one_sided:
            penalty += penalties["earnings"]
            reasons.append({"code": "earnings", "text": f"earnings in {flow.earnings_days}d and flow is two-sided"})

    # lottery: far OTM, short dated, small premium
    mid_px = snap.mid or 0.0
    if mny is not None and mny > 0.12 and (days or 99) <= 10 and mid_px < 0.50:
        tags.append("lottery")
        penalty += penalties["lottery"]
        reasons.append({"code": "lottery", "text": "far OTM short-dated cheap premium — usually retail"})

    if spread is not None and spread > 0.25:
        tags.append("wide_spread")
        penalty += penalties["wide_spread"]

    # roll: caller sets tag via flow hint stored on snapshot? we accept a tag in prior
    # Detect roll if this contract's volume is high while a nearer expiry same strike
    # is provided via flow. We keep a simple hook: if 'roll' already in tags from caller.
    # Directional / hedge fingerprints
    if snap.call_put == "P" and (flow.spot_change_pct or 0) > 0.4 and (vol_oi or 0) >= 1.5:
        tags.append("possible_hedge")
        reasons.append({"code": "hedge", "text": "put volume on a rising stock — often a hedge, not a short"})

    if snap.call_put == "C" and (flow.spot_change_pct or 0) < -0.4 and (vol_oi or 0) >= 2:
        tags.append("divergence")
        reasons.append({"code": "div", "text": "call buying while the stock is down"})

    if days is not None and 7 <= days <= 45 and mny is not None and abs(mny) < 0.08:
        tags.append("concentrated")

    if vol_oi is not None and vol_oi >= 2:
        tags.append("likely_opening")

    score = 100.0 * _clip(raw - penalty)

    # Direction
    if "two_sided" in tags:
        direction = "vol"
    elif snap.call_put == "C":
        direction = "bullish"
    else:
        direction = "bearish"
    if "possible_hedge" in tags:
        direction = "hedge"

    if score >= 70 and "size" not in tags and premium:
        reasons.append({"code": "score", "text": f"composite unusual score {score:.0f}"})

    return ScoreResult(
        score=round(score, 1),
        direction=direction,
        tags=sorted(set(tags)),
        reasons=reasons,
        components={k: round(v, 3) for k, v in components.items()},
        vol_oi=round(vol_oi, 2) if vol_oi is not None else None,
        est_premium=premium,
        iv_delta=round(iv_delta, 4) if iv_delta is not None else None,
    )


def detect_rolls(snaps: list[ContractSnapshot]) -> set[str]:
    """Same strike, two expiries, both printing size — likely a roll."""
    by_key: dict[tuple[str, float, str], list[ContractSnapshot]] = {}
    for s in snaps:
        if not s.volume or s.volume < 400:
            continue
        by_key.setdefault((s.underlying, s.strike, s.call_put), []).append(s)
    rolled: set[str] = set()
    for group in by_key.values():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda x: x.expiry)
        near, far = group[0], group[-1]
        if near.expiry != far.expiry:
            rolled.add(near.occ_symbol)
            rolled.add(far.occ_symbol)
    return rolled
