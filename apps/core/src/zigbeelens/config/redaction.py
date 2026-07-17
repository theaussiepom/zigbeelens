"""Secret-safe redaction helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import SecretStr

REDACTED = "***"

_EXACT_SECRET_KEYS = frozenset(
    {
        "password",
        "passphrase",
        "secret",
        "session_secret",
        "client_secret",
        "token",
        "api_token",
        "access_token",
        "refresh_token",
        "api_key",
        "authorization",
        "private_key",
        "network_key",
        "install_code",
    }
)

_SECRET_SUFFIXES = (
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
)

_CONNECTION_QUERY_SECRET = re.compile(
    r"(?i)([?&#](?:password|passwd|passphrase|secret|token|api[_-]?key|access_token|refresh_token)=)([^&#]*)"
)


def is_secret_key(key: str) -> bool:
    """Return True for conventional secret field names, not safe metadata."""
    lower = key.lower()
    if lower.endswith("_configured") or lower.endswith("_count"):
        return False
    if lower in {"token_source", "secret_source"}:
        return False
    if lower in _EXACT_SECRET_KEYS:
        return True
    return any(lower.endswith(suffix) for suffix in _SECRET_SUFFIXES)


def redact_mqtt_server(server: str, username: str = "") -> str:
    """Return an MQTT server URI safe for logs and API responses."""
    if not server:
        return server
    try:
        parsed = urlparse(server)
    except ValueError:
        return REDACTED

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user_part = f"{username}:{REDACTED}@" if username else ""
    netloc = f"{user_part}{host}{port}" if host else parsed.netloc
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def redact_connection_string(value: str) -> str:
    """Redact credentials embedded in connection strings and query/fragment text."""
    redacted = re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", value)
    return _CONNECTION_QUERY_SECRET.sub(r"\1***", redacted)


def _looks_like_credential_uri(value: str) -> bool:
    if "://" not in value:
        return False
    if re.search(r"://[^:/@]+:[^@/]+@", value):
        return True
    return bool(_CONNECTION_QUERY_SECRET.search(value))


def _redact_any(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            key: (REDACTED if is_secret_key(str(key)) else _redact_any(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_any(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_any(item) for item in value)
    if isinstance(value, (set, frozenset)):
        # Sets cannot contain unhashable nested structures after redaction of
        # dicts; convert members individually and preserve set-ness when safe.
        redacted_items = [_redact_any(item) for item in value]
        try:
            return type(value)(redacted_items)
        except TypeError:
            return redacted_items
    if isinstance(value, str) and _looks_like_credential_uri(value):
        return redact_connection_string(value)
    return value


def redact_dict_secrets(data: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Deep-copy mapping-like data with conventional secret keys redacted."""
    redacted = _redact_any(data)
    if not isinstance(redacted, dict):
        return dict(redacted)
    return redacted
