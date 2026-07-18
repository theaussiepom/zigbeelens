"""HttpOnly session-cookie set/clear helpers with matched attributes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Response
from starlette.responses import Response as StarletteResponse

from zigbeelens.security.browser_sessions import SESSION_COOKIE_NAME, BrowserSessionManager

NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


def apply_no_store(response: Response | StarletteResponse) -> None:
    for key, value in NO_STORE_HEADERS.items():
        response.headers[key] = value


def set_session_cookie(
    response: Response | StarletteResponse,
    manager: BrowserSessionManager,
    cookie_value: str,
    *,
    expires_at: int,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=manager.ttl_seconds,
        expires=datetime.fromtimestamp(expires_at, tz=timezone.utc),
        path="/",
        secure=manager.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    apply_no_store(response)


def clear_session_cookie(
    response: Response | StarletteResponse,
    manager: BrowserSessionManager,
) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=manager.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    apply_no_store(response)
