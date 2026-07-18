"""Explicit bearer authentication and route access dependencies."""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from zigbeelens.app.context import get_context

logger = logging.getLogger(__name__)

AUTH_DETAIL = "Authentication required."
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable."

# Declared for OpenAPI HTTP Bearer advertising; parsing is custom (stricter).
bearer_scheme = HTTPBearer(auto_error=False)

AuthMethod = Literal["bearer", "trusted_local"]


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    auth_method: AuthMethod


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=AUTH_DETAIL,
        headers={
            "WWW-Authenticate": "Bearer",
            "Cache-Control": "no-store",
        },
    )


def _token_matches(provided: str, expected: str) -> bool:
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


def _extract_bearer_token(request: Request) -> str | None:
    """Return the Bearer credential, None if absent, or raise uniform 401."""
    values = request.headers.getlist("authorization")
    if len(values) > 1:
        raise _unauthorized()
    if not values:
        return None

    raw = values[0]
    if "," in raw:
        # Reject comma-combined credentials / multi-challenge headers.
        raise _unauthorized()

    parts = raw.split(None, 1)
    if len(parts) != 2:
        raise _unauthorized()

    scheme, credential = parts
    if scheme.lower() != "bearer":
        raise _unauthorized()
    if not credential or credential != credential.strip():
        raise _unauthorized()
    if any(ch.isspace() for ch in credential):
        raise _unauthorized()
    return credential


def authenticate_bearer(request: Request) -> AuthIdentity:
    """Resolve trusted-local open mode or require a matching Bearer token."""
    try:
        ctx = get_context()
    except RuntimeError:
        logger.error("Bearer authenticator invoked before application context was ready")
        raise HTTPException(
            status_code=503,
            detail=SERVICE_UNAVAILABLE_DETAIL,
        ) from None

    expected = ctx.config.security.api_token
    if expected is None:
        request.state.auth_method = "trusted_local"
        return AuthIdentity("trusted_local")

    provided = _extract_bearer_token(request)
    if provided is None:
        raise _unauthorized()

    if not _token_matches(provided, expected.get_secret_value()):
        raise _unauthorized()

    request.state.auth_method = "bearer"
    return AuthIdentity("bearer")


async def require_read_access(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> AuthIdentity:
    """Require bearer when a token is configured (protected reads / SSE / downloads)."""
    return authenticate_bearer(request)


async def require_mutation_access(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> AuthIdentity:
    """Require bearer when a token is configured (mutations; CSRF seam for later)."""
    return authenticate_bearer(request)
