from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session
from app.jobs.analysis import analyze_trades
from app.jobs.grok_review import (
    build_alert_outcomes,
    build_premium_prompt,
    import_pasted_review,
    pack_dataset,
    run_grok_review,
)
from app.jobs.autotrade import auto_close, auto_trade, get_auto_settings, save_auto_settings
from app.desk import apply_control, load_desk_settings, save_desk_settings
from app.jobs.paper import get_account, mark_positions, reset_account, seed_account

router = APIRouter()


def _row(m) -> dict[str, Any]:
    d = dict(m)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            d[k] = str(v)
    if isinstance(d.get("reasons"), str):
        d["reasons"] = json.loads(d["reasons"])
    if d.get("tags") is None:
        d["tags"] = []
    return d


class AlertRuleIn(BaseModel):
    name: str
    enabled: bool = True
    min_score: float = 80
    filters: dict[str, Any] = Field(default_factory=dict)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    cooldown_seconds: int = 1800
    digest_seconds: int = 900


class WatchlistIn(BaseModel):
    symbols: list[str]


class SettingsIn(BaseModel):
    value: dict[str, Any]


class GrokPasteIn(BaseModel):
    text: str


class PaperAutoIn(BaseModel):
    enabled: bool = True
    min_score: float = 80
    option_take_profit: float = 0.30
    option_stop_loss: float = 0.40
    stock_take_profit: float = 0.05
    stock_stop_loss: float = 0.04


class SettingsPatch(BaseModel):
    poll_interval_seconds: int | None = Field(default=None, ge=60, le=3600)
    max_scan_underlyings: int | None = Field(default=None, ge=5, le=200)
    feed_min_score: float | None = Field(default=None, ge=0, le=100)
    unusual_min_score: float | None = Field(default=None, ge=0, le=100)
    alert_min_score: float | None = Field(default=None, ge=0, le=100)
    auto_enabled: bool | None = None
    auto_min_score: float | None = Field(default=None, ge=50, le=100)
    option_take_profit: float | None = Field(default=None, ge=0.05, le=2)
    option_stop_loss: float | None = Field(default=None, ge=0.05, le=1)
    stock_take_profit: float | None = Field(default=None, ge=0.01, le=0.5)
    stock_stop_loss: float | None = Field(default=None, ge=0.01, le=0.5)
    watchlist: str | None = None


def _health_payload() -> dict[str, Any]:
    settings = get_settings()
    session = get_session()
    try:
        rows = session.execute(text("SELECT key, value, updated_at FROM health_state")).mappings().all()
        state = {r["key"]: {"value": r["value"], "updated_at": r["updated_at"].isoformat()} for r in rows}
        last_sig = session.execute(text("SELECT MAX(created_at) FROM signals")).scalar()
        n_sig = session.execute(text("SELECT COUNT(*) FROM signals")).scalar()
    finally:
        session.close()
    return {
        "ok": True,
        "mode": settings.data_mode,
        "signals": n_sig,
        "last_signal_at": last_sig.isoformat() if last_sig else None,
        "state": state,
        "poll_interval_seconds": settings.poll_interval_seconds,
        "max_scan_underlyings": settings.max_scan_underlyings,
        "cadence": (
            "Replay: load once at startup, refresh every 6 hours. No Yahoo/OCC calls."
            if settings.data_mode == "replay"
            else (
                f"Live: Yahoo + OCC every {settings.poll_interval_seconds // 60} minutes "
                f"(up to {settings.max_scan_underlyings} names). "
                "OCC confirmation 07:20 and 18:40 America/New_York."
            )
        ),
        "disclaimer": "Not investment advice. Premium is estimated. Intraday data is delayed. Flow is a radar, not a signal to copy.",
    }


@router.get("/health")
def health():
    return _health_payload()


@router.get("/overview")
def overview():
    session = get_session()
    try:
        seed_account(session)
        account = get_account(session)
        health_payload = _health_payload()
        settings = load_desk_settings(session)
        closed = account["winners"] + account["losers"] + account["flat"]
        win_rate = (account["winners"] / closed) if closed else None
        return _jsonable(
            {
                "account": account,
                "health": health_payload,
                "settings": settings,
                "stats": {
                    "wins": account["winners"],
                    "losses": account["losers"],
                    "flats": account["flat"],
                    "win_rate": win_rate,
                    "signals": health_payload.get("signals") or 0,
                },
            }
        )
    finally:
        session.close()


@router.get("/settings")
def settings_get():
    session = get_session()
    try:
        return load_desk_settings(session)
    finally:
        session.close()


@router.patch("/settings")
def settings_patch(body: SettingsPatch):
    session = get_session()
    try:
        return save_desk_settings(session, body.model_dump(exclude_none=True))
    finally:
        session.close()


@router.post("/control/{action}")
def control(action: str):
    session = get_session()
    try:
        try:
            account = apply_control(session, action)
        except ValueError:
            raise HTTPException(400, "Unknown action") from None
        return {
            "ok": True,
            "state": account.get("worker_state"),
            "killed": account.get("killed"),
        }
    finally:
        session.close()


@router.get("/signals")
def list_signals(
    min_score: float | None = None,
    call_put: str | None = None,
    underlying: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    exclude_tag: list[str] | None = Query(default=None),
    session_date: date | None = None,
    limit: int = 200,
):
    settings = get_settings()
    min_score = settings.feed_min_score if min_score is None else min_score
    clauses = ["s.score >= :min_score"]
    params: dict[str, Any] = {"min_score": min_score, "limit": min(limit, 500)}
    if call_put:
        clauses.append("s.call_put = :cp")
        params["cp"] = call_put
    if underlying:
        clauses.append("s.underlying = :und")
        params["und"] = underlying.upper()
    if status:
        clauses.append("s.status = :st")
        params["st"] = status
    if session_date:
        clauses.append("s.session_date = :sd")
        params["sd"] = session_date
    if tag:
        clauses.append(":tag = ANY(s.tags)")
        params["tag"] = tag
    sql = (
        f"SELECT s.*, COALESCE(s.company_name, u.name) AS company_name "
        f"FROM signals s LEFT JOIN underlyings u ON u.symbol = s.underlying "
        f"WHERE {' AND '.join(clauses)} "
        f"ORDER BY s.score DESC, s.created_at DESC LIMIT :limit"
    )
    session = get_session()
    try:
        rows = [_row(r) for r in session.execute(text(sql), params).mappings().all()]
    finally:
        session.close()
    if exclude_tag:
        ex = set(exclude_tag)
        rows = [r for r in rows if not ex.intersection(r.get("tags") or [])]
    return {"items": rows, "count": len(rows)}


@router.get("/signals/{signal_id}")
def get_signal(signal_id: str):
    session = get_session()
    try:
        row = session.execute(text("SELECT * FROM signals WHERE id = CAST(:id AS uuid)"), {"id": signal_id}).mappings().first()
    finally:
        session.close()
    if not row:
        raise HTTPException(404, "signal not found")
    return _row(row)


@router.get("/tickers/{symbol}")
def ticker(symbol: str):
    symbol = symbol.upper()
    session = get_session()
    try:
        und = session.execute(text("SELECT * FROM underlyings WHERE symbol = :s"), {"s": symbol}).mappings().first()
        if not und:
            raise HTTPException(404, "ticker not found")
        snaps = session.execute(
            text(
                """
                SELECT DISTINCT ON (c.occ_symbol)
                    c.occ_symbol, c.expiry, c.strike, c.call_put,
                    s.volume, s.open_interest, s.last_price, s.bid, s.ask, s.iv, s.spot, s.est_premium, s.time, s.source
                FROM contracts c
                JOIN snapshots s ON s.occ_symbol = c.occ_symbol
                WHERE c.underlying = :s
                ORDER BY c.occ_symbol, s.time DESC
                """
            ),
            {"s": symbol},
        ).mappings().all()
        signals = session.execute(
            text(
                """
                SELECT s.*, COALESCE(s.company_name, u.name) AS company_name
                FROM signals s LEFT JOIN underlyings u ON u.symbol = s.underlying
                WHERE s.underlying = :s
                ORDER BY s.session_date DESC, s.score DESC LIMIT 80
                """
            ),
            {"s": symbol},
        ).mappings().all()
        confirmed = [r for r in signals if r["status"] in ("confirmed", "faded", "hedge")]
        live = [r for r in signals if r["status"] == "live"]
        call_p = sum((r["est_premium"] or 0) for r in snaps if r["call_put"] == "C")
        put_p = sum((r["est_premium"] or 0) for r in snaps if r["call_put"] == "P")
    finally:
        session.close()
    return {
        "underlying": _row(und),
        "net": {"call_premium": call_p, "put_premium": put_p, "put_call": (put_p / call_p) if call_p else None},
        "chain": [_row(r) for r in snaps],
        "signals": [_row(r) for r in live],
        "confirmation": [_row(r) for r in confirmed],
    }


@router.get("/occ/report")
def occ_report(session_date: date | None = None):
    session = get_session()
    try:
        if session_date is None:
            session_date = session.execute(text("SELECT MAX(session_date) FROM signals WHERE status <> 'live'")).scalar()
        rows = session.execute(
            text(
                """
                SELECT s.*, COALESCE(s.company_name, u.name) AS company_name
                FROM signals s LEFT JOIN underlyings u ON u.symbol = s.underlying
                WHERE s.session_date = :d AND s.status IN ('confirmed','faded','hedge')
                ORDER BY s.score DESC
                """
            ),
            {"d": session_date},
        ).mappings().all()
    finally:
        session.close()
    return {"session_date": session_date.isoformat() if session_date else None, "items": [_row(r) for r in rows]}


@router.get("/screeners")
def screeners():
    session = get_session()
    try:
        rows = session.execute(text("SELECT * FROM screeners ORDER BY name")).mappings().all()
    finally:
        session.close()
    return {"items": [_row(r) for r in rows]}


@router.get("/watchlist")
def get_watchlist():
    session = get_session()
    try:
        rows = session.execute(text("SELECT symbol FROM watchlist ORDER BY symbol")).scalars().all()
    finally:
        session.close()
    return {"symbols": rows}


@router.put("/watchlist")
def put_watchlist(body: WatchlistIn):
    session = get_session()
    try:
        session.execute(text("DELETE FROM watchlist"))
        for s in body.symbols:
            session.execute(text("INSERT INTO watchlist (symbol) VALUES (:s) ON CONFLICT DO NOTHING"), {"s": s.upper()})
        session.commit()
    finally:
        session.close()
    return {"symbols": [s.upper() for s in body.symbols]}


@router.get("/alerts/rules")
def list_rules():
    session = get_session()
    try:
        rows = session.execute(text("SELECT * FROM alert_rules ORDER BY name")).mappings().all()
    finally:
        session.close()
    return {"items": [_row(r) for r in rows]}


@router.post("/alerts/rules")
def create_rule(body: AlertRuleIn):
    session = get_session()
    rid = str(uuid.uuid4())
    try:
        session.execute(
            text(
                """
                INSERT INTO alert_rules (id, name, enabled, min_score, filters, channels, cooldown_seconds, digest_seconds)
                VALUES (CAST(:id AS uuid), :name, :en, :ms, CAST(:filters AS jsonb), CAST(:ch AS jsonb), :cd, :dg)
                """
            ),
            {
                "id": rid,
                "name": body.name,
                "en": body.enabled,
                "ms": body.min_score,
                "filters": json.dumps(body.filters),
                "ch": json.dumps(body.channels),
                "cd": body.cooldown_seconds,
                "dg": body.digest_seconds,
            },
        )
        session.commit()
    finally:
        session.close()
    return {"id": rid}


@router.put("/alerts/rules/{rule_id}")
def update_rule(rule_id: str, body: AlertRuleIn):
    session = get_session()
    try:
        session.execute(
            text(
                """
                UPDATE alert_rules SET name=:name, enabled=:en, min_score=:ms,
                    filters=CAST(:filters AS jsonb), channels=CAST(:ch AS jsonb),
                    cooldown_seconds=:cd, digest_seconds=:dg
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {
                "id": rule_id,
                "name": body.name,
                "en": body.enabled,
                "ms": body.min_score,
                "filters": json.dumps(body.filters),
                "ch": json.dumps(body.channels),
                "cd": body.cooldown_seconds,
                "dg": body.digest_seconds,
            },
        )
        session.commit()
    finally:
        session.close()
    return {"id": rule_id}


@router.delete("/alerts/rules/{rule_id}")
def delete_rule(rule_id: str):
    session = get_session()
    try:
        session.execute(text("DELETE FROM alert_rules WHERE id = CAST(:id AS uuid)"), {"id": rule_id})
        session.commit()
    finally:
        session.close()
    return {"ok": True}


@router.get("/alerts/events")
def alert_events(limit: int = 50):
    session = get_session()
    try:
        rows = session.execute(
            text("SELECT * FROM alert_events ORDER BY sent_at DESC LIMIT :n"), {"n": limit}
        ).mappings().all()
    finally:
        session.close()
    return {"items": [_row(r) for r in rows]}


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@router.get("/paper")
def paper_account():
    session = get_session()
    try:
        seed_account(session)
        return _jsonable(get_account(session))
    finally:
        session.close()


@router.post("/paper/reset")
def paper_reset(wipe_history: bool = False):
    session = get_session()
    try:
        return _jsonable(reset_account(session, wipe_history=wipe_history))
    finally:
        session.close()


@router.get("/paper/auto")
def paper_auto_get():
    session = get_session()
    try:
        return get_auto_settings(session)
    finally:
        session.close()


@router.put("/paper/auto")
def paper_auto_put(body: PaperAutoIn):
    session = get_session()
    try:
        return save_auto_settings(session, body.model_dump())
    finally:
        session.close()


@router.post("/paper/auto-run")
def paper_auto_run():
    session = get_session()
    try:
        seed_account(session)
        report = auto_trade(session)
        mark_positions(session)
        report["sold"] = auto_close(session)
        return _jsonable({**report, "account": get_account(session)})
    finally:
        session.close()


@router.get("/paper/analysis")
def paper_analysis():
    session = get_session()
    try:
        report = analyze_trades(session)
        if not report.get("grok"):
            report["grok"] = run_grok_review(session, report)
        return _jsonable(report)
    finally:
        session.close()


@router.post("/paper/analysis/grok")
def paper_analysis_grok():
    session = get_session()
    try:
        report = analyze_trades(session)
        review = run_grok_review(session, report)
        return _jsonable(review)
    finally:
        session.close()


def _briefing_text() -> tuple[str, str]:
    session = get_session()
    try:
        report = analyze_trades(session)
        outcomes = build_alert_outcomes(session)
        data = pack_dataset({**report, "alert_outcomes": outcomes}, outcomes)
        prompt = build_premium_prompt(data)
        stamp = datetime.now().strftime("%Y-%m-%d")
        return prompt, f"unusual-options-grok-briefing-{stamp}.txt"
    finally:
        session.close()


@router.get("/paper/analysis/briefing")
def paper_analysis_briefing():
    prompt, filename = _briefing_text()
    return {"prompt": prompt, "grok_url": "https://grok.x.com", "chars": len(prompt), "filename": filename}


@router.get("/paper/analysis/briefing.txt")
def paper_analysis_briefing_txt():
    prompt, filename = _briefing_text()
    return PlainTextResponse(
        prompt,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/paper/analysis/grok-import")
def paper_analysis_grok_import(body: GrokPasteIn):
    session = get_session()
    try:
        if not (body.text or "").strip():
            raise HTTPException(400, "Paste Grok's reply first")
        return _jsonable(import_pasted_review(session, body.text))
    finally:
        session.close()


@router.get("/settings/{key}")
def get_setting(key: str):
    session = get_session()
    try:
        row = session.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).scalar()
    finally:
        session.close()
    return {"key": key, "value": row or {}}


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingsIn):
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO settings (key, value) VALUES (:k, CAST(:v AS jsonb))
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """
            ),
            {"k": key, "v": json.dumps(body.value)},
        )
        session.commit()
    finally:
        session.close()
    return {"key": key, "value": body.value}
