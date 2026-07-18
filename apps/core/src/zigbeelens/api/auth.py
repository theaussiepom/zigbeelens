"""Multi-method authentication and pre-body CSRF enforcement."""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from fastapi.security import APIKeyCookie, APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from zigbeelens.app.context import get_context
from zigbeelens.config.api_token import parse_bearer_authorization_header
from zigbeelens.config.http_origin import InvalidHttpOrigin, canonicalize_http_origin
from zigbeelens.security.browser_sessions import (
    MAX_SESSION_COOKIE_BYTES,
    SESSION_COOKIE_NAME,
    BrowserSessionManager,
    SessionClaims,
)

logger = logging.getLogger(__name__)

AUTH_DETAIL = "Authentication required."
CSRF_DETAIL = "CSRF validation failed."
ORIGIN_DETAIL = "Browser origin validation failed."
SESSION_UNAVAILABLE_DETAIL = "Browser sessions are not configured."
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable."
CSRF_HEADER_NAME = "X-ZigbeeLens-CSRF-Token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Request-local cache for AuthIdentity only (never tokens, cookies, or CSRF).
_AUTH_IDENTITY_STATE_ATTR = "_zigbeelens_auth_identity"
_MUTATION_AUTHORIZED_ATTR = "_zigbeelens_mutation_authorized"
_ORIGIN_AUTHORIZED_ATTR = "_zigbeelens_origin_authorized"

# OpenAPI advertising helpers (custom parsing remains authoritative).
bearer_scheme = HTTPBearer(auto_error=False)
browser_session_scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)
csrf_header_scheme = APIKeyHeader(name=CSRF_HEADER_NAME, auto_error=False)

AuthMethod = Literal["bearer", "session", "trusted_local"]


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    auth_method: AuthMethod
    session_id: str | None = field(default=None, repr=False)
    session_expires_at: int | None = field(default=None, repr=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=AUTH_DETAIL,
        headers={
            "WWW-Authenticate": "Bearer",
            "Cache-Control": "no-store",
        },
    )


def _csrf_failed() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=CSRF_DETAIL,
        headers={"Cache-Control": "no-store"},
    )


def _origin_failed() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=ORIGIN_DETAIL,
        headers={"Cache-Control": "no-store"},
    )


def _sessions_unavailable() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=SESSION_UNAVAILABLE_DETAIL,
        headers={"Cache-Control": "no-store"},
    )


def _token_matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("ascii"), expected.encode("ascii"))


def _extract_bearer_token(request: Request) -> str | None:
    """Return Bearer credential, None if absent, or raise uniform 401."""
    values = request.headers.getlist("authorization")
    if len(values) > 1:
        raise _unauthorized()
    if not values:
        return None
    try:
        return parse_bearer_authorization_header(values[0])
    except ValueError:
        raise _unauthorized() from None


def extract_session_cookie_value(request: Request) -> str | None:
    """Return the session cookie value or None.

    Fail closed on duplicate/malformed ``zigbeelens_session`` occurrences.
    The authentication-cookie name must match exactly (no surrounding
    whitespace). Unrelated well-formed or malformed cookies are ignored.
    Does not use ``request.cookies`` (which can silently overwrite duplicates).
    """
    values: list[str] = []
    for header in request.headers.getlist("cookie"):
        if not header:
            continue
        for part in header.split(";"):
            segment = part.strip()
            if not segment:
                continue
            if "=" not in segment:
                if segment == SESSION_COOKIE_NAME:
                    raise ValueError("invalid session cookie")
                continue
            raw_name, _, value = segment.partition("=")
            # Exact Core-issued name grammar — do not silently canonicalise.
            if raw_name.strip() == SESSION_COOKIE_NAME and raw_name != SESSION_COOKIE_NAME:
                raise ValueError("invalid session cookie")
            if raw_name != SESSION_COOKIE_NAME:
                continue
            # Reject whitespace around the signed value and quoted forms.
            if value != value.strip() or not value:
                raise ValueError("invalid session cookie")
            if value.startswith('"') or value.endswith('"'):
                raise ValueError("invalid session cookie")
            if len(value.encode("utf-8")) > MAX_SESSION_COOKIE_BYTES:
                raise ValueError("invalid session cookie")
            values.append(value)
    if len(values) > 1:
        raise ValueError("duplicate session cookie")
    if not values:
        return None
    return values[0]


def _cached_auth_identity(request: Request) -> AuthIdentity | None:
    cached = getattr(request.state, _AUTH_IDENTITY_STATE_ATTR, None)
    if isinstance(cached, AuthIdentity):
        return cached
    return None


def _store_auth_identity(request: Request, identity: AuthIdentity) -> AuthIdentity:
    setattr(request.state, _AUTH_IDENTITY_STATE_ATTR, identity)
    return identity


def _session_manager() -> BrowserSessionManager:
    try:
        ctx = get_context()
    except RuntimeError:
        logger.error("Authenticator invoked before application context was ready")
        raise HTTPException(
            status_code=503,
            detail=SERVICE_UNAVAILABLE_DETAIL,
        ) from None
    manager = ctx.session_manager
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail=SERVICE_UNAVAILABLE_DETAIL,
        )
    return manager


def authenticate_request(request: Request) -> AuthIdentity:
    """Resolve bearer, session, or trusted-local identity for a protected route.

    Precedence:
    1. Authorization header present → bearer only (no cookie fallback).
    2. Else session cookie when browser sessions are enabled.
    3. Else trusted-local when no API token, otherwise 401.
    """
    cached = _cached_auth_identity(request)
    if cached is not None:
        return cached

    manager = _session_manager()
    ctx = get_context()
    expected = ctx.config.security.api_token

    auth_values = request.headers.getlist("authorization")
    if auth_values:
        provided = _extract_bearer_token(request)
        assert provided is not None
        if expected is None or not _token_matches(provided, expected.get_secret_value()):
            raise _unauthorized()
        return _store_auth_identity(request, AuthIdentity("bearer"))

    if expected is None:
        return _store_auth_identity(request, AuthIdentity("trusted_local"))

    if manager.enabled:
        try:
            cookie_value = extract_session_cookie_value(request)
        except ValueError:
            raise _unauthorized() from None
        if cookie_value is not None:
            try:
                claims = manager.load_session_cookie(cookie_value)
            except ValueError:
                raise _unauthorized() from None
            return _store_auth_identity(
                request,
                AuthIdentity(
                    "session",
                    session_id=claims.session_id,
                    session_expires_at=claims.expires_at,
                ),
            )

    raise _unauthorized()


def authenticate_bearer(request: Request) -> AuthIdentity:
    """Backward-compatible alias used by existing call sites and Track 4B tests."""
    return authenticate_request(request)


def require_bearer_bootstrap(request: Request) -> AuthIdentity:
    """Require the static API token; never accept a browser session as bootstrap."""
    cached = _cached_auth_identity(request)
    if cached is not None and cached.auth_method == "bearer":
        return cached

    manager = _session_manager()
    ctx = get_context()
    expected = ctx.config.security.api_token
    if expected is None:
        raise _unauthorized()

    provided = _extract_bearer_token(request)
    if provided is None:
        raise _unauthorized()
    if not _token_matches(provided, expected.get_secret_value()):
        raise _unauthorized()

    # Valid bearer presented — session support availability is a separate 409.
    _ = manager
    return _store_auth_identity(request, AuthIdentity("bearer"))


def request_same_origin(request: Request) -> str:
    """Return the request's effective same-origin from ASGI scope (no proxy trust)."""
    url = request.url
    scheme = (url.scheme or "http").lower()
    host = url.hostname
    if not host:
        raise InvalidHttpOrigin("missing hostname")
    # Starlette returns bare IPv6 hostnames; origins require brackets.
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = url.port
    if port is not None:
        candidate = f"{scheme}://{host}:{port}"
    else:
        candidate = f"{scheme}://{host}"
    return canonicalize_http_origin(candidate)


def _extract_single_origin_header(request: Request) -> str | None:
    """Return one Origin header value, or raise on duplicates/combined forms."""
    values = request.headers.getlist("origin")
    if not values:
        return None
    if len(values) > 1:
        raise _origin_failed()
    raw = values[0]
    if not raw or "," in raw:
        raise _origin_failed()
    return raw


def origin_is_allowed_for_browser(request: Request, origin_header: str) -> bool:
    """True when Origin matches same-origin or an exact cors_allowed_origins entry."""
    try:
        presented = canonicalize_http_origin(origin_header)
        same = request_same_origin(request)
    except InvalidHttpOrigin:
        return False
    if presented == same:
        return True
    allowed = get_context().config.security.cors_allowed_origins
    return presented in allowed


def enforce_session_mutation_origin(request: Request, identity: AuthIdentity) -> None:
    """Require an exact browser Origin for session-authenticated unsafe methods."""
    if getattr(request.state, _ORIGIN_AUTHORIZED_ATTR, False):
        return
    if identity.auth_method != "session":
        setattr(request.state, _ORIGIN_AUTHORIZED_ATTR, True)
        return
    if request.method.upper() not in _UNSAFE_METHODS:
        setattr(request.state, _ORIGIN_AUTHORIZED_ATTR, True)
        return

    try:
        raw = _extract_single_origin_header(request)
    except HTTPException:
        raise
    if raw is None:
        raise _origin_failed()
    if not origin_is_allowed_for_browser(request, raw):
        raise _origin_failed()
    setattr(request.state, _ORIGIN_AUTHORIZED_ATTR, True)


def enforce_mutation_csrf(request: Request, identity: AuthIdentity) -> None:
    """Require CSRF for session-authenticated mutations before body decoding."""
    if getattr(request.state, _MUTATION_AUTHORIZED_ATTR, False):
        return
    if identity.auth_method != "session":
        setattr(request.state, _MUTATION_AUTHORIZED_ATTR, True)
        return

    manager = _session_manager()
    values = request.headers.getlist(CSRF_HEADER_NAME)
    if len(values) != 1:
        raise _csrf_failed()
    token = values[0]
    if not token or "," in token:
        raise _csrf_failed()
    if identity.session_id is None:
        raise _csrf_failed()
    try:
        manager.validate_csrf_token(token, session_id=identity.session_id)
    except ValueError:
        raise _csrf_failed() from None
    setattr(request.state, _MUTATION_AUTHORIZED_ATTR, True)


def enforce_mutation_browser_policy(request: Request, identity: AuthIdentity) -> None:
    """Session mutations: Origin then CSRF, both before body decoding."""
    enforce_session_mutation_origin(request, identity)
    enforce_mutation_csrf(request, identity)


def enforce_session_bootstrap_origin(request: Request) -> None:
    """When Origin is present on bearer session login, require an allowed origin."""
    try:
        raw = _extract_single_origin_header(request)
    except HTTPException:
        raise
    if raw is None:
        return
    if not origin_is_allowed_for_browser(request, raw):
        raise _origin_failed()


class ReadAccessPreflightRoute(APIRoute):
    """Authenticate before FastAPI reads or JSON-decodes the request body."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def protected_route_handler(request: Request) -> Response:
            authenticate_request(request)
            return await original(request)

        return protected_route_handler


class MutationAccessPreflightRoute(APIRoute):
    """Authenticate and enforce Origin+CSRF before FastAPI body decoding."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def protected_route_handler(request: Request) -> Response:
            identity = authenticate_request(request)
            enforce_mutation_browser_policy(request, identity)
            return await original(request)

        return protected_route_handler


class BearerBootstrapPreflightRoute(APIRoute):
    """Require static bearer bootstrap before FastAPI body decoding."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def protected_route_handler(request: Request) -> Response:
            require_bearer_bootstrap(request)
            enforce_session_bootstrap_origin(request)
            return await original(request)

        return protected_route_handler


# Compatibility alias for older imports/tests.
BearerPreflightRoute = ReadAccessPreflightRoute


async def require_read_access(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    _session: Annotated[str | None, Depends(browser_session_scheme)] = None,
) -> AuthIdentity:
    """Require bearer or browser session when authentication is configured."""
    return authenticate_request(request)


async def require_mutation_access(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    _session: Annotated[str | None, Depends(browser_session_scheme)] = None,
    _csrf: Annotated[str | None, Depends(csrf_header_scheme)] = None,
) -> AuthIdentity:
    """Require bearer, or session plus Origin and CSRF, for mutations."""
    identity = authenticate_request(request)
    enforce_mutation_browser_policy(request, identity)
    return identity


async def require_bearer_bootstrap_access(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> AuthIdentity:
    """Require static bearer for session login; OpenAPI advertises Bearer only."""
    identity = require_bearer_bootstrap(request)
    enforce_session_bootstrap_origin(request)
    return identity


def try_load_session_claims(request: Request) -> SessionClaims | None:
    """Best-effort session load for public status (invalid → None)."""
    manager = _session_manager()
    if not manager.enabled:
        return None
    try:
        cookie_value = extract_session_cookie_value(request)
    except ValueError:
        return None
    if cookie_value is None:
        return None
    try:
        return manager.load_session_cookie(cookie_value)
    except ValueError:
        return None


def sessions_unavailable_error() -> HTTPException:
    return _sessions_unavailable()
