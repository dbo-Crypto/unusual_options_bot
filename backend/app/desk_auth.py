from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse


def extract_token(request: Request) -> str:
    header = request.headers.get("x-desk-token", "").strip()
    if header:
        return header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.query_params.get("token") or "").strip()


def assert_desk_token(expected: str, provided: str) -> None:
    if not expected:
        return
    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def desk_http_guard(request: Request, call_next, expected: str):
    if request.url.path.startswith("/api"):
        try:
            assert_desk_token(expected, extract_token(request))
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


async def accept_desk_ws(ws: WebSocket, expected: str) -> bool:
    if not expected:
        await ws.accept()
        return True
    token = (ws.query_params.get("token") or "").strip()
    header = (ws.headers.get("x-desk-token") or "").strip()
    if token != expected and header != expected:
        await ws.close(code=4401)
        return False
    await ws.accept()
    return True
