"""Exact Home Assistant Supervisor ingress peer trust and identity.

Trust is limited to exact configured ASGI peer IPs. Forwarded headers are never
consulted. Raw ``X-Remote-User-*`` headers are stripped before downstream code.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from zigbeelens.config.api_token import parse_bearer_authorization_header
from zigbeelens.config.ingress_trust import normalize_ha_user_id
from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import SecurityMode

AUTH_DETAIL = "Authentication required."

# Private request-local key (scope state). Not a public API.
INGRESS_IDENTITY_SCOPE_KEY = "_zigbeelens_ha_ingress_identity"

# Keep in sync with zigbeelens.api.auth._AUTH_IDENTITY_STATE_ATTR
_AUTH_IDENTITY_STATE_ATTR = "_zigbeelens_auth_identity"

_REMOTE_USER_HEADER_NAMES = frozenset(
    {
        b"x-remote-user-id",
        b"x-remote-user-name",
        b"x-remote-user-display-name",
    }
)


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


def _try_validate_bearer(scope: Scope, config: AppConfig) -> bool:
    """Return True when Authorization is a correct bearer for this config."""
    expected = config.security.api_token
    if expected is None:
        return False
    values = _authorization_values(scope)
    if len(values) != 1:
        return False
    try:
        provided = parse_bearer_authorization_header(values[0])
    except ValueError:
        return False
    return hmac.compare_digest(
        provided.encode("ascii"),
        expected.get_secret_value().encode("ascii"),
    )


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

        if trusted:
            id_values = _header_values(scope, b"x-remote-user-id")
            cleaned = _strip_remote_user_headers(scope)
            state = cleaned.setdefault("state", {})
            if len(id_values) > 1:
                await _send_json_401(send)
                return
            if len(id_values) == 1:
                user_id = normalize_ha_user_id(id_values[0])
                if user_id is None:
                    await _send_json_401(send)
                    return
                state[INGRESS_IDENTITY_SCOPE_KEY] = HomeAssistantIngressIdentity(
                    user_id=user_id
                )
            await self.app(cleaned, receive, send)
            return

        # Untrusted peer: always strip identity headers.
        cleaned = _strip_remote_user_headers(scope)
        state = cleaned.setdefault("state", {})

        if _path_is_loopback_healthz(path, method) and peer in {"127.0.0.1", "::1"}:
            await self.app(cleaned, receive, send)
            return

        if not self._proxy_only:
            await self.app(cleaned, receive, send)
            return

        # proxy_only: only public machine probes, public session status, or valid bearer.
        if _path_is_public_machine_probe(path, method) or _path_is_public_session_status(
            path, method
        ):
            await self.app(cleaned, receive, send)
            return

        auth_values = _authorization_values(cleaned)
        if auth_values:
            if _try_validate_bearer(cleaned, self._config):
                from zigbeelens.api.auth import AuthIdentity

                state[_AUTH_IDENTITY_STATE_ATTR] = AuthIdentity("bearer")
                await self.app(cleaned, receive, send)
                return
            await _send_json_401(send)
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
