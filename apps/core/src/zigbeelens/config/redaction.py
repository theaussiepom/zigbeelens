"""Secret-safe redaction helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import SecretStr

REDACTED = "***"

_EXACT_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
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


def is_secret_key(key: str) -> bool:
    """Return True for conventional secret field names, not safe metadata."""
    # Normalise hyphenated URL/config keys (api-key → api_key).
    lower = key.lower().replace("-", "_")
    if lower.endswith("_configured") or lower.endswith("_count"):
        return False
    if lower in {"token_source", "secret_source"}:
        return False
    if lower in _EXACT_SECRET_KEYS:
        return True
    return any(lower.endswith(suffix) for suffix in _SECRET_SUFFIXES)


def _redact_param_string(value: str) -> str:
    """Redact secret-bearing query/fragment parameters using is_secret_key()."""
    if not value:
        return ""
    # parse_qsl URL-decodes keys/values and preserves order.
    pairs = parse_qsl(value, keep_blank_values=True)
    redacted_pairs: list[tuple[str, str]] = []
    for key, item in pairs:
        if is_secret_key(key):
            redacted_pairs.append((key, REDACTED))
        else:
            redacted_pairs.append((key, item))
    # Keep REDACTED ("***") literal; preserve practical ordering from parse_qsl.
    return urlencode(redacted_pairs, doseq=True, safe="*")


def _param_string_has_secret(value: str) -> bool:
    if not value:
        return False
    return any(is_secret_key(key) for key, _ in parse_qsl(value, keep_blank_values=True))


def redact_mqtt_server(server: str, username: str = "") -> str:
    """Return an MQTT server URI safe for logs and API responses."""
    if not server:
        return server
    try:
        parsed = urlparse(server)
    except ValueError:
        return REDACTED

    try:
        port_number = parsed.port
    except ValueError:
        return REDACTED

    host = parsed.hostname or ""
    port = f":{port_number}" if port_number else ""
    user_part = f"{username}:{REDACTED}@" if username else ""
    if not host:
        # Fail closed for hostless/malformed authorities (e.g. mqtt://user:pass@).
        # Never return a raw netloc that may still contain userinfo.
        if parsed.netloc or "@" in server:
            return REDACTED
        netloc = ""
    else:
        netloc = f"{user_part}{host}{port}"

    query = _redact_param_string(parsed.query)
    fragment = _redact_param_string(parsed.fragment)
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, query, fragment)
    )


def redact_connection_string(value: str) -> str:
    """Redact credentials embedded in connection strings and query/fragment text."""
    redacted = re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", value)
    try:
        parsed = urlparse(redacted)
    except ValueError:
        return REDACTED
    query = _redact_param_string(parsed.query)
    fragment = _redact_param_string(parsed.fragment)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, fragment)
    )


def _looks_like_credential_uri(value: str) -> bool:
    if "://" not in value:
        return False
    if re.search(r"://[^:/@]+:[^@/]+@", value):
        return True
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return _param_string_has_secret(parsed.query) or _param_string_has_secret(
        parsed.fragment
    )


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
