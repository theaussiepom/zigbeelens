"""Signed browser-session cookies and CSRF tokens (integrity, not confidentiality)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from itsdangerous import BadData, URLSafeSerializer
from pydantic import SecretStr

from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import (
    SESSION_COOKIE_NAME,
    browser_sessions_enabled,
    is_loopback_bind,
)
SESSION_PAYLOAD_VERSION = 1
CSRF_PAYLOAD_VERSION = 1
SESSION_SIGNING_SALT = "zigbeelens-browser-session-v1"
CSRF_SIGNING_SALT = "zigbeelens-csrf-token-v1"
MAX_SESSION_COOKIE_BYTES = 4096
MAX_CSRF_TOKEN_BYTES = 4096
MAX_FUTURE_CLOCK_SKEW_SECONDS = 60
SESSION_ID_BYTES = 16

_SIGNER_KWARGS: Mapping[str, Any] = MappingProxyType(
    {
        "key_derivation": "hmac",
        "digest_method": hashlib.sha256,
    }
)

Clock = Callable[[], float]

__all__ = [
    "SESSION_COOKIE_NAME",
    "BrowserSessionManager",
    "SessionClaims",
    "browser_sessions_enabled",
    "resolve_session_cookie_secure",
]


def _new_serializer(secret: str, *, salt: str) -> URLSafeSerializer:
    """Build a URLSafeSerializer with the frozen HMAC-SHA256 signer policy."""
    return URLSafeSerializer(
        secret,
        salt=salt,
        signer_kwargs=_SIGNER_KWARGS,
    )


def resolve_session_cookie_secure(config: AppConfig) -> bool:
    """Resolve the Secure cookie attribute from config and bind address."""
    explicit = config.security.session_cookie_secure
    if explicit is True:
        return True
    if explicit is False:
        return False
    return not is_loopback_bind(config.server.host)


def _api_credential_binding(api_token: str, session_secret: str) -> str:
    """Opaque keyed binding so api_token rotation invalidates sessions."""
    return hmac.new(
        session_secret.encode("utf-8"),
        api_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _is_strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_session_id(value: str) -> bool:
    if len(value) != SESSION_ID_BYTES * 2:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _safe_signed_load(serializer: URLSafeSerializer, value: str) -> Any:
    """Load signed data; translate every BadData failure to a safe ValueError."""
    try:
        return serializer.loads(value)
    except BadData:
        raise ValueError("invalid signed data") from None


@dataclass(frozen=True, slots=True)
class SessionClaims:
    version: int
    session_id: str = field(repr=False)
    issued_at: int
    expires_at: int
    api_credential_binding: str = field(repr=False)

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "api_credential_binding": self.api_credential_binding,
        }

    @classmethod
    def from_payload(cls, payload: object) -> SessionClaims:
        if not isinstance(payload, dict):
            raise ValueError("invalid session payload")
        if set(payload) != {
            "version",
            "session_id",
            "issued_at",
            "expires_at",
            "api_credential_binding",
        }:
            raise ValueError("invalid session payload")
        version = payload["version"]
        session_id = payload["session_id"]
        issued_at = payload["issued_at"]
        expires_at = payload["expires_at"]
        binding = payload["api_credential_binding"]
        if not _is_strict_int(version) or version != SESSION_PAYLOAD_VERSION:
            raise ValueError("invalid session payload")
        if not isinstance(session_id, str) or not _valid_session_id(session_id):
            raise ValueError("invalid session payload")
        if not _is_strict_int(issued_at):
            raise ValueError("invalid session payload")
        if not _is_strict_int(expires_at):
            raise ValueError("invalid session payload")
        if not isinstance(binding, str) or len(binding) != 64:
            raise ValueError("invalid session payload")
        try:
            bytes.fromhex(binding)
        except ValueError:
            raise ValueError("invalid session payload") from None
        return cls(
            version=version,
            session_id=session_id,
            issued_at=issued_at,
            expires_at=expires_at,
            api_credential_binding=binding,
        )


@dataclass(frozen=True, slots=True)
class BrowserSessionManager:
    """Process-local signed session/CSRF service built from effective AppConfig."""

    enabled: bool
    ttl_seconds: int
    cookie_secure: bool
    _session_serializer: URLSafeSerializer | None = field(repr=False)
    _csrf_serializer: URLSafeSerializer | None = field(repr=False)
    _api_credential_binding: str | None = field(repr=False)
    _clock: Clock = field(repr=False)

    def __repr__(self) -> str:
        return (
            "BrowserSessionManager("
            f"enabled={self.enabled!r}, "
            f"ttl_seconds={self.ttl_seconds!r}, "
            f"cookie_secure={self.cookie_secure!r})"
        )

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        *,
        clock: Clock | None = None,
    ) -> BrowserSessionManager:
        enabled = browser_sessions_enabled(config)
        api_token = (
            config.security.api_token.get_secret_value()
            if config.security.api_token is not None
            else None
        )
        session_secret = (
            config.security.session_secret.get_secret_value()
            if config.security.session_secret is not None
            else None
        )
        session_serializer = None
        csrf_serializer = None
        binding = None
        if enabled and session_secret is not None and api_token is not None:
            session_serializer = _new_serializer(
                session_secret,
                salt=SESSION_SIGNING_SALT,
            )
            csrf_serializer = _new_serializer(
                session_secret,
                salt=CSRF_SIGNING_SALT,
            )
            binding = _api_credential_binding(api_token, session_secret)
        return cls(
            enabled=enabled,
            ttl_seconds=config.security.session_ttl_seconds,
            cookie_secure=resolve_session_cookie_secure(config),
            _session_serializer=session_serializer,
            _csrf_serializer=csrf_serializer,
            _api_credential_binding=binding,
            _clock=clock or time.time,
        )

    def now(self) -> float:
        return float(self._clock())

    def now_ts(self) -> int:
        return int(self.now())

    def issue_session(self) -> tuple[SessionClaims, str, str]:
        """Return claims, signed cookie value, and signed CSRF token."""
        if (
            not self.enabled
            or self._session_serializer is None
            or self._csrf_serializer is None
            or self._api_credential_binding is None
        ):
            raise RuntimeError("browser sessions are not configured")

        issued_at = self.now_ts()
        expires_at = issued_at + self.ttl_seconds
        claims = SessionClaims(
            version=SESSION_PAYLOAD_VERSION,
            session_id=secrets.token_hex(SESSION_ID_BYTES),
            issued_at=issued_at,
            expires_at=expires_at,
            api_credential_binding=self._api_credential_binding,
        )
        cookie_value = self._session_serializer.dumps(claims.to_payload())
        if len(cookie_value.encode("utf-8")) > MAX_SESSION_COOKIE_BYTES:
            raise RuntimeError("session cookie exceeded maximum size")
        csrf_token = self.issue_csrf_token(claims.session_id)
        return claims, cookie_value, csrf_token

    def issue_csrf_token(self, session_id: str) -> str:
        if self._csrf_serializer is None:
            raise RuntimeError("browser sessions are not configured")
        if not _valid_session_id(session_id):
            raise RuntimeError("browser sessions are not configured")
        token = self._csrf_serializer.dumps(
            {"version": CSRF_PAYLOAD_VERSION, "session_id": session_id}
        )
        if len(token.encode("utf-8")) > MAX_CSRF_TOKEN_BYTES:
            raise RuntimeError("csrf token exceeded maximum size")
        return token

    def load_session_cookie(self, cookie_value: str) -> SessionClaims:
        """Validate and return claims, or raise ValueError without echoing input."""
        if not self.enabled or self._session_serializer is None:
            raise ValueError("invalid session")
        if cookie_value != cookie_value.strip():
            raise ValueError("invalid session")
        if len(cookie_value.encode("utf-8")) > MAX_SESSION_COOKIE_BYTES:
            raise ValueError("invalid session")
        try:
            payload = _safe_signed_load(self._session_serializer, cookie_value)
            claims = SessionClaims.from_payload(payload)
            self._validate_claims(claims)
        except ValueError:
            raise ValueError("invalid session") from None
        return claims

    def _validate_claims(self, claims: SessionClaims) -> None:
        if self._api_credential_binding is None:
            raise ValueError("invalid session")
        now = self.now_ts()
        if claims.issued_at > now + MAX_FUTURE_CLOCK_SKEW_SECONDS:
            raise ValueError("invalid session")
        if claims.expires_at <= claims.issued_at:
            raise ValueError("invalid session")
        if claims.expires_at - claims.issued_at > self.ttl_seconds:
            raise ValueError("invalid session")
        if claims.expires_at <= now:
            raise ValueError("invalid session")
        if not hmac.compare_digest(
            claims.api_credential_binding,
            self._api_credential_binding,
        ):
            raise ValueError("invalid session")

    def validate_csrf_token(self, token: str, *, session_id: str) -> None:
        if not self.enabled or self._csrf_serializer is None:
            raise ValueError("invalid csrf")
        if token != token.strip():
            raise ValueError("invalid csrf")
        if len(token.encode("utf-8")) > MAX_CSRF_TOKEN_BYTES:
            raise ValueError("invalid csrf")
        if not _valid_session_id(session_id):
            raise ValueError("invalid csrf")
        try:
            payload = _safe_signed_load(self._csrf_serializer, token)
        except ValueError:
            raise ValueError("invalid csrf") from None
        if not isinstance(payload, dict):
            raise ValueError("invalid csrf")
        if set(payload) != {"version", "session_id"}:
            raise ValueError("invalid csrf")
        version = payload.get("version")
        if not _is_strict_int(version) or version != CSRF_PAYLOAD_VERSION:
            raise ValueError("invalid csrf")
        sid = payload.get("session_id")
        if not isinstance(sid, str) or not _valid_session_id(sid):
            raise ValueError("invalid csrf")
        if not hmac.compare_digest(sid, session_id):
            raise ValueError("invalid csrf")

    def expires_at_iso(self, claims: SessionClaims) -> str:
        return (
            datetime.fromtimestamp(claims.expires_at, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )


def secret_str_present(value: SecretStr | None) -> bool:
    return value is not None
