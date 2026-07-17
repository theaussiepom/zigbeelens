"""Shared security configuration enums and helpers."""

from __future__ import annotations

from enum import Enum


class SecurityMode(str, Enum):
    local = "local"
    authenticated = "authenticated"
    home_assistant_ingress = "home_assistant_ingress"


def is_loopback_bind(host: str) -> bool:
    """Return True when *host* is a loopback bind without DNS resolution."""
    normalized = host.strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized in {"127.0.0.1", "localhost", "::1"}
