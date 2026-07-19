"""Exact ingress trusted-proxy and Home Assistant user-ID grammar."""

from __future__ import annotations

import ipaddress
import re

# Exact Supervisor ingress peer used by the ZigbeeLens add-on.
ADDON_SUPERVISOR_INGRESS_PEER = "172.30.32.2"

_USER_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class InvalidIngressTrustedProxy(ValueError):
    """Trusted proxy literal failed validation (message never echoes input)."""


def canonicalize_ingress_trusted_proxy(value: object) -> str:
    """Return a canonical exact IP literal or raise InvalidIngressTrustedProxy."""
    if not isinstance(value, str):
        raise InvalidIngressTrustedProxy("must be an IP address string")
    if value != value.strip() or not value:
        raise InvalidIngressTrustedProxy("must not have leading or trailing whitespace")
    if "/" in value or "%" in value:
        raise InvalidIngressTrustedProxy("CIDRs and zone identifiers are not allowed")
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        raise InvalidIngressTrustedProxy("must be an exact IP address") from None
    if addr.is_unspecified or addr.is_multicast:
        raise InvalidIngressTrustedProxy("address is not allowed")
    return str(addr)


def canonicalize_ingress_trusted_proxies(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raise InvalidIngressTrustedProxy("must be a list of IP address strings")
    if not isinstance(values, (list, tuple)):
        raise InvalidIngressTrustedProxy("must be a list of IP address strings")
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        canonical = canonicalize_ingress_trusted_proxy(item)
        if canonical in seen:
            raise InvalidIngressTrustedProxy("duplicate trusted proxy")
        seen.add(canonical)
        out.append(canonical)
    return tuple(out)


def normalize_ha_user_id(raw: str) -> str | None:
    """Return lowercase exact 32-hex user ID, or None when structurally invalid.

    Accepts only ``[0-9A-Fa-f]{32}``. Hyphenated UUID strings are rejected.
    """
    if not isinstance(raw, str) or not raw:
        return None
    if raw != raw.strip():
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return None
    if any(ch in raw for ch in ("-", ",", " ", "\t", "{", "}")):
        return None
    candidate = raw.lower()
    if _USER_ID_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate
