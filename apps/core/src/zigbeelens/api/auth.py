"""Optional API key guard for mutating Core routes."""

from __future__ import annotations

import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_MUTATING_PREFIXES = (
    "/api/reports",
    "/api/v1/reports",
    "/api/topology",
    "/api/v1/topology",
    "/api/enrichment",
    "/api/v1/enrichment",
)


def _configured_api_key() -> str | None:
    value = os.environ.get("ZIGBEELENS_API_KEY", "").strip()
    return value or None


def _requires_api_key(request: Request) -> bool:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return False
    path = request.url.path
    return any(path.startswith(prefix) for prefix in _MUTATING_PREFIXES)


class OptionalApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests when ZIGBEELENS_API_KEY is set and header missing."""

    async def dispatch(self, request: Request, call_next):
        api_key = _configured_api_key()
        if api_key and _requires_api_key(request):
            provided = request.headers.get("X-ZigbeeLens-Api-Key", "").strip()
            if provided != api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing ZigbeeLens API key."},
                )
        return await call_next(request)
