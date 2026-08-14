CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS underlyings (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    next_earnings DATE,
    last_spot DOUBLE PRECISION,
    last_spot_change_pct DOUBLE PRECISION,
    last_spot_asof TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS contracts (
    occ_symbol TEXT PRIMARY KEY,
    underlying TEXT NOT NULL REFERENCES underlyings(symbol) ON DELETE CASCADE,
    expiry DATE NOT NULL,
    strike DOUBLE PRECISION NOT NULL,
    call_put CHAR(1) NOT NULL CHECK (call_put IN ('C', 'P')),
    UNIQUE (underlying, expiry, strike, call_put)
);

CREATE TABLE IF NOT EXISTS snapshots (
    time TIMESTAMPTZ NOT NULL,
    occ_symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    volume BIGINT,
    open_interest BIGINT,
    last_price DOUBLE PRECISION,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    iv DOUBLE PRECISION,
    spot DOUBLE PRECISION,
    est_premium DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS occ_daily (
    session_date DATE NOT NULL,
    occ_symbol TEXT NOT NULL,
    underlying TEXT,
    expiry DATE,
    strike DOUBLE PRECISION,
    call_put CHAR(1),
    volume BIGINT,
    open_interest BIGINT,
    PRIMARY KEY (session_date, occ_symbol, call_put)
);

CREATE TABLE IF NOT EXISTS contract_baselines (
    occ_symbol TEXT PRIMARY KEY,
    asof_date DATE,
    avg_volume_20d DOUBLE PRECISION,
    p50_premium DOUBLE PRECISION,
    p90_premium DOUBLE PRECISION,
    p99_premium DOUBLE PRECISION,
    avg_iv DOUBLE PRECISION,
    sessions_count INT
);

CREATE TABLE IF NOT EXISTS underlying_baselines (
    symbol TEXT PRIMARY KEY,
    asof_date DATE,
    avg_daily_premium DOUBLE PRECISION,
    p90_daily_premium DOUBLE PRECISION,
    p99_daily_premium DOUBLE PRECISION,
    avg_call_volume DOUBLE PRECISION,
    avg_put_volume DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    occ_symbol TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry DATE,
    strike DOUBLE PRECISION,
    call_put CHAR(1),
    score DOUBLE PRECISION NOT NULL,
    direction TEXT,
    status TEXT NOT NULL DEFAULT 'live',
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    volume BIGINT,
    open_interest BIGINT,
    vol_oi DOUBLE PRECISION,
    est_premium DOUBLE PRECISION,
    iv DOUBLE PRECISION,
    iv_delta DOUBLE PRECISION,
    spot DOUBLE PRECISION,
    source TEXT,
    data_asof TIMESTAMPTZ,
    session_date DATE,
    company_name TEXT,
    plain_english TEXT,
    last_price DOUBLE PRECISION,
    actionable BOOLEAN DEFAULT TRUE,
    suggested_action TEXT,
    outcome_verdict TEXT,
    outcome_quality TEXT,
    outcome_return_pct DOUBLE PRECISION,
    outcome_spot DOUBLE PRECISION,
    outcome_plain TEXT,
    outcome_news JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS headlines (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    url TEXT,
    source TEXT
);

CREATE INDEX IF NOT EXISTS signals_score_idx ON signals (score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS signals_underlying_idx ON signals (underlying, session_date DESC);
CREATE INDEX IF NOT EXISTS signals_status_idx ON signals (status, session_date);

CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    min_score DOUBLE PRECISION NOT NULL DEFAULT 80,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    cooldown_seconds INT NOT NULL DEFAULT 1800,
    digest_seconds INT NOT NULL DEFAULT 900
);

CREATE TABLE IF NOT EXISTS alert_events (
    id UUID PRIMARY KEY,
    rule_id UUID REFERENCES alert_rules(id) ON DELETE CASCADE,
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    channel TEXT NOT NULL,
    payload JSONB,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screeners (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    filters JSONB NOT NULL,
    builtin BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS health_state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'snapshots'
    ) THEN
        PERFORM create_hypertable('snapshots', 'time', if_not_exists => TRUE);
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'timescaledb hypertable skipped: %', SQLERRM;
END $$;

CREATE INDEX IF NOT EXISTS snapshots_symbol_time_idx ON snapshots (occ_symbol, time DESC);

CREATE UNIQUE INDEX IF NOT EXISTS signals_live_uniq
    ON signals (session_date, occ_symbol) WHERE status = 'live';

CREATE TABLE IF NOT EXISTS paper_account (
    id INT PRIMARY KEY,
    cash DOUBLE PRECISION NOT NULL,
    starting_cash DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id UUID PRIMARY KEY,
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('stock', 'option')),
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
    thesis TEXT,
    origin TEXT DEFAULT 'manual',
    score DOUBLE PRECISION,
    tags TEXT[],
    close_reason TEXT
);

CREATE TABLE IF NOT EXISTS paper_auto_log (
    id UUID PRIMARY KEY,
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
