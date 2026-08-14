from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.detect.outcome import judge_outcome

log = logging.getLogger(__name__)


def upsert_headline(session: Session, symbol: str, title: str, published_at, url: str | None = None, source: str = "yahoo") -> None:
    session.execute(
        text(
            """
            INSERT INTO headlines (symbol, title, published_at, url, source)
            VALUES (:s, :t, :p, :u, :src)
            """
        ),
        {"s": symbol.upper(), "t": title, "p": published_at, "u": url, "src": source},
    )


def load_fixture_news(session: Session, items: list[dict]) -> int:
    session.execute(text("DELETE FROM headlines WHERE source = 'replay'"))
    n = 0
    for item in items:
        pub = item.get("published_at") or item.get("when")
        if isinstance(pub, str):
            pub = datetime.fromisoformat(pub)
        upsert_headline(
            session,
            item["symbol"],
            item.get("title") or item.get("headline") or "",
            pub or datetime.now(timezone.utc),
            item.get("url"),
            item.get("source") or "replay",
        )
        n += 1
    session.commit()
    return n


def _news_for(session: Session, symbol: str, around: date) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT title, published_at, url, source
            FROM headlines
            WHERE symbol = :s
              AND published_at::date BETWEEN :a AND :b
            ORDER BY published_at DESC
            LIMIT 5
            """
        ),
        {"s": symbol, "a": around - timedelta(days=2), "b": around + timedelta(days=2)},
    ).mappings().all()
    return [
        {
            "title": r["title"],
            "published_at": r["published_at"].isoformat() if hasattr(r["published_at"], "isoformat") else r["published_at"],
            "url": r["url"],
            "source": r["source"],
        }
        for r in rows
    ]


def evaluate_outcomes(session: Session) -> int:
    """Score each alert: did the stock move the expected way, and was there news?"""
    rows = session.execute(
        text(
            """
            SELECT s.id, s.underlying, s.direction, s.call_put, s.spot, s.status, s.actionable,
                   s.session_date, u.last_spot, u.next_earnings
            FROM signals s
            LEFT JOIN underlyings u ON u.symbol = s.underlying
            """
        )
    ).mappings().all()
    n = 0
    for s in rows:
        later = s["last_spot"]
        around = s["session_date"] or date.today()
        news = _news_for(session, s["underlying"], around)
        earn = None
        if s["next_earnings"] and around:
            earn = (s["next_earnings"] - around).days
        out = judge_outcome(
            direction=s["direction"],
            call_put=s["call_put"],
            entry_spot=s["spot"],
            later_spot=later,
            occ_status=s["status"],
            actionable=bool(s["actionable"]) if s["actionable"] is not None else True,
            news=news,
            earnings_days=earn,
        )
        session.execute(
            text(
                """
                UPDATE signals SET
                    outcome_verdict = :v,
                    outcome_quality = :q,
                    outcome_return_pct = :r,
                    outcome_spot = :spot,
                    outcome_plain = :plain,
                    outcome_news = CAST(:news AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "v": out.verdict,
                "q": out.quality,
                "r": out.return_pct,
                "spot": out.later_spot,
                "plain": out.plain,
                "news": json.dumps(out.news),
                "id": s["id"],
            },
        )
        n += 1
    session.commit()
    log.info("evaluated outcomes for %s signals", n)
    return n
