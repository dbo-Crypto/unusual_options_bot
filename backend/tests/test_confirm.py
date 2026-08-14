from app.detect.confirm import ConfirmInput, confirm_signal


def test_call_oi_up_with_rally_is_confirmed():
    status, note = confirm_signal(
        ConfirmInput(call_put="C", spot_change_pct=1.2, oi_change=3300, prior_oi=900, direction="bullish")
    )
    assert status == "confirmed"
    assert "call" in note.lower()


def test_call_oi_up_on_dip_is_still_confirmed():
    status, note = confirm_signal(
        ConfirmInput(call_put="C", spot_change_pct=-1.1, oi_change=3300, prior_oi=900, direction="bullish")
    )
    assert status == "confirmed"
    assert "dip" in note.lower()


def test_put_oi_up_on_rally_is_hedge():
    status, _ = confirm_signal(
        ConfirmInput(call_put="P", spot_change_pct=1.4, oi_change=6700, prior_oi=1500, direction="bearish")
    )
    assert status == "hedge"


def test_oi_down_is_faded():
    status, _ = confirm_signal(
        ConfirmInput(call_put="C", spot_change_pct=0.2, oi_change=-100, prior_oi=4000, direction="bullish")
    )
    assert status == "faded"


def test_missing_oi_stays_live():
    status, _ = confirm_signal(
        ConfirmInput(call_put="C", spot_change_pct=1.0, oi_change=None, prior_oi=900, direction="bullish")
    )
    assert status == "live"
