from app.detect.outcome import judge_outcome


def test_call_followed_is_good():
    out = judge_outcome(
        direction="bullish",
        call_put="C",
        entry_spot=178.4,
        later_spot=186.8,
        occ_status="confirmed",
        actionable=True,
        news=[{"title": "Chip demand comments lift names"}],
    )
    assert out.verdict == "followed"
    assert out.quality in ("good_signal", "mixed")
    assert "up" in out.plain


def test_call_wrong_way_is_poor():
    out = judge_outcome(
        direction="bullish",
        call_put="C",
        entry_spot=41.8,
        later_spot=40.1,
        occ_status="live",
        actionable=True,
    )
    assert out.verdict == "faded_price"
    assert out.quality == "poor_signal"


def test_hedge_is_not_a_trade():
    out = judge_outcome(
        direction="hedge",
        call_put="P",
        entry_spot=227.9,
        later_spot=231.2,
        occ_status="hedge",
        actionable=False,
        news=[{"title": "Apple shares firm"}],
    )
    assert out.quality == "not_a_trade"
    assert out.verdict == "not_directional"


def test_pending_without_later_price():
    out = judge_outcome(
        direction="bullish",
        call_put="C",
        entry_spot=178.4,
        later_spot=None,
        actionable=True,
    )
    assert out.verdict == "pending"
    assert out.quality == "too_soon"
