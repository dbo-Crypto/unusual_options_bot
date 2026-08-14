# Unusual Options Bot

A personal Dockerized **unusual options activity** terminal. It finds contracts whose volume, volume/open-interest, estimated premium, and implied-vol look abnormal versus that name's own history — then confirms the next morning with official OCC open interest.

This is **not** a clone of Unusual Whales' live print tape. That product sits on a licensed OPRA feed (sweeps, blocks, aggressor side). Those prints are not free. This app uses only free sources and is honest about it.

**Not investment advice.** Premium is estimated. Intraday data is delayed. Flow is a radar, not a signal to copy.

## Data (all free)

| Source | What it is | Role |
| --- | --- | --- |
| Yahoo Finance options chains (`yfinance`) | Delayed ~15m snapshots: last, bid, ask, volume, OI, IV | Intraday scanner |
| OCC series search (`marketdata.theocc.com`) | Official per-strike open interest | Next-day confirmation |
| OCC volume query | Official call/put volume by underlying | One-sided vs two-sided check |
| Checked-in fixtures | Replay tape | Saturday / first boot / CI |

No API keys. Yahoo is unofficial and can rate-limit — the worker is polite (watchlist + liquid universe, not the entire listed surface).

## Run

```bash
cd "/Users/damien/Documents/02 - Dev/unusual_options_bot"
cp .env.example .env
make up
```

- UI: http://localhost:3000
- Paper trades: http://localhost:3000/trades
- Control: http://localhost:3000/control
- API: http://localhost:8000/docs

Default `DATA_MODE=replay` loads fixtures so the UI is full immediately.

Live (delayed Yahoo + OCC):

```bash
make live
```

Stop:

```bash
make down
```

Tests (scoring, OCC parser, confirmation):

```bash
make test
```

## What the score is

Each contract gets an explainable 0–100 score:

- volume / prior OI
- volume vs 20-session average
- estimated premium vs that ticker's own distribution
- IV shock
- intraday acceleration
- multi-day accumulation with rising OI
- sector confluence

Penalties: 0DTE noise, earnings two-sided vol trades, rolls, lottery tickets, wide markets.

Default alerts fire at score ≥ 80 and drop 0DTE / rolls / two-sided flow.

The **OCC confirm** page is the important one. Yesterday's spike is only a position if official OI rose. If OI fell, it was covering. Puts opened on a rising stock are tagged **hedge**.

## Layout

```
backend/     FastAPI + worker (Python 3.12)
web/          Next.js terminal UI
docker-compose.yml
docker-compose.vps.yml
```

VPS (same box as `market_bot` / `prediction_bot`): see `DEPLOY.md`. UI at `/options/`.

To add a paid OPRA adapter later, implement `MarketDataProvider` and leave the UI alone.
