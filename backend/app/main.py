from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db import init_db
from app.desk_auth import accept_desk_ws, desk_http_guard
from app.jobs.paper import seed_account
from app.db import get_session
from app.redisutil import CHANNEL_SIGNALS, get_redis

settings = get_settings()
logging.basicConfig(level=settings.log_level)
app = FastAPI(title="Unusual Options Bot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _desk_guard(request: Request, call_next):
    return await desk_http_guard(request, call_next, settings.desk_token)


app.include_router(router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    session = get_session()
    try:
        seed_account(session)
    finally:
        session.close()


@app.get("/")
def root():
    return {"name": "unusual-options-bot", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"ok": True, "mode": "paper"}


@app.websocket("/ws")
async def ws_feed(ws: WebSocket):
    if not await accept_desk_ws(ws, settings.desk_token):
        return
    pubsub = get_redis().pubsub()
    pubsub.subscribe(CHANNEL_SIGNALS)
    try:
        await ws.send_json({"type": "hello", "mode": get_settings().data_mode})
        while True:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                data = msg["data"]
                payload = json.loads(data) if isinstance(data, str) else data
                await ws.send_json({"type": "signal", "signal": payload})
            else:
                await asyncio.sleep(0.15)
    except WebSocketDisconnect:
        pass
    finally:
        pubsub.close()
