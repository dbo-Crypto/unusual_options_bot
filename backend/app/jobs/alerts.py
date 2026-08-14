from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _matches(signal: dict, rule: dict) -> bool:
    if signal.get("score", 0) < (rule.get("min_score") or 0):
        return False
    filters = rule.get("filters") or {}
    if filters.get("call_put") and signal.get("call_put") != filters["call_put"]:
        return False
    tags = set(signal.get("tags") or [])
    if filters.get("tags") and not set(filters["tags"]).issubset(tags):
        return False
    if filters.get("exclude_tags") and set(filters["exclude_tags"]) & tags:
        return False
    watch = filters.get("watchlist")
    if watch and signal.get("underlying") not in watch:
        return False
    return True


def dispatch_alerts(session: Session, signals: list[dict]) -> int:
    rules = session.execute(text("SELECT * FROM alert_rules WHERE enabled = TRUE")).mappings().all()
    sent = 0
    for rule in rules:
        filters = rule["filters"] if isinstance(rule["filters"], dict) else json.loads(rule["filters"] or "{}")
        channels = rule["channels"] if isinstance(rule["channels"], list) else json.loads(rule["channels"] or "[]")
        rule_d = {**dict(rule), "filters": filters, "channels": channels}
        for sig in signals:
            if not _matches(sig, rule_d):
                continue
            recent = session.execute(
                text(
                    """
                    SELECT 1 FROM alert_events
                    WHERE rule_id = :rid AND payload->>'occ_symbol' = :occ
                      AND sent_at > :since
                    LIMIT 1
                    """
                ),
                {
                    "rid": rule["id"],
                    "occ": sig.get("occ_symbol"),
                    "since": datetime.now(timezone.utc) - timedelta(seconds=rule["cooldown_seconds"] or 1800),
                },
            ).first()
            if recent:
                continue
            for channel in channels:
                ok = _send(channel, sig, rule_d)
                session.execute(
                    text(
                        """
                        INSERT INTO alert_events (id, rule_id, signal_id, sent_at, channel, payload, status)
                        VALUES (:id, :rid, CAST(:sid AS uuid), NOW(), :ch, CAST(:payload AS jsonb), :st)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "rid": rule["id"],
                        "sid": sig.get("id"),
                        "ch": channel.get("type", "webhook"),
                        "payload": json.dumps(sig, default=str),
                        "st": "sent" if ok else "error",
                    },
                )
                sent += int(ok)
    session.commit()
    return sent


def _send(channel: dict, sig: dict, rule: dict) -> bool:
    url = channel.get("url")
    if not url:
        return False
    text_msg = (
        f"**{sig.get('underlying')}** {sig.get('expiry')} {sig.get('strike')}{sig.get('call_put')} "
        f"score {sig.get('score')} · vol {sig.get('volume')} · OI {sig.get('open_interest')} · "
        f"vol/OI {sig.get('vol_oi')} · est ${sig.get('est_premium') or 0:,.0f}\n"
        f"{', '.join(r.get('text','') for r in (sig.get('reasons') or [])[:3])}"
    )
    try:
        if channel.get("type") == "discord":
            httpx.post(url, json={"content": text_msg}, timeout=10).raise_for_status()
        else:
            httpx.post(url, json={"text": text_msg, "signal": sig, "rule": rule.get("name")}, timeout=10).raise_for_status()
        return True
    except Exception as exc:
        log.warning("alert send failed: %s", exc)
        return False
