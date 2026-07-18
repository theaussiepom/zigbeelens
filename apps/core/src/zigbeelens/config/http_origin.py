"""Canonical HTTP/HTTPS origin validation and normalization."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

import idna

from zigbeelens.config.secret_validation import contains_control_characters

MAX_ORIGIN_LENGTH = 2048

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidHttpOrigin(ValueError):
    """Raised when a value is not a canonical HTTP(S) origin."""

    def __init__(self, reason: str = "invalid origin") -> None:
        # Never embed the rejected input — it may contain credentials.
        super().__init__(reason)


def _has_forbidden_characters(value: str) -> bool:
    if "\\" in value:
        return True
    return contains_control_characters(value)


def _normalize_hostname(hostname: str) -> str:
    if not hostname:
        raise InvalidHttpOrigin("missing hostname")
    if "*" in hostname:
        raise InvalidHttpOrigin("wildcard hostname")
    if hostname.endswith("."):
        raise InvalidHttpOrigin("trailing-dot hostname")
    # Reject IPv6 zone identifiers (not required by current deployments).
    if "%" in hostname:
        raise InvalidHttpOrigin("zone identifier")
    # ASCII hosts (including IPv4/IPv6 literals) stay lowercase without IDNA.
    try:
        hostname.encode("ascii")
        return hostname.lower()
    except UnicodeEncodeError:
        pass
    try:
        # Browser-aligned IDNA 2008 / UTS 46, non-transitional.
        return idna.encode(hostname, uts46=True, transitional=False).decode("ascii")
    except (idna.IDNAError, UnicodeError, ValueError) as exc:
        raise InvalidHttpOrigin("invalid hostname") from exc


def canonicalize_http_origin(value: str) -> str:
    """Return ``scheme://host[:port]`` or raise InvalidHttpOrigin.

    Rejects credentials, paths (other than empty/``/``), query, fragment,
    wildcards, non-HTTP schemes, and control characters. Does not resolve DNS.
    """
    if not isinstance(value, str):
        raise InvalidHttpOrigin("must be a string")
    if not value:
        raise InvalidHttpOrigin("empty")
    if value != value.strip():
        raise InvalidHttpOrigin("whitespace")
    if len(value) > MAX_ORIGIN_LENGTH:
        raise InvalidHttpOrigin("too long")
    if _has_forbidden_characters(value):
        raise InvalidHttpOrigin("forbidden characters")
    if value.lower() == "null":
        raise InvalidHttpOrigin("null origin")
    if value.startswith("//"):
        raise InvalidHttpOrigin("scheme-relative")
    if "\\" in value:
        raise InvalidHttpOrigin("backslash")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise InvalidHttpOrigin("malformed") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidHttpOrigin("unsupported scheme")

    # urlsplit puts userinfo in username/password; also reject raw '@' authority.
    if parts.username is not None or parts.password is not None:
        raise InvalidHttpOrigin("userinfo")
    if "@" in (parts.netloc or ""):
        raise InvalidHttpOrigin("userinfo")

    hostname = parts.hostname
    if hostname is None or hostname == "":
        raise InvalidHttpOrigin("missing hostname")

    # Path must be empty or a single slash; no params/query/fragment.
    path = parts.path or ""
    if path not in {"", "/"}:
        raise InvalidHttpOrigin("path")
    if parts.query:
        raise InvalidHttpOrigin("query")
    if parts.fragment:
        raise InvalidHttpOrigin("fragment")
    # Reject path parameters (`;…`) that urlsplit leaves inside path.
    if ";" in path:
        raise InvalidHttpOrigin("params")

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidHttpOrigin("invalid port") from exc
    if port is not None and (port < 1 or port > 65535):
        raise InvalidHttpOrigin("invalid port")

    host = _normalize_hostname(hostname)
    # Bracket IPv6 literals for the authority form.
    if ":" in host and not host.startswith("["):
        host_fmt = f"[{host}]"
    else:
        host_fmt = host

    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host_fmt}"
    return f"{scheme}://{host_fmt}:{port}"


def canonicalize_http_origins(values: Iterable[str]) -> tuple[str, ...]:
    """Canonicalize origins, deduplicating while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        origin = canonicalize_http_origin(raw)
        if origin in seen:
            continue
        seen.add(origin)
        out.append(origin)
    return tuple(out)
