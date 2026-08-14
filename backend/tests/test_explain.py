from datetime import date, datetime, timezone

from app.detect.explain import company_label, explain_signal
from app.detect.score import Baseline, UnderlyingFlow, score_contract
from app.providers.base import ContractSnapshot


def test_company_label_uses_name():
    assert "NVIDIA" in company_label("NVDA", "NVIDIA Corporation")
    assert "NVDA" in company_label("NVDA", "NVIDIA Corporation")


def test_plain_english_mentions_company_and_why():
    snap = ContractSnapshot(
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
    result = score_contract(
        snap,
        Baseline(avg_volume_20d=900, und_p99_premium=800_000, avg_iv=0.39),
        UnderlyingFlow(call_premium=2_000_000, put_premium=80_000, spot_change_pct=-1.1, sector_peers_unusual=3),
        asof=date(2026, 8, 14),
    )
    expl = explain_signal(snap, result, company_name="NVIDIA Corporation", asof=date(2026, 8, 14))
    assert "NVIDIA" in expl.plain_english
    assert "call" in expl.plain_english.lower()
    assert "open" in expl.plain_english.lower()
    assert expl.actionable is True
    assert expl.suggested_action == "consider_long"


def test_hedge_is_not_actionable():
    snap = ContractSnapshot(
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
        asof=datetime(2026, 8, 14, 19, 45, tzinfo=timezone.utc),
    )
    result = score_contract(
        snap,
        Baseline(avg_volume_20d=2000),
        UnderlyingFlow(call_premium=200_000, put_premium=4_700_000, spot_change_pct=1.4),
        asof=date(2026, 8, 14),
    )
    expl = explain_signal(snap, result, company_name="Apple Inc.", asof=date(2026, 8, 14))
    assert expl.actionable is False
    assert expl.suggested_action == "skip"
    assert "insurance" in expl.plain_english.lower() or "hedge" in expl.plain_english.lower()
