import json
from typing import Any

import redis

from app.config import get_settings

CHANNEL_SIGNALS = "uoa.signals"
CHANNEL_HEALTH = "uoa.health"

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def publish(channel: str, payload: dict[str, Any]) -> None:
    get_redis().publish(channel, json.dumps(payload, default=str))


def cache_set(key: str, payload: Any, ttl: int = 300) -> None:
    get_redis().setex(key, ttl, json.dumps(payload, default=str))


def cache_get(key: str) -> Any | None:
    raw = get_redis().get(key)
    if not raw:
        return None
    return json.loads(raw)
