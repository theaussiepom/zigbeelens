"""Optional API key guard for mutating Core routes."""

from __future__ import annotations

import hmac
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from zigbeelens.app.context import get_context

logger = logging.getLogger(__name__)

_MUTATING_PREFIXES = (
    "/api/reports",
    "/api/v1/reports",
    "/api/topology",
    "/api/v1/topology",
    "/api/enrichment",
    "/api/v1/enrichment",
)


def _requires_api_key(request: Request) -> bool:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return False
    path = request.url.path
    return any(path.startswith(prefix) for prefix in _MUTATING_PREFIXES)


def _header_matches_token(provided: str, expected: str) -> bool:
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


class OptionalApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests when a resolved api_token is configured."""

    async def dispatch(self, request: Request, call_next):
        if not _requires_api_key(request):
            return await call_next(request)

        try:
            ctx = get_context()
        except RuntimeError:
            logger.error("API key guard invoked before application context was ready")
            return JSONResponse(
                status_code=503,
                content={"detail": "Application context is not available."},
            )

        token = ctx.config.security.api_token
        if token is None:
            return await call_next(request)

        provided = request.headers.get("X-ZigbeeLens-Api-Key", "")
        expected = token.get_secret_value()
        if not _header_matches_token(provided, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing ZigbeeLens API key."},
            )
        return await call_next(request)
