"""Canonical HTTP/HTTPS origin validation and normalization."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import urlsplit

import idna

from zigbeelens.config.secret_validation import contains_control_characters

MAX_ORIGIN_LENGTH = 2048

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

# Canonical dotted-decimal IPv4 only (no legacy browser forms).
_IPV4_STRICT = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
)
_NUMERIC_HOST = re.compile(r"^(?:[0-9.]+|0[xX][0-9A-Fa-f]+|[0-9]+)$")


class InvalidHttpOrigin(ValueError):
    """Raised when a value is not a canonical HTTP(S) origin."""

    def __init__(self, reason: str = "invalid origin") -> None:
        # Never embed the rejected input — it may contain credentials.
        super().__init__(reason)


def _has_forbidden_characters(value: str) -> bool:
    if "\\" in value:
        return True
    return contains_control_characters(value)


def _looks_like_numeric_host(hostname: str) -> bool:
    """True for hosts that must be strict IPv4 (never DNS fallthrough)."""
    return _NUMERIC_HOST.fullmatch(hostname) is not None


def _normalize_hostname(hostname: str) -> str:
    if not hostname:
        raise InvalidHttpOrigin("missing hostname")
    if "*" in hostname:
        raise InvalidHttpOrigin("wildcard hostname")
    if hostname.endswith("."):
        raise InvalidHttpOrigin("trailing-dot hostname")
    if "%" in hostname:
        raise InvalidHttpOrigin("zone identifier")
    if any(ch.isspace() for ch in hostname):
        raise InvalidHttpOrigin("whitespace hostname")
    if any(ch in hostname for ch in ("'", '"', ";", ",", "\\")):
        raise InvalidHttpOrigin("forbidden hostname characters")

    # IPv6 literals (urlsplit returns unbracketed form).
    if ":" in hostname:
        try:
            return ipaddress.IPv6Address(hostname).compressed
        except ValueError as exc:
            raise InvalidHttpOrigin("invalid ipv6") from exc

    # Numeric / dotted hosts: strict canonical IPv4 only — never DNS fallthrough.
    if _looks_like_numeric_host(hostname):
        if _IPV4_STRICT.fullmatch(hostname) is None:
            raise InvalidHttpOrigin("invalid ipv4")
        try:
            return str(ipaddress.IPv4Address(hostname))
        except ValueError as exc:
            raise InvalidHttpOrigin("invalid ipv4") from exc

    try:
        # Browser-aligned IDNA 2008 / UTS 46, non-transitional, STD3 rules.
        return idna.encode(
            hostname, uts46=True, transitional=False, std3_rules=True
        ).decode("ascii")
    except (idna.IDNAError, UnicodeError, ValueError) as exc:
        raise InvalidHttpOrigin("invalid hostname") from exc


def canonicalize_http_origin(value: str) -> str:
    """Return ``scheme://host[:port]`` or raise InvalidHttpOrigin.

    Rejects credentials, paths (other than empty/``/``), query, fragment,
    wildcards, non-HTTP schemes, and control characters. Does not resolve DNS.
    Hostnames use a CSP-safe grammar (strict IPv4/IPv6 or IDNA STD3 DNS).
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
    if ":" in host:
        host_fmt = f"[{host}]"
    else:
        host_fmt = host

    if port is None or port == _DEFAULT_PORTS[scheme]:
        origin = f"{scheme}://{host_fmt}"
    else:
        origin = f"{scheme}://{host_fmt}:{port}"

    # One whitespace-free CSP/CORS source expression.
    if any(ch.isspace() for ch in origin):
        raise InvalidHttpOrigin("whitespace origin")
    return origin


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
