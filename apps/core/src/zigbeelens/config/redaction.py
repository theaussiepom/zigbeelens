"""Secret-safe redaction helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import ParseResult, parse_qsl, unquote_plus, urlencode, urlparse, urlunparse

from pydantic import SecretStr

from zigbeelens.config.security_types import SESSION_COOKIE_NAME

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
        # Fixed browser-session authentication cookie / query key.
        SESSION_COOKIE_NAME,
        # Private Home Assistant ingress identity metadata (not bearer secrets).
        "x_remote_user_id",
        "x_remote_user_name",
        "x_remote_user_display_name",
        "remote_user_id",
        "remote_user_name",
        "remote_user_display_name",
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


def _raw_query_mentions_secret_key(query: str) -> bool:
    """Best-effort detection of secret-like keys in possibly malformed query text."""
    if not query:
        return False
    try:
        if _param_string_has_secret(query):
            return True
    except Exception:
        pass
    for part in query.split("&"):
        if not part:
            continue
        key = part.split("=", 1)[0]
        try:
            decoded = unquote_plus(key)
        except Exception:
            decoded = key
        if is_secret_key(decoded):
            return True
    return False


def redact_request_target(target: str) -> str:
    """Redact secret query values from an HTTP request target for access logs.

    Preserves the path and practical query ordering. Fragments are dropped
    because they are not part of HTTP request targets. Malformed query data
    fails closed to a fully redacted query when a secret-like key is present.
    """
    if not target:
        return target
    # Fragments are never part of the HTTP request target Uvicorn logs.
    target = target.split("#", 1)[0]
    if "?" not in target:
        return target
    path, query = target.split("?", 1)
    try:
        redacted_query = _redact_param_string(query)
    except Exception:
        if _raw_query_mentions_secret_key(query):
            return f"{path}?{REDACTED}"
        return path
    if not query and not redacted_query:
        return path
    return f"{path}?{redacted_query}"


def _format_host(hostname: str) -> str:
    """Bracket IPv6 hostnames for a valid URI authority."""
    if ":" in hostname and not hostname.startswith("["):
        return f"[{hostname}]"
    return hostname


def _redacted_netloc(
    parsed: ParseResult,
    *,
    username_override: str | None = None,
) -> str | None:
    """Build a safe authority from parsed URL facts.

    Returns None when the caller should fail closed to REDACTED (malformed port,
    or password-bearing / non-empty authority without a usable hostname).
    """
    try:
        port_number = parsed.port
    except ValueError:
        return None

    host = parsed.hostname or ""
    if not host:
        if parsed.password is not None or parsed.netloc:
            return None
        return ""

    host_fmt = _format_host(host)
    port = f":{port_number}" if port_number else ""

    if username_override:
        # MQTT status path: config username is known; never echo a password.
        return f"{username_override}:{REDACTED}@{host_fmt}{port}"

    if parsed.password is not None:
        # Empty username + password must still redact (mqtt://:secret@host).
        user = parsed.username if parsed.username is not None else ""
        return f"{user}:{REDACTED}@{host_fmt}{port}"

    if parsed.username:
        return f"{parsed.username}@{host_fmt}{port}"

    return f"{host_fmt}{port}"


def redact_mqtt_server(server: str, username: str = "") -> str:
    """Return an MQTT server URI safe for logs and API responses."""
    if not server:
        return server
    try:
        parsed = urlparse(server)
    except ValueError:
        return REDACTED

    netloc = _redacted_netloc(parsed, username_override=username or None)
    if netloc is None:
        # Fail closed for hostless/malformed authorities (e.g. mqtt://user:pass@).
        return REDACTED

    query = _redact_param_string(parsed.query)
    fragment = _redact_param_string(parsed.fragment)
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, query, fragment)
    )


def redact_connection_string(value: str) -> str:
    """Redact credentials embedded in connection strings and query/fragment text."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return REDACTED

    netloc = _redacted_netloc(parsed)
    if netloc is None:
        return REDACTED

    query = _redact_param_string(parsed.query)
    fragment = _redact_param_string(parsed.fragment)
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, query, fragment)
    )


def _raw_authority(value: str) -> str | None:
    """Return the raw authority between :// and the first /, ?, or #."""
    if "://" not in value:
        return None
    rest = value.split("://", 1)[1]
    for sep in ("/", "?", "#"):
        idx = rest.find(sep)
        if idx != -1:
            rest = rest[:idx]
            break
    return rest


def _raw_authority_is_credential_bearing(authority: str) -> bool:
    """True when userinfo before the final @ contains a password separator."""
    if "@" not in authority:
        return False
    userinfo, _, _host = authority.rpartition("@")
    # Includes empty usernames (`:password@host`) and non-empty (`user:pass@host`).
    return ":" in userinfo


def _raw_query_fragment_has_secret(value: str) -> bool:
    """Conservatively detect secret query/fragment keys without full URL parse."""
    query = ""
    fragment = ""
    if "?" in value:
        after_q = value.split("?", 1)[1]
        if "#" in after_q:
            query, fragment = after_q.split("#", 1)
        else:
            query = after_q
    elif "#" in value:
        fragment = value.split("#", 1)[1]
    return _param_string_has_secret(query) or _param_string_has_secret(fragment)


def _looks_like_credential_uri(value: str) -> bool:
    if "://" not in value:
        return False

    authority = _raw_authority(value) or ""
    raw_credential_authority = _raw_authority_is_credential_bearing(authority)

    try:
        parsed = urlparse(value)
    except ValueError:
        # Fail closed: unparseable credential-like URIs must still be redacted.
        return raw_credential_authority or _raw_query_fragment_has_secret(value)

    if parsed.password is not None or raw_credential_authority:
        return True
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
