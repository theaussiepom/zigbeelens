"""Shared security configuration enums and helpers."""

from __future__ import annotations

from enum import Enum
from typing import Any


class SecurityMode(str, Enum):
    local = "local"
    authenticated = "authenticated"
    home_assistant_ingress = "home_assistant_ingress"


def _security_block(config: Any) -> Any:
    return getattr(config, "security", config)


def bearer_auth_enabled(config: Any) -> bool:
    """True when a configured api_token opts the protected API into bearer auth."""
    return _security_block(config).api_token is not None


def trusted_local_open(config: Any) -> bool:
    security = _security_block(config)
    return security.mode is SecurityMode.local and security.api_token is None


def is_loopback_bind(host: str) -> bool:
    """Return True when *host* is a loopback bind without DNS resolution."""
    normalized = host.strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized in {"127.0.0.1", "localhost", "::1"}
