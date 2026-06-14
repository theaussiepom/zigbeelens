"""Secret-safe redaction helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

REDACTED = "***"


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
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def redact_dict_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a dict with common secret keys redacted."""
    secret_keys = {"password", "secret", "token", "api_key", "network_key", "install_code"}
    out: dict[str, Any] = {}
    for key, value in data.items():
        lower = key.lower()
        if lower in secret_keys:
            out[key] = REDACTED
        elif isinstance(value, dict):
            out[key] = redact_dict_secrets(value)
        else:
            out[key] = value
    return out


def redact_connection_string(value: str) -> str:
    """Redact credentials embedded in connection strings."""
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", value)
