from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


MIGRATIONS = [
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS company_name TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS plain_english TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS last_price DOUBLE PRECISION",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS actionable BOOLEAN DEFAULT TRUE",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS suggested_action TEXT",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS signals_live_uniq
        ON signals (session_date, occ_symbol) WHERE status = 'live'
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_account (
        id INT PRIMARY KEY,
        cash DOUBLE PRECISION NOT NULL,
        starting_cash DOUBLE PRECISION NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_positions (
        id UUID PRIMARY KEY,
        signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
        kind TEXT NOT NULL,
        symbol TEXT NOT NULL,
        company_name TEXT,
        occ_symbol TEXT,
        expiry DATE,
        strike DOUBLE PRECISION,
        call_put CHAR(1),
        qty INT NOT NULL,
        entry_price DOUBLE PRECISION NOT NULL,
        entry_spot DOUBLE PRECISION,
        mark_price DOUBLE PRECISION,
        mark_spot DOUBLE PRECISION,
        opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        closed_at TIMESTAMPTZ,
        close_price DOUBLE PRECISION,
        realized_pnl DOUBLE PRECISION,
        result TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        thesis TEXT
    )
    """,
    "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'manual'",
    "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS score DOUBLE PRECISION",
    "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS tags TEXT[]",
    "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS close_reason TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_verdict TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_quality TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_return_pct DOUBLE PRECISION",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_spot DOUBLE PRECISION",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_plain TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_news JSONB DEFAULT '[]'::jsonb",
    """
    CREATE TABLE IF NOT EXISTS headlines (
        id SERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        title TEXT NOT NULL,
        published_at TIMESTAMPTZ,
        url TEXT,
        source TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_auto_log (
        id UUID PRIMARY KEY,
        signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
        action TEXT NOT NULL,
        reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE paper_account ADD COLUMN IF NOT EXISTS worker_state TEXT NOT NULL DEFAULT 'running'",
    "ALTER TABLE paper_account ADD COLUMN IF NOT EXISTS killed BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE paper_account ADD COLUMN IF NOT EXISTS last_error TEXT",
]


def init_db() -> None:
    engine = get_engine()
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text()
    with engine.begin() as conn:
        conn.execute(text(sql))
        for stmt in MIGRATIONS:
            conn.execute(text(stmt))
