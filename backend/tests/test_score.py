from datetime import date, datetime, timezone

from app.detect.score import Baseline, UnderlyingFlow, detect_rolls, score_contract
from app.providers.base import ContractSnapshot


def _snap(**kwargs) -> ContractSnapshot:
    base = dict(
        occ_symbol="NVDA260904C190",
        underlying="NVDA",
        expiry=date(2026, 9, 4),
        strike=190,
        call_put="C",
        volume=18400,
        open_interest=2100,
        last_price=6.35,
        bid=6.2,
        ask=6.45,
        iv=0.48,
        spot=178.4,
        asof=datetime(2026, 8, 14, 19, 45, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return ContractSnapshot(**base)


def test_high_vol_oi_scores_high():
    result = score_contract(
        _snap(),
        Baseline(avg_volume_20d=900, und_p90_premium=200_000, und_p99_premium=800_000, avg_iv=0.39),
        UnderlyingFlow(call_premium=2_000_000, put_premium=80_000, spot_change_pct=-1.1),
        asof=date(2026, 8, 14),
    )
    assert result.score >= 80
    assert result.direction == "bullish"
    assert "vol_gt_oi" in result.tags
    assert result.vol_oi and result.vol_oi >= 5


def test_twosided_0dte_does_not_alert():
    spy_c = _snap(
        occ_symbol="SPY260814C563",
        underlying="SPY",
        expiry=date(2026, 8, 14),
        strike=563,
        call_put="C",
        volume=180000,
        open_interest=24000,
        last_price=0.42,
        bid=0.41,
        ask=0.43,
        iv=0.18,
        spot=562.3,
    )
    result = score_contract(
        spy_c,
        Baseline(avg_volume_20d=50000),
        UnderlyingFlow(call_premium=7_500_000, put_premium=6_200_000, spot_change_pct=0.1),
        asof=date(2026, 8, 14),
    )
    assert "0dte" in result.tags
    assert "two_sided" in result.tags
    assert result.score < 80
    assert result.direction == "vol"


def test_lottery_penalized():
    result = score_contract(
        _snap(
            occ_symbol="SMR260821C20",
            underlying="SMR",
            expiry=date(2026, 8, 21),
            strike=20,
            call_put="C",
            volume=8900,
            open_interest=400,
            last_price=0.18,
            bid=0.12,
            ask=0.25,
            iv=1.4,
            spot=14.2,
        ),
        Baseline(),
        UnderlyingFlow(call_premium=16000, put_premium=0, spot_change_pct=2.1),
        asof=date(2026, 8, 14),
    )
    assert "lottery" in result.tags
    assert result.score < 70


def test_put_on_rising_stock_tagged_hedge():
    result = score_contract(
        _snap(
            occ_symbol="AAPL260918P220",
            underlying="AAPL",
            expiry=date(2026, 9, 18),
            strike=220,
            call_put="P",
            volume=11200,
            open_interest=4300,
            last_price=4.25,
            bid=4.15,
            ask=4.35,
            iv=0.24,
            spot=227.9,
        ),
        Baseline(avg_volume_20d=2000),
        UnderlyingFlow(call_premium=200_000, put_premium=4_700_000, spot_change_pct=1.4),
        asof=date(2026, 8, 14),
    )
    assert "possible_hedge" in result.tags
    assert result.direction == "hedge"


def test_roll_detection():
    a = _snap(occ_symbol="MSFT260821C430", underlying="MSFT", expiry=date(2026, 8, 21), strike=430, volume=7200)
    b = _snap(occ_symbol="MSFT260918C430", underlying="MSFT", expiry=date(2026, 9, 18), strike=430, volume=6800)
    rolled = detect_rolls([a, b])
    assert a.occ_symbol in rolled
    assert b.occ_symbol in rolled
