from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.detect.confirm import ConfirmInput, confirm_signal
from app.detect.explain import explain_signal
from app.detect.score import Baseline, PriorSession, UnderlyingFlow, detect_rolls, score_contract
from app.providers.base import ContractSnapshot, MarketBundle, OccDailyRow, UnderlyingInfo
from app.redisutil import CHANNEL_SIGNALS, publish
from app.universe import SECTOR_ETFS

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def upsert_underlying(session: Session, u: UnderlyingInfo) -> None:
    session.execute(
        text(
            """
            INSERT INTO underlyings (symbol, name, sector, next_earnings, last_spot, last_spot_change_pct, last_spot_asof)
            VALUES (:symbol, :name, :sector, :next_earnings, :spot, :chg, :asof)
            ON CONFLICT (symbol) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, underlyings.name),
                sector = COALESCE(EXCLUDED.sector, underlyings.sector),
                next_earnings = COALESCE(EXCLUDED.next_earnings, underlyings.next_earnings),
                last_spot = COALESCE(EXCLUDED.last_spot, underlyings.last_spot),
                last_spot_change_pct = COALESCE(EXCLUDED.last_spot_change_pct, underlyings.last_spot_change_pct),
                last_spot_asof = COALESCE(EXCLUDED.last_spot_asof, underlyings.last_spot_asof)
            """
        ),
        {
            "symbol": u.symbol,
            "name": u.name,
            "sector": u.sector,
            "next_earnings": u.next_earnings,
            "spot": u.spot,
            "chg": u.spot_change_pct,
            "asof": u.asof,
        },
    )


def upsert_contract(session: Session, s: ContractSnapshot) -> None:
    session.execute(
        text(
            """
            INSERT INTO contracts (occ_symbol, underlying, expiry, strike, call_put)
            VALUES (:occ, :und, :exp, :strike, :cp)
            ON CONFLICT (occ_symbol) DO NOTHING
            """
        ),
        {"occ": s.occ_symbol, "und": s.underlying, "exp": s.expiry, "strike": s.strike, "cp": s.call_put},
    )


def insert_snapshot(session: Session, s: ContractSnapshot) -> None:
    session.execute(
        text(
            """
            INSERT INTO snapshots (time, occ_symbol, source, volume, open_interest, last_price, bid, ask, iv, spot, est_premium)
            VALUES (:time, :occ, :source, :vol, :oi, :last, :bid, :ask, :iv, :spot, :prem)
            """
        ),
        {
            "time": s.asof or datetime.now(timezone.utc),
            "occ": s.occ_symbol,
            "source": s.source,
            "vol": s.volume,
            "oi": s.open_interest,
            "last": s.last_price,
            "bid": s.bid,
            "ask": s.ask,
            "iv": s.iv,
            "spot": s.spot,
            "prem": s.est_premium,
        },
    )


def upsert_occ_row(session: Session, r: OccDailyRow) -> None:
    session.execute(
        text(
            """
            INSERT INTO occ_daily (session_date, occ_symbol, underlying, expiry, strike, call_put, volume, open_interest)
            VALUES (:d, :occ, :und, :exp, :strike, :cp, :vol, :oi)
            ON CONFLICT (session_date, occ_symbol, call_put) DO UPDATE SET
                volume = COALESCE(EXCLUDED.volume, occ_daily.volume),
                open_interest = COALESCE(EXCLUDED.open_interest, occ_daily.open_interest)
            """
        ),
        {
            "d": r.session_date,
            "occ": r.occ_symbol,
            "und": r.underlying,
            "exp": r.expiry,
            "strike": r.strike,
            "cp": r.call_put,
            "vol": r.volume,
            "oi": r.open_interest,
        },
    )


def rebuild_baselines(session: Session, asof: date) -> None:
    session.execute(
        text(
            """
            INSERT INTO contract_baselines (occ_symbol, asof_date, avg_volume_20d, p50_premium, p90_premium, p99_premium, avg_iv, sessions_count)
            SELECT occ_symbol,
                   :asof,
                   AVG(volume),
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(volume,0) * COALESCE(
                       (SELECT last_price FROM snapshots s WHERE s.occ_symbol = o.occ_symbol ORDER BY time DESC LIMIT 1), 0
                   ) * 100),
                   PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY COALESCE(volume,0)),
                   PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY COALESCE(volume,0)),
                   NULL,
                   COUNT(*)
            FROM occ_daily o
            WHERE session_date >= :start AND session_date < :asof
            GROUP BY occ_symbol
            ON CONFLICT (occ_symbol) DO UPDATE SET
                asof_date = EXCLUDED.asof_date,
                avg_volume_20d = EXCLUDED.avg_volume_20d,
                sessions_count = EXCLUDED.sessions_count
            """
        ),
        {"asof": asof, "start": asof - timedelta(days=40)},
    )
    # Simpler, robust baseline from occ_daily volume + stored snapshots
    session.execute(
        text(
            """
            INSERT INTO contract_baselines (occ_symbol, asof_date, avg_volume_20d, p50_premium, p90_premium, p99_premium, avg_iv, sessions_count)
            SELECT occ_symbol, :asof, AVG(volume)::float, NULL, NULL, NULL, NULL, COUNT(*)
            FROM occ_daily
            WHERE session_date >= :start AND session_date < :asof AND volume IS NOT NULL
            GROUP BY occ_symbol
            ON CONFLICT (occ_symbol) DO UPDATE SET
                asof_date = EXCLUDED.asof_date,
                avg_volume_20d = EXCLUDED.avg_volume_20d,
                sessions_count = EXCLUDED.sessions_count
            """
        ),
        {"asof": asof, "start": asof - timedelta(days=40)},
    )
    session.execute(
        text(
            """
            INSERT INTO underlying_baselines (symbol, asof_date, avg_daily_premium, p90_daily_premium, p99_daily_premium, avg_call_volume, avg_put_volume)
            SELECT underlying, :asof,
                   AVG(volume)::float * 100,
                   PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY volume) * 100,
                   PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY volume) * 100,
                   AVG(volume) FILTER (WHERE call_put = 'C'),
                   AVG(volume) FILTER (WHERE call_put = 'P')
            FROM occ_daily
            WHERE session_date >= :start AND session_date < :asof
            GROUP BY underlying
            ON CONFLICT (symbol) DO UPDATE SET
                asof_date = EXCLUDED.asof_date,
                avg_daily_premium = EXCLUDED.avg_daily_premium,
                p90_daily_premium = EXCLUDED.p90_daily_premium,
                p99_daily_premium = EXCLUDED.p99_daily_premium,
                avg_call_volume = EXCLUDED.avg_call_volume,
                avg_put_volume = EXCLUDED.avg_put_volume
            """
        ),
        {"asof": asof, "start": asof - timedelta(days=40)},
    )


def _load_baseline(session: Session, occ_symbol: str, underlying: str) -> Baseline:
    row = session.execute(
        text("SELECT avg_volume_20d, p50_premium, p90_premium, p99_premium, avg_iv, sessions_count FROM contract_baselines WHERE occ_symbol = :s"),
        {"s": occ_symbol},
    ).mappings().first()
    und = session.execute(
        text("SELECT p90_daily_premium, p99_daily_premium FROM underlying_baselines WHERE symbol = :s"),
        {"s": underlying},
    ).mappings().first()
    b = Baseline()
    if row:
        b.avg_volume_20d = row["avg_volume_20d"]
        b.p50_premium = row["p50_premium"]
        b.p90_premium = row["p90_premium"]
        b.p99_premium = row["p99_premium"]
        b.avg_iv = row["avg_iv"]
        b.sessions_count = row["sessions_count"] or 0
    if und:
        b.und_p90_premium = und["p90_daily_premium"]
        b.und_p99_premium = und["p99_daily_premium"]
    return b


def _prior_sessions(session: Session, occ_symbol: str, asof: date) -> list[PriorSession]:
    rows = session.execute(
        text(
            """
            SELECT session_date, COALESCE(volume,0) AS volume, COALESCE(open_interest,0) AS oi
            FROM occ_daily
            WHERE occ_symbol = :s AND session_date < :asof
            ORDER BY session_date DESC
            LIMIT 8
            """
        ),
        {"s": occ_symbol, "asof": asof},
    ).mappings().all()
    out = []
    for r in reversed(list(rows)):
        vol, oi = int(r["volume"] or 0), int(r["oi"] or 0)
        unusual = (oi > 0 and vol / oi >= 2.0) or vol >= 3000
        out.append(PriorSession(session_date=r["session_date"], volume=vol, open_interest=oi, unusual=unusual))
    return out


def _yesterday_volume(session: Session, occ_symbol: str, asof: date) -> int | None:
    row = session.execute(
        text("SELECT volume FROM occ_daily WHERE occ_symbol = :s AND session_date < :asof ORDER BY session_date DESC LIMIT 1"),
        {"s": occ_symbol, "asof": asof},
    ).first()
    return int(row[0]) if row and row[0] is not None else None


def persist_bundle(session: Session, bundle: MarketBundle) -> None:
    for u in bundle.underlyings:
        upsert_underlying(session, u)
    for s in bundle.snapshots:
        if s.underlying not in {u.symbol for u in bundle.underlyings}:
            upsert_underlying(session, UnderlyingInfo(symbol=s.underlying, spot=s.spot, asof=s.asof))
        upsert_contract(session, s)
        insert_snapshot(session, s)
    for r in bundle.occ_rows:
        if r.underlying:
            upsert_underlying(session, UnderlyingInfo(symbol=r.underlying))
        # ensure contract exists
        upsert_contract(
            session,
            ContractSnapshot(
                occ_symbol=r.occ_symbol,
                underlying=r.underlying,
                expiry=r.expiry,
                strike=r.strike,
                call_put=r.call_put,
            ),
        )
        upsert_occ_row(session, r)
    asof = (bundle.asof.astimezone(ET).date() if bundle.asof.tzinfo else bundle.asof.date())
    rebuild_baselines(session, asof)
    session.commit()


def score_bundle(session: Session, bundle: MarketBundle) -> list[dict]:
    settings = get_settings()
    asof = bundle.asof.astimezone(ET).date() if bundle.asof.tzinfo else bundle.asof.date()
    rolled = detect_rolls(bundle.snapshots)

    und_map = {u.symbol: u for u in bundle.underlyings}
    flow_by_und: dict[str, UnderlyingFlow] = defaultdict(UnderlyingFlow)
    for s in bundle.snapshots:
        f = flow_by_und[s.underlying]
        prem = s.est_premium or 0.0
        if s.call_put == "C":
            f.call_premium += prem
            f.call_volume += s.volume or 0
        else:
            f.put_premium += prem
            f.put_volume += s.volume or 0
        u = und_map.get(s.underlying)
        if u:
            f.spot_change_pct = u.spot_change_pct
            if u.next_earnings:
                f.earnings_days = (u.next_earnings - asof).days

    # sector confluence: count underlyings in same sector with one-sided high premium
    sector_of = {u.symbol: u.sector for u in bundle.underlyings if u.sector}
    unusual_und: set[str] = set()
    for sym, f in flow_by_und.items():
        if f.total_premium >= 250_000 and (f.call_share >= 0.7 or f.call_share <= 0.3):
            unusual_und.add(sym)
    for s in bundle.snapshots:
        sector = sector_of.get(s.underlying)
        if not sector:
            continue
        peers = [p for p, sec in sector_of.items() if sec == sector and p in unusual_und and p != s.underlying]
        etf = SECTOR_ETFS.get(sector)
        extra = 1 if etf and etf in unusual_und else 0
        flow_by_und[s.underlying].sector_peers_unusual = len(peers) + extra

    created: list[dict] = []
    # Replace today's live signals for these contracts
    for s in bundle.snapshots:
        if not s.volume or s.volume < 50:
            continue
        result = score_contract(
            s,
            _load_baseline(session, s.occ_symbol, s.underlying),
            flow_by_und[s.underlying],
            prior=_prior_sessions(session, s.occ_symbol, asof),
            yesterday_volume=_yesterday_volume(session, s.occ_symbol, asof),
            asof=asof,
        )
        if s.occ_symbol in rolled:
            result.tags.append("roll")
            result.reasons.append({"code": "roll", "text": "Same strike printing in two expiries — likely a roll"})
            result.score = round(max(0.0, result.score - 25.0), 1)

        if result.score < settings.feed_min_score:
            continue

        und = und_map.get(s.underlying)
        expl = explain_signal(s, result, company_name=und.name if und else None, asof=asof)
        sid = uuid.uuid4()
        payload = {
            "id": str(sid),
            "created_at": datetime.now(timezone.utc),
            "occ_symbol": s.occ_symbol,
            "underlying": s.underlying,
            "expiry": s.expiry,
            "strike": s.strike,
            "call_put": s.call_put,
            "score": result.score,
            "direction": result.direction,
            "status": "live",
            "reasons": json.dumps(result.reasons),
            "tags": result.tags,
            "volume": s.volume,
            "open_interest": s.open_interest,
            "vol_oi": result.vol_oi,
            "est_premium": result.est_premium,
            "iv": s.iv,
            "iv_delta": result.iv_delta,
            "spot": s.spot,
            "source": s.source,
            "data_asof": s.asof,
            "session_date": asof,
            "company_name": expl.company_name,
            "plain_english": expl.plain_english,
            "last_price": s.last_price or s.mid,
            "actionable": expl.actionable,
            "suggested_action": expl.suggested_action,
        }
        session.execute(
            text(
                """
                INSERT INTO signals (
                    id, created_at, occ_symbol, underlying, expiry, strike, call_put, score, direction, status,
                    reasons, tags, volume, open_interest, vol_oi, est_premium, iv, iv_delta, spot, source, data_asof, session_date,
                    company_name, plain_english, last_price, actionable, suggested_action
                ) VALUES (
                    :id, :created_at, :occ_symbol, :underlying, :expiry, :strike, :call_put, :score, :direction, :status,
                    CAST(:reasons AS jsonb), :tags, :volume, :open_interest, :vol_oi, :est_premium, :iv, :iv_delta, :spot, :source, :data_asof, :session_date,
                    :company_name, :plain_english, :last_price, :actionable, :suggested_action
                )
                ON CONFLICT (session_date, occ_symbol) WHERE status = 'live' DO UPDATE SET
                    score = EXCLUDED.score,
                    direction = EXCLUDED.direction,
                    reasons = EXCLUDED.reasons,
                    tags = EXCLUDED.tags,
                    volume = EXCLUDED.volume,
                    open_interest = EXCLUDED.open_interest,
                    vol_oi = EXCLUDED.vol_oi,
                    est_premium = EXCLUDED.est_premium,
                    iv = EXCLUDED.iv,
                    iv_delta = EXCLUDED.iv_delta,
                    spot = EXCLUDED.spot,
                    data_asof = EXCLUDED.data_asof,
                    company_name = EXCLUDED.company_name,
                    plain_english = EXCLUDED.plain_english,
                    last_price = EXCLUDED.last_price,
                    actionable = EXCLUDED.actionable,
                    suggested_action = EXCLUDED.suggested_action
                """
            ),
            payload,
        )
        kept = session.execute(
            text(
                """
                SELECT id FROM signals
                WHERE session_date = :session_date AND occ_symbol = :occ_symbol AND status = 'live'
                """
            ),
            payload,
        ).scalar()
        payload["id"] = str(kept or sid)
        pub = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in payload.items()}
        pub["reasons"] = result.reasons
        created.append(pub)
        if result.score >= settings.unusual_min_score:
            publish(CHANNEL_SIGNALS, pub)

    session.commit()
    log.info("scored %s contracts, kept %s signals", len(bundle.snapshots), len(created))
    return created


def run_confirmation(session: Session, asof: date | None = None) -> int:
    asof = asof or datetime.now(ET).date()
    yesterday = asof - timedelta(days=1)
    # walk back to last weekday with signals
    rows = session.execute(
        text(
            """
            SELECT s.id, s.call_put, s.direction, s.underlying, s.occ_symbol, s.open_interest AS prior_oi, s.session_date,
                   u.last_spot_change_pct
            FROM signals s
            LEFT JOIN underlyings u ON u.symbol = s.underlying
            WHERE s.status = 'live' AND s.session_date < :asof
            """
        ),
        {"asof": asof},
    ).mappings().all()
    updated = 0
    for row in rows:
        occ_row = session.execute(
            text(
                """
                SELECT open_interest FROM occ_daily
                WHERE occ_symbol = :occ AND session_date >= :d
                ORDER BY session_date ASC LIMIT 1
                """
            ),
            {"occ": row["occ_symbol"], "d": row["session_date"] + timedelta(days=1)},
        ).first()
        new_oi = int(occ_row[0]) if occ_row and occ_row[0] is not None else None
        prior_oi = int(row["prior_oi"] or 0)
        oi_change = (new_oi - prior_oi) if new_oi is not None else None
        status, note = confirm_signal(
            ConfirmInput(
                call_put=row["call_put"],
                spot_change_pct=row["last_spot_change_pct"],
                oi_change=oi_change,
                prior_oi=prior_oi,
                direction=row["direction"],
            )
        )
        if new_oi is None:
            continue
        reasons = session.execute(text("SELECT reasons, plain_english FROM signals WHERE id = :id"), {"id": row["id"]}).mappings().first()
        rs = list((reasons["reasons"] if reasons else None) or [])
        rs.append({"code": "occ", "text": note})
        plain = (reasons["plain_english"] if reasons else "") or ""
        occ_plain = {
            "confirmed": " Next-morning official records: open interest rose, so someone actually stayed in this position.",
            "faded": " Next-morning official records: open interest did not rise. Yesterday's volume was likely a day trade that was closed.",
            "hedge": " Next-morning official records: puts were opened while the stock went up — that is usually insurance, not a bet the stock will fall.",
        }.get(status, "")
        if occ_plain and occ_plain.strip() not in plain:
            plain = (plain + occ_plain).strip()
        session.execute(
            text(
                """
                UPDATE signals SET status = :st, reasons = CAST(:rs AS jsonb), plain_english = :plain
                WHERE id = :id
                """
            ),
            {"st": status, "rs": json.dumps(rs), "id": row["id"], "plain": plain},
        )
        updated += 1
    session.commit()
    log.info("confirmed %s signals against OCC OI", updated)
    return updated


def seed_demo_yesterday_signals(session: Session, asof: date) -> None:
    """Insert a few prior-session live signals so OCC confirmation has something to flip."""
    yesterday = asof - timedelta(days=1)
    demo_occs = ["NVDA260821C185", "AAPL260815P225", "TSLA260815C255"]
    used = session.execute(
        text(
            """
            SELECT 1 FROM paper_positions
            WHERE occ_symbol = ANY(CAST(:occs AS text[]))
               OR signal_id IN (SELECT id FROM signals WHERE occ_symbol = ANY(CAST(:occs AS text[])) AND session_date = :d)
            LIMIT 1
            """
        ),
        {"occs": demo_occs, "d": yesterday},
    ).first()
    if used:
        return
    session.execute(
        text("DELETE FROM signals WHERE occ_symbol = ANY(CAST(:occs AS text[])) AND session_date = :d"),
        {"occs": demo_occs, "d": yesterday},
    )
    samples = [
        {
            "occ": "NVDA260821C185",
            "und": "NVDA",
            "exp": date(2026, 8, 21),
            "strike": 185,
            "cp": "C",
            "score": 86,
            "direction": "bullish",
            "tags": ["vol_gt_oi", "likely_opening", "size"],
            "volume": 6400,
            "oi": 900,
            "vol_oi": 7.11,
            "prem": 1_280_000,
            "reasons": [{"code": "voi", "text": "vol/OI 7.1 (prior OI 900)"}],
            "company": "NVIDIA (NVDA)",
            "plain": "NVIDIA (NVDA) showed a huge burst in the August 21 $185 call. Volume was about 7× what was already open, and roughly $1.3 million changed hands. That usually means a new bet the stock goes up, not someone closing an old trade. We wait for official open interest the next morning to see if they stayed in.",
            "last": 2.0,
            "spot": 178.4,
        },
        {
            "occ": "AAPL260815P225",
            "und": "AAPL",
            "exp": date(2026, 8, 15),
            "strike": 225,
            "cp": "P",
            "score": 78,
            "direction": "bearish",
            "tags": ["vol_gt_oi", "possible_hedge"],
            "volume": 9000,
            "oi": 1500,
            "vol_oi": 6.0,
            "prem": 720_000,
            "reasons": [{"code": "hedge", "text": "put volume on a rising stock"}],
            "company": "Apple (AAPL)",
            "plain": "Apple (AAPL) saw heavy trading in the August 15 $225 put while the stock itself was rising. A put pays if the stock falls — but when the stock is going up, this is usually insurance (a hedge), not a bet Apple will crash. Copying this as a short would likely be reading it backwards.",
            "last": 0.80,
            "spot": 227.9,
            "actionable": False,
        },
        {
            "occ": "TSLA260815C255",
            "und": "TSLA",
            "exp": date(2026, 8, 15),
            "strike": 255,
            "cp": "C",
            "score": 74,
            "direction": "bullish",
            "tags": ["vol_gt_oi"],
            "volume": 15000,
            "oi": 4000,
            "vol_oi": 3.75,
            "prem": 900_000,
            "reasons": [{"code": "vol", "text": "large one-day print"}],
            "company": "Tesla (TSLA)",
            "plain": "Tesla (TSLA) had a large one-day burst in the August 15 $255 call. About 15,000 contracts traded. A single noisy day is weaker than activity that repeats. Official open interest the next morning tells us if this was a real new position or a day trade that vanished.",
            "last": 0.60,
            "spot": 241.0,
        },
    ]
    for s in samples:
        upsert_underlying(session, UnderlyingInfo(symbol=s["und"], name=s.get("company")))
        upsert_contract(
            session,
            ContractSnapshot(
                occ_symbol=s["occ"],
                underlying=s["und"],
                expiry=s["exp"],
                strike=s["strike"],
                call_put=s["cp"],
            ),
        )
        session.execute(
            text(
                """
                INSERT INTO signals (
                    id, created_at, occ_symbol, underlying, expiry, strike, call_put, score, direction, status,
                    reasons, tags, volume, open_interest, vol_oi, est_premium, source, data_asof, session_date,
                    company_name, plain_english, last_price, spot, actionable
                ) VALUES (
                    :id, :created_at, :occ, :und, :exp, :strike, :cp, :score, :dir, 'live',
                    CAST(:reasons AS jsonb), :tags, :vol, :oi, :voi, :prem, 'replay', :asof, :sd,
                    :company, :plain, :last, :spot, :actionable
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "created_at": datetime(2026, 8, 13, 15, 40, tzinfo=timezone.utc),
                "occ": s["occ"],
                "und": s["und"],
                "exp": s["exp"],
                "strike": s["strike"],
                "cp": s["cp"],
                "score": s["score"],
                "dir": s["direction"],
                "reasons": json.dumps(s["reasons"]),
                "tags": s["tags"],
                "vol": s["volume"],
                "oi": s["oi"],
                "voi": s["vol_oi"],
                "prem": s["prem"],
                "asof": datetime(2026, 8, 13, 15, 40, tzinfo=timezone.utc),
                "sd": yesterday,
                "company": s.get("company"),
                "plain": s.get("plain"),
                "last": s.get("last"),
                "spot": s.get("spot"),
                "actionable": s.get("actionable", True),
            },
        )
    session.commit()


def seed_screeners(session: Session) -> None:
    presets = [
        ("opening_calls", "Opening calls", {"call_put": "C", "min_vol_oi": 2, "exclude_tags": ["0dte", "two_sided"]}),
        ("put_spikes", "Put volume spikes", {"call_put": "P", "min_score": 70, "exclude_tags": ["possible_hedge"]}),
        ("multi_day", "Multi-day accumulation", {"tags": ["multi_day"], "min_score": 65}),
        ("one_sided_clean", "One-sided, no earnings", {"tags": ["one_sided"], "exclude_tags": ["earnings", "0dte", "two_sided"], "min_score": 70}),
    ]
    for pid, name, filters in presets:
        session.execute(
            text(
                """
                INSERT INTO screeners (id, name, filters, builtin)
                VALUES (:id, :name, CAST(:filters AS jsonb), TRUE)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, filters = EXCLUDED.filters
                """
            ),
            {"id": pid, "name": name, "filters": json.dumps(filters)},
        )
    session.execute(
        text(
            """
            INSERT INTO alert_rules (id, name, enabled, min_score, filters, channels, cooldown_seconds, digest_seconds)
            SELECT CAST(:id AS uuid), 'High conviction', TRUE, 80,
                   '{"exclude_tags":["0dte","roll","two_sided"]}'::jsonb,
                   '[]'::jsonb, 1800, 900
            WHERE NOT EXISTS (SELECT 1 FROM alert_rules)
            """
        ),
        {"id": str(uuid.uuid4())},
    )
    session.commit()


def apply_later_marks(session: Session, marks: list[dict]) -> int:
    """Apply 'what happened next' prices so paper trades can show a winner/loser."""
    n = 0
    for m in marks:
        asof = m.get("asof")
        occ = m.get("occ_symbol")
        if not occ:
            continue
        session.execute(
            text(
                """
                INSERT INTO snapshots (time, occ_symbol, source, last_price, spot, volume, open_interest)
                VALUES (:t, :occ, 'replay_mark', :last, :spot, NULL, NULL)
                """
            ),
            {
                "t": datetime.fromisoformat(asof) if asof else datetime.now(timezone.utc),
                "occ": occ,
                "last": m.get("last_price"),
                "spot": m.get("spot"),
            },
        )
        if m.get("underlying") and m.get("spot") is not None:
            session.execute(
                text("UPDATE underlyings SET last_spot = :spot, last_spot_asof = NOW() WHERE symbol = :s"),
                {"spot": m["spot"], "s": m["underlying"]},
            )
        n += 1
    session.commit()
    return n


def set_health(session: Session, key: str, value: dict) -> None:
    session.execute(
        text(
            """
            INSERT INTO health_state (key, value, updated_at)
            VALUES (:k, CAST(:v AS jsonb), NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """
        ),
        {"k": key, "v": json.dumps(value, default=str)},
    )
    session.commit()
