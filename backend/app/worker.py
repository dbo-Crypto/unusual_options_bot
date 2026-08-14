from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session, init_db
from app.jobs.alerts import dispatch_alerts
from app.jobs.autotrade import auto_close, auto_trade
from app.jobs.paper import mark_positions, seed_account
from app.jobs.outcomes import evaluate_outcomes, load_fixture_news, upsert_headline
from app.jobs.pipeline import (
    apply_later_marks,
    persist_bundle,
    run_confirmation,
    score_bundle,
    seed_demo_yesterday_signals,
    seed_screeners,
    set_health,
)
from app.providers.base import MarketBundle, UnderlyingInfo
from app.providers.occ import OccProvider
from app.providers.replay import ReplayProvider
from app.providers.yahoo import YahooProvider

logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")
ET = ZoneInfo("America/New_York")


def load_replay() -> None:
    settings = get_settings()
    session = get_session()
    try:
        seed_screeners(session)
        seed_account(session)
        provider = ReplayProvider(settings.fixtures_dir)
        bundle = provider.load_bundle()
        persist_bundle(session, bundle)
        signals = score_bundle(session, bundle)
        asof = bundle.asof.astimezone(ET).date() if bundle.asof.tzinfo else bundle.asof.date()
        seed_demo_yesterday_signals(session, asof)
        confirmed = run_confirmation(session, asof)
        auto_report = auto_trade(session)
        apply_later_marks(session, provider.load_later_marks())
        load_fixture_news(session, provider.load_news())
        evaluate_outcomes(session)
        mark_positions(session)
        sold = auto_close(session)
        auto_report["sold"] = sold
        dispatch_alerts(session, signals)
        set_health(
            session,
            "ingest",
            {
                "mode": "replay",
                "asof": bundle.asof.isoformat(),
                "snapshots": len(bundle.snapshots),
                "signals": len(signals),
                "confirmed": confirmed,
                "auto_bought": len(auto_report.get("bought") or []),
                "auto_sold": len(sold),
                "source": "replay",
            },
        )
        log.info(
            "replay loaded: %s snapshots, %s signals, auto-bought %s auto-sold %s",
            len(bundle.snapshots),
            len(signals),
            len(auto_report.get("bought") or []),
            len(sold),
        )
    finally:
        session.close()


def live_cycle() -> None:
    settings = get_settings()
    yahoo = YahooProvider()
    occ = OccProvider()
    session = get_session()
    try:
        seed_screeners(session)
        seed_account(session)
        watch = list(session.execute(text("SELECT symbol FROM watchlist")).scalars().all())
        prior = list(
            session.execute(
                text("SELECT DISTINCT underlying FROM signals WHERE created_at > NOW() - INTERVAL '2 days'")
            ).scalars().all()
        )
        symbols = list(dict.fromkeys([*watch, *prior, *yahoo.discover()]))[: settings.max_scan_underlyings]
        underlyings: list[UnderlyingInfo] = []
        snapshots = []
        occ_rows = []
        errors = 0
        for i, sym in enumerate(symbols):
            und = yahoo.fetch_underlying(sym)
            if und:
                underlyings.append(und)
            chain = yahoo.fetch_chain(sym)
            snapshots.extend(chain)
            # OCC OI only for names that already look active — keep Yahoo polite AND OCC polite
            if any((c.volume or 0) >= 500 for c in chain):
                occ_rows.extend(occ.fetch_occ_oi(sym))
            if i and i % 8 == 0:
                time.sleep(1.5)
        asof = datetime.now(ET)
        bundle = MarketBundle(asof=asof, underlyings=underlyings, snapshots=snapshots, occ_rows=occ_rows, source="yahoo")
        persist_bundle(session, bundle)
        signals = score_bundle(session, bundle)
        auto_report = auto_trade(session)
        try:
            seen = {s.get("underlying") for s in signals if s.get("underlying")}
            for sym in list(seen)[:25]:
                for item in yahoo.fetch_news(sym):
                    if item.get("title"):
                        upsert_headline(session, item["symbol"], item["title"], item.get("published_at"), item.get("url"), "yahoo")
            session.commit()
        except Exception:
            log.debug("live news attach skipped", exc_info=True)
        evaluate_outcomes(session)
        mark_positions(session)
        sold = auto_close(session)
        auto_report["sold"] = sold
        dispatch_alerts(session, signals)
        y_ping = yahoo.ping()
        o_ping = occ.ping()
        set_health(
            session,
            "ingest",
            {
                "mode": "live",
                "asof": asof.isoformat(),
                "scanned": symbols,
                "snapshots": len(snapshots),
                "signals": len(signals),
                "auto_bought": len(auto_report.get("bought") or []),
                "auto_sold": len(sold),
                "yahoo": y_ping,
                "occ": o_ping,
                "errors": errors,
                "source": "yahoo+occ",
                "delay": "15m",
            },
        )
        log.info("live cycle: scanned %s, snapshots %s, signals %s", len(symbols), len(snapshots), len(signals))
    except Exception:
        log.exception("live cycle failed")
        set_health(session, "ingest", {"mode": "live", "ok": False, "error": "cycle failed"})
    finally:
        session.close()


def occ_confirm_job() -> None:
    session = get_session()
    try:
        n = run_confirmation(session)
        sold = auto_close(session)
        set_health(session, "occ_confirm", {"updated": n, "auto_sold": len(sold), "asof": datetime.now(ET).isoformat()})
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    log.info("worker starting mode=%s", settings.data_mode)
    init_db()
    if settings.data_mode == "replay":
        load_replay()
        # Stay alive so compose doesn't flap; refresh replay hourly in case DB was wiped
        sched = BlockingScheduler(timezone=ET)
        sched.add_job(load_replay, IntervalTrigger(hours=6), id="replay_refresh")
        sched.start()
        return

    # Prime once, then schedule
    live_cycle()
    sched = BlockingScheduler(timezone=ET)
    sched.add_job(live_cycle, IntervalTrigger(seconds=settings.poll_interval_seconds), id="poll")
    sched.add_job(occ_confirm_job, CronTrigger(hour=7, minute=20, timezone=ET), id="occ_morning")
    sched.add_job(occ_confirm_job, CronTrigger(hour=18, minute=40, timezone=ET), id="occ_evening")
    sched.start()


if __name__ == "__main__":
    main()
