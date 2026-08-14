from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.autotrade import DEFAULT_AUTO, get_auto_settings, save_auto_settings
from app.jobs.paper import get_account, reset_account, seed_account


def load_desk_settings(session: Session) -> dict[str, Any]:
    settings = get_settings()
    row = session.execute(text("SELECT value FROM settings WHERE key = 'desk'")).scalar()
    stored: dict[str, Any] = {}
    if row:
        stored = json.loads(row) if isinstance(row, str) else dict(row)
    auto = get_auto_settings(session)
    watch = list(session.execute(text("SELECT symbol FROM watchlist ORDER BY symbol")).scalars().all())
    return {
        "data_mode": settings.data_mode,
        "poll_interval_seconds": int(stored.get("poll_interval_seconds", settings.poll_interval_seconds)),
        "max_scan_underlyings": int(stored.get("max_scan_underlyings", settings.max_scan_underlyings)),
        "feed_min_score": float(stored.get("feed_min_score", settings.feed_min_score)),
        "unusual_min_score": float(stored.get("unusual_min_score", settings.unusual_min_score)),
        "alert_min_score": float(stored.get("alert_min_score", settings.alert_min_score)),
        "auto_enabled": bool(auto.get("enabled", DEFAULT_AUTO["enabled"])),
        "auto_min_score": float(auto.get("min_score", DEFAULT_AUTO["min_score"])),
        "option_take_profit": float(auto.get("option_take_profit", DEFAULT_AUTO["option_take_profit"])),
        "option_stop_loss": float(auto.get("option_stop_loss", DEFAULT_AUTO["option_stop_loss"])),
        "stock_take_profit": float(auto.get("stock_take_profit", DEFAULT_AUTO["stock_take_profit"])),
        "stock_stop_loss": float(auto.get("stock_stop_loss", DEFAULT_AUTO["stock_stop_loss"])),
        "watchlist": ",".join(watch),
        "paper_bankroll": settings.paper_bankroll,
    }


def save_desk_settings(session: Session, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_desk_settings(session)
    merged = {**current, **{k: v for k, v in updates.items() if v is not None}}
    desk_keys = (
        "poll_interval_seconds",
        "max_scan_underlyings",
        "feed_min_score",
        "unusual_min_score",
        "alert_min_score",
    )
    session.execute(
        text(
            """
            INSERT INTO settings (key, value) VALUES ('desk', CAST(:v AS jsonb))
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {"v": json.dumps({k: merged[k] for k in desk_keys})},
    )
    save_auto_settings(
        session,
        {
            "enabled": bool(merged["auto_enabled"]),
            "min_score": float(merged["auto_min_score"]),
            "option_take_profit": float(merged["option_take_profit"]),
            "option_stop_loss": float(merged["option_stop_loss"]),
            "stock_take_profit": float(merged["stock_take_profit"]),
            "stock_stop_loss": float(merged["stock_stop_loss"]),
        },
    )
    if "watchlist" in updates and updates["watchlist"] is not None:
        symbols = [s.strip().upper() for s in str(updates["watchlist"]).replace(";", ",").split(",") if s.strip()]
        session.execute(text("DELETE FROM watchlist"))
        for sym in symbols:
            session.execute(
                text("INSERT INTO watchlist (symbol) VALUES (:s) ON CONFLICT (symbol) DO NOTHING"),
                {"s": sym},
            )
        session.commit()
    return load_desk_settings(session)


def set_worker_control(session: Session, *, state: str | None = None, killed: bool | None = None, last_error: str | None = False) -> dict:
    seed_account(session)
    if state is not None:
        session.execute(text("UPDATE paper_account SET worker_state = :s, updated_at = NOW() WHERE id = 1"), {"s": state})
    if killed is not None:
        session.execute(text("UPDATE paper_account SET killed = :k, updated_at = NOW() WHERE id = 1"), {"k": killed})
    if last_error is not False:
        session.execute(text("UPDATE paper_account SET last_error = :e, updated_at = NOW() WHERE id = 1"), {"e": last_error})
    session.commit()
    return get_account(session)


def apply_control(session: Session, action: str) -> dict:
    seed_account(session)
    if action == "start":
        return set_worker_control(session, state="running", killed=False, last_error=None)
    if action == "pause":
        return set_worker_control(session, state="paused", killed=False)
    if action == "kill":
        return set_worker_control(session, state="halted", killed=True)
    if action == "reset":
        reset_account(session, wipe_history=False)
        return set_worker_control(session, state="running", killed=False, last_error=None)
    raise ValueError(action)
