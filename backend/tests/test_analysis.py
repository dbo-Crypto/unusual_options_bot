from app.jobs.analysis import _bucket, _lessons
from app.jobs.autotrade import SKIP_TAGS, decide_exit
from app.jobs.grok_review import build_premium_prompt, import_pasted_review, write_local_review


def test_skip_list_covers_noise():
    assert "lottery" in SKIP_TAGS
    assert "possible_hedge" in SKIP_TAGS
    assert "0dte" in SKIP_TAGS
    assert "two_sided" in SKIP_TAGS


def test_bucket_win_rate():
    trades = [
        {"status": "closed", "realized_pnl": 80, "qty": 1, "entry_price": 1, "mark_price": 1, "kind": "stock"},
        {"status": "closed", "realized_pnl": -20, "qty": 1, "entry_price": 1, "mark_price": 1, "kind": "stock"},
        {"status": "closed", "realized_pnl": 10, "qty": 1, "entry_price": 1, "mark_price": 1, "kind": "stock"},
    ]
    b = _bucket(trades)
    assert b["n"] == 3
    assert b["winners"] == 2
    assert b["losers"] == 1
    assert b["total_pnl"] == 70
    assert b["win_rate"] == 66.7


def test_auto_exit_option_take_profit():
    why = decide_exit(
        kind="option",
        call_put="C",
        entry=5.0,
        mark=7.0,
        entry_spot=100,
        mark_spot=102,
        signal_status="live",
        opposite_flow=False,
        cfg={"option_take_profit": 0.3, "option_stop_loss": 0.4, "stock_take_profit": 0.05, "stock_stop_loss": 0.04},
    )
    assert why and "take-profit" in why


def test_auto_exit_faded_thesis():
    why = decide_exit(
        kind="option",
        call_put="P",
        entry=4.0,
        mark=3.9,
        entry_spot=200,
        mark_spot=201,
        signal_status="faded",
        opposite_flow=False,
    )
    assert why and "faded" in why


def test_auto_exit_holds_inside_band():
    why = decide_exit(
        kind="stock",
        call_put=None,
        entry=178.0,
        mark=180.0,
        entry_spot=178.0,
        mark_spot=180.0,
        signal_status="live",
        opposite_flow=False,
    )
    assert why is None


def test_premium_prompt_contains_the_book():
    prompt = build_premium_prompt({"sample": {"trades": 2, "total_pnl": 10}, "trades": []})
    assert "unusual-options" in prompt.lower() or "paper" in prompt.lower()
    assert '"trades": 2' in prompt


def test_local_grok_review_uses_the_book():
    memo = write_local_review(
        {
            "sample": {"trades": 4, "open": 2, "closed": 2, "win_rate": 100, "total_pnl": 352, "expectancy": 88},
            "by_kind": {
                "option": {"n": 2, "total_pnl": 340, "expectancy": 170},
                "stock": {"n": 2, "total_pnl": 12, "expectancy": 6},
            },
            "by_side": {"call": {"n": 4, "total_pnl": 352}},
            "trades": [
                {"status": "closed", "close_reason": "take-profit: option gained 31%", "pnl": 170, "tags": ["multi_day"]},
            ],
            "alert_outcomes": [
                {"quality": "good_signal", "verdict": "followed", "symbol": "NVDA"},
                {"quality": "poor_signal", "verdict": "faded_price", "symbol": "PLTR"},
            ],
        }
    )
    assert memo["findings"]
    assert memo["changes"]
    assert "tiny sample" in " ".join(memo["findings"]).lower() or "small" in memo["headline"].lower()


def test_lessons_mention_low_sample():
    overall = _bucket(
        [{"status": "closed", "realized_pnl": -5, "qty": 1, "entry_price": 1, "mark_price": 1, "kind": "option"}]
    )
    notes = _lessons(overall, {}, {}, {}, {}, {}, [])
    assert any("hint" in n.lower() or "only have 1" in n.lower() for n in notes)
