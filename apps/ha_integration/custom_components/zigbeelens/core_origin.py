"""Canonical HTTP/HTTPS Core origin validation for the HACS companion."""

from __future__ import annotations

from urllib.parse import urlsplit

import idna

MAX_ORIGIN_LENGTH = 2048
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidCoreOrigin(ValueError):
    """Raised when a Core URL is not a canonical HTTP(S) origin."""

    def __init__(self, reason: str = "invalid_url") -> None:
        # Never embed rejected input — it may contain credentials.
        super().__init__(reason)


def _has_forbidden_characters(value: str) -> bool:
    if "\\" in value:
        return True
    # Full Unicode Cc category (matches Core secret_validation predicate).
    import unicodedata

    return any(unicodedata.category(ch) == "Cc" for ch in value)


def _normalize_hostname(hostname: str) -> str:
    if not hostname:
        raise InvalidCoreOrigin("invalid_url")
    if "*" in hostname:
        raise InvalidCoreOrigin("invalid_url")
    if hostname.endswith("."):
        raise InvalidCoreOrigin("invalid_url")
    if "%" in hostname:
        raise InvalidCoreOrigin("invalid_url")
    try:
        hostname.encode("ascii")
        return hostname.lower()
    except UnicodeEncodeError:
        pass
    try:
        return idna.encode(hostname, uts46=True, transitional=False).decode("ascii")
    except (idna.IDNAError, UnicodeError, ValueError) as exc:
        raise InvalidCoreOrigin("invalid_url") from exc


def canonicalize_core_origin(value: str) -> str:
    """Return a canonical ``scheme://host[:port]`` Core origin.

    Rejects credentials, non-root paths, query, fragment, wildcards, and
    non-HTTP schemes. Does not resolve DNS. A single trailing ``/`` is the only
    path form that normalizes away.
    """
    if not isinstance(value, str):
        raise InvalidCoreOrigin("invalid_url")
    if not value:
        raise InvalidCoreOrigin("invalid_url")
    if value != value.strip():
        raise InvalidCoreOrigin("invalid_url")
    if len(value) > MAX_ORIGIN_LENGTH:
        raise InvalidCoreOrigin("invalid_url")
    if _has_forbidden_characters(value):
        raise InvalidCoreOrigin("invalid_url")
    if value.lower() == "null":
        raise InvalidCoreOrigin("invalid_url")
    if value.startswith("//"):
        raise InvalidCoreOrigin("invalid_url")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise InvalidCoreOrigin("invalid_url") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidCoreOrigin("invalid_url")
    if parts.username is not None or parts.password is not None:
        raise InvalidCoreOrigin("invalid_url")
    if "@" in (parts.netloc or ""):
        raise InvalidCoreOrigin("invalid_url")

    hostname = parts.hostname
    if hostname is None or hostname == "":
        raise InvalidCoreOrigin("invalid_url")

    path = parts.path or ""
    if path not in {"", "/"}:
        raise InvalidCoreOrigin("invalid_url")
    if parts.query or parts.fragment:
        raise InvalidCoreOrigin("invalid_url")
    if ";" in path:
        raise InvalidCoreOrigin("invalid_url")

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidCoreOrigin("invalid_url") from exc
    if port is not None and (port < 1 or port > 65535):
        raise InvalidCoreOrigin("invalid_url")

    host = _normalize_hostname(hostname)
    if ":" in host and not host.startswith("["):
        host_fmt = f"[{host}]"
    else:
        host_fmt = host

    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host_fmt}"
    return f"{scheme}://{host_fmt}:{port}"
