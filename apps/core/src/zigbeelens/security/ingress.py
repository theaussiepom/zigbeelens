"""Exact Home Assistant Supervisor ingress peer trust and identity.

Trust is limited to exact configured ASGI peer IPs. Forwarded headers are never
consulted. Raw ``X-Remote-User-*`` headers are stripped before downstream code.

Authorization (Bearer) is evaluated before ingress-identity parsing whenever the
header is present.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from starlette.types import ASGIApp, Receive, Scope, Send

from zigbeelens.config.api_token import parse_bearer_authorization_header
from zigbeelens.config.ingress_trust import normalize_ha_user_id
from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import SecurityMode

AUTH_DETAIL = "Authentication required."

# Private request-local keys (scope state). Not a public API.
INGRESS_IDENTITY_SCOPE_KEY = "_zigbeelens_ha_ingress_identity"
INGRESS_PEER_SCOPE_KEY = "_zigbeelens_ha_ingress_peer"

# Keep in sync with zigbeelens.api.auth._AUTH_IDENTITY_STATE_ATTR
_AUTH_IDENTITY_STATE_ATTR = "_zigbeelens_auth_identity"

_REMOTE_USER_HEADER_NAMES = frozenset(
    {
        b"x-remote-user-id",
        b"x-remote-user-name",
        b"x-remote-user-display-name",
    }
)

_DOCS_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})


class IngressPeerKind(str, Enum):
    """Request-local peer classification (never stores the peer IP)."""

    untrusted = "untrusted"
    trusted_without_identity = "trusted_without_identity"
    trusted_with_identity = "trusted_with_identity"


@dataclass(frozen=True, slots=True)
class HomeAssistantIngressIdentity:
    """Request-local HA ingress identity. Never logged or projected."""

    user_id: str = field(repr=False)

    def __repr__(self) -> str:
        return "HomeAssistantIngressIdentity(user_id=<redacted>)"


def peer_ip_from_scope(scope: Scope) -> str | None:
    """Return the immediate ASGI client IP, or None when unavailable."""
    client = scope.get("client")
    if not client or not isinstance(client, (list, tuple)) or not client[0]:
        return None
    host = client[0]
    if not isinstance(host, str):
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def path_allows_direct_bearer(path: str) -> bool:
    """True for reviewed machine API/docs paths (not static UI / SPA)."""
    if path in _DOCS_PATHS:
        return True
    if path == "/api" or path.startswith("/api/"):
        return True
    return False


def _header_values(scope: Scope, name: bytes) -> list[str]:
    values: list[str] = []
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            try:
                values.append(value.decode("latin-1"))
            except Exception:
                values.append("")
    return values


def _strip_remote_user_headers(scope: Scope) -> Scope:
    headers = [
        (k, v)
        for k, v in (scope.get("headers") or [])
        if k.lower() not in _REMOTE_USER_HEADER_NAMES
    ]
    new_scope = dict(scope)
    new_scope["headers"] = headers
    return new_scope


def _path_is_public_machine_probe(path: str, method: str) -> bool:
    if method not in {"GET", "HEAD"}:
        return False
    return path in {
        "/healthz",
        "/api/version",
        "/api/v1/version",
    }


def _path_is_public_session_status(path: str, method: str) -> bool:
    if method not in {"GET", "HEAD"}:
        return False
    return path in {"/api/auth/session", "/api/v1/auth/session"}


def _path_is_loopback_healthz(path: str, method: str) -> bool:
    return method in {"GET", "HEAD"} and path == "/healthz"


def _authorization_values(scope: Scope) -> list[str]:
    return _header_values(scope, b"authorization")


def _validate_bearer_when_present(
    scope: Scope, config: AppConfig
) -> Literal["absent", "valid", "invalid"]:
    """Classify Authorization without storing the token."""
    values = _authorization_values(scope)
    if not values:
        return "absent"
    expected = config.security.api_token
    if expected is None or len(values) != 1:
        return "invalid"
    try:
        provided = parse_bearer_authorization_header(values[0])
    except ValueError:
        return "invalid"
    if hmac.compare_digest(
        provided.encode("ascii"),
        expected.get_secret_value().encode("ascii"),
    ):
        return "valid"
    return "invalid"


async def _send_json_401(send: Send) -> None:
    body = json.dumps({"detail": AUTH_DETAIL}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _cache_bearer_identity(state: dict[str, Any]) -> None:
    from zigbeelens.api.auth import AuthIdentity

    state[_AUTH_IDENTITY_STATE_ATTR] = AuthIdentity("bearer")


def _set_peer_kind(state: dict[str, Any], kind: IngressPeerKind) -> None:
    state[INGRESS_PEER_SCOPE_KEY] = kind


class HomeAssistantIngressBoundaryMiddleware:
    """Exact-peer Home Assistant ingress boundary (pure ASGI, no body buffering)."""

    def __init__(self, app: ASGIApp, *, config: AppConfig) -> None:
        self.app = app
        self._config = config
        self._mode = config.security.mode
        self._trusted = frozenset(config.security.ingress_trusted_proxies)
        self._proxy_only = bool(config.security.ingress_proxy_only)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._mode is not SecurityMode.home_assistant_ingress:
            await self.app(_strip_remote_user_headers(scope), receive, send)
            return

        peer = peer_ip_from_scope(scope)
        path = scope.get("path") or ""
        method = (scope.get("method") or "GET").upper()
        trusted = peer is not None and peer in self._trusted

        # Authorization present → bearer only; never parse ingress identity.
        bearer = _validate_bearer_when_present(scope, self._config)
        if bearer != "absent":
            cleaned = _strip_remote_user_headers(scope)
            state = cleaned.setdefault("state", {})
            _set_peer_kind(
                state,
                IngressPeerKind.trusted_without_identity
                if trusted
                else IngressPeerKind.untrusted,
            )
            if bearer == "invalid":
                await _send_json_401(send)
                return
            # Valid bearer: never fall back to ingress identity.
            # Proxy-only untrusted peers may use bearer for API/docs/public probes
            # only — not static UI / SPA catch-all.
            allow_valid_bearer = (
                trusted
                or path_allows_direct_bearer(path)
                or _path_is_public_machine_probe(path, method)
                or _path_is_public_session_status(path, method)
                or not self._proxy_only
            )
            if not allow_valid_bearer:
                await _send_json_401(send)
                return
            _cache_bearer_identity(state)
            await self.app(cleaned, receive, send)
            return

        cleaned = _strip_remote_user_headers(scope)
        state = cleaned.setdefault("state", {})

        if trusted:
            # Re-read identity from original scope (cleaned already stripped).
            id_values = _header_values(scope, b"x-remote-user-id")
            if len(id_values) > 1:
                _set_peer_kind(state, IngressPeerKind.trusted_without_identity)
                await _send_json_401(send)
                return
            if len(id_values) == 1:
                user_id = normalize_ha_user_id(id_values[0])
                if user_id is None:
                    _set_peer_kind(state, IngressPeerKind.trusted_without_identity)
                    await _send_json_401(send)
                    return
                state[INGRESS_IDENTITY_SCOPE_KEY] = HomeAssistantIngressIdentity(
                    user_id=user_id
                )
                _set_peer_kind(state, IngressPeerKind.trusted_with_identity)
            else:
                _set_peer_kind(state, IngressPeerKind.trusted_without_identity)
            await self.app(cleaned, receive, send)
            return

        # Untrusted peer: headers already stripped; no ingress identity.
        _set_peer_kind(state, IngressPeerKind.untrusted)

        if _path_is_loopback_healthz(path, method) and peer in {"127.0.0.1", "::1"}:
            await self.app(cleaned, receive, send)
            return

        if not self._proxy_only:
            await self.app(cleaned, receive, send)
            return

        # proxy_only: public machine probes / session status only (no static UI).
        if _path_is_public_machine_probe(path, method) or _path_is_public_session_status(
            path, method
        ):
            await self.app(cleaned, receive, send)
            return

        await _send_json_401(send)


def get_ingress_identity_from_request_state(state: Any) -> HomeAssistantIngressIdentity | None:
    identity = getattr(state, INGRESS_IDENTITY_SCOPE_KEY, None)
    if isinstance(identity, HomeAssistantIngressIdentity):
        return identity
    if isinstance(state, dict):
        value = state.get(INGRESS_IDENTITY_SCOPE_KEY)
        if isinstance(value, HomeAssistantIngressIdentity):
            return value
    return None


def get_ingress_peer_kind(state: Any) -> IngressPeerKind | None:
    value = getattr(state, INGRESS_PEER_SCOPE_KEY, None)
    if isinstance(value, IngressPeerKind):
        return value
    if isinstance(state, dict):
        value = state.get(INGRESS_PEER_SCOPE_KEY)
        if isinstance(value, IngressPeerKind):
            return value
    return None


def trusted_ingress_peer_without_identity(state: Any) -> bool:
    return get_ingress_peer_kind(state) is IngressPeerKind.trusted_without_identity
