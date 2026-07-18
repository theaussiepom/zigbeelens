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
# WHATWG IPv4-number-like final label: decimal digits or 0x-hex.
_IPV4_NUMBER_LABEL = re.compile(r"^(?:[0-9]+|0[xX][0-9A-Fa-f]+)$")


class InvalidHttpOrigin(ValueError):
    """Raised when a value is not a canonical HTTP(S) origin."""

    def __init__(self, reason: str = "invalid origin") -> None:
        # Never embed the rejected input — it may contain credentials.
        super().__init__(reason)


def _has_forbidden_characters(value: str) -> bool:
    if "\\" in value:
        return True
    return contains_control_characters(value)


def _ends_in_ipv4_number(hostname: str) -> bool:
    """True when the last label is WHATWG IPv4-number-like."""
    if not hostname:
        return False
    label = hostname.rsplit(".", 1)[-1]
    return _IPV4_NUMBER_LABEL.fullmatch(label) is not None


def _strict_ipv4(hostname: str) -> str:
    if _IPV4_STRICT.fullmatch(hostname) is None:
        raise InvalidHttpOrigin("invalid ipv4")
    try:
        return str(ipaddress.IPv4Address(hostname))
    except ValueError:
        raise InvalidHttpOrigin("invalid ipv4") from None


def _validate_ascii_hostname(hostname: str) -> None:
    """Post-IDNA / ASCII host checks (trailing-dot, empty labels, IPv4 fallthrough)."""
    if not hostname:
        raise InvalidHttpOrigin("missing hostname")
    if hostname.endswith(".") or hostname.startswith("."):
        raise InvalidHttpOrigin("trailing-dot hostname")
    if ".." in hostname:
        raise InvalidHttpOrigin("empty label")
    if any(ch.isspace() for ch in hostname):
        raise InvalidHttpOrigin("whitespace hostname")
    if any(ch in hostname for ch in ("'", '"', ";", ",", "\\")):
        raise InvalidHttpOrigin("forbidden hostname characters")
    if _ends_in_ipv4_number(hostname) and _IPV4_STRICT.fullmatch(hostname) is None:
        raise InvalidHttpOrigin("invalid ipv4")


def _normalize_hostname(hostname: str, *, bracketed: bool) -> str:
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

    # Bracketed authorities are IPv6-only (reject IPvFuture / bracketed DNS).
    if bracketed:
        try:
            return ipaddress.IPv6Address(hostname).compressed
        except ValueError:
            raise InvalidHttpOrigin("invalid ipv6") from None

    # Unbracketed host with ':' is treated as IPv6 literal.
    if ":" in hostname:
        try:
            return ipaddress.IPv6Address(hostname).compressed
        except ValueError:
            raise InvalidHttpOrigin("invalid ipv6") from None

    # Hosts ending in an IPv4-number-like label: strict dotted-decimal only.
    if _ends_in_ipv4_number(hostname):
        return _strict_ipv4(hostname)

    try:
        ascii_host = idna.encode(
            hostname, uts46=True, transitional=False, std3_rules=True
        ).decode("ascii")
    except (idna.IDNAError, UnicodeError, ValueError):
        raise InvalidHttpOrigin("invalid hostname") from None

    _validate_ascii_hostname(ascii_host)
    return ascii_host


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
    except ValueError:
        raise InvalidHttpOrigin("malformed") from None

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidHttpOrigin("unsupported scheme")

    # urlsplit puts userinfo in username/password; also reject raw '@' authority.
    if parts.username is not None or parts.password is not None:
        raise InvalidHttpOrigin("userinfo")
    if "@" in (parts.netloc or ""):
        raise InvalidHttpOrigin("userinfo")

    netloc = parts.netloc or ""
    bracketed = netloc.startswith("[")
    if bracketed and "]" not in netloc:
        raise InvalidHttpOrigin("invalid ipv6")

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
    if ";" in path:
        raise InvalidHttpOrigin("params")

    try:
        port = parts.port
    except ValueError:
        raise InvalidHttpOrigin("invalid port") from None
    if port is not None and (port < 1 or port > 65535):
        raise InvalidHttpOrigin("invalid port")

    host = _normalize_hostname(hostname, bracketed=bracketed)
    if ":" in host:
        host_fmt = f"[{host}]"
    else:
        host_fmt = host

    if port is None or port == _DEFAULT_PORTS[scheme]:
        origin = f"{scheme}://{host_fmt}"
    else:
        origin = f"{scheme}://{host_fmt}:{port}"

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
