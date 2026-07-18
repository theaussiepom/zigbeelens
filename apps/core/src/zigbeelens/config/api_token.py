"""Shared API-token grammar for configuration and HTTP Bearer parsing.

Tokens must be ASCII token68-compatible so every accepted configured value can
be sent as ``Authorization: Bearer <token>`` without structural rejection.
"""

from __future__ import annotations

import re

from pydantic import SecretStr

from zigbeelens.config.secret_validation import contains_control_characters

API_TOKEN_MIN_LENGTH = 32
API_TOKEN_MAX_LENGTH = 4096

# token68 body with optional '=' padding restricted to the end.
API_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9\-._~+/]+={0,}$")

# Scheme + one or more ASCII spaces (not tabs) + token. Case-insensitive scheme.
BEARER_AUTHORIZATION_PATTERN = re.compile(
    r"^Bearer( +)([A-Za-z0-9\-._~+/]+={0,})$",
    re.IGNORECASE,
)


def is_api_token_shape(value: str) -> bool:
    """Return True when *value* matches the shared bearer token grammar."""
    if not (API_TOKEN_MIN_LENGTH <= len(value) <= API_TOKEN_MAX_LENGTH):
        return False
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return API_TOKEN_PATTERN.fullmatch(value) is not None


def parse_bearer_authorization_header(raw: str) -> str | None:
    """Return the bearer credential from a single Authorization header value.

    Returns None only when the helper should not be used (caller handles empty).
    Raises ValueError for malformed values without echoing the credential.
    """
    if "," in raw:
        raise ValueError("malformed authorization header")
    match = BEARER_AUTHORIZATION_PATTERN.fullmatch(raw)
    if match is None:
        raise ValueError("malformed authorization header")
    token = match.group(2)
    if not is_api_token_shape(token):
        raise ValueError("malformed authorization header")
    return token


def reject_invalid_api_token(value: object) -> SecretStr:
    """Validate an API token for configuration without echoing rejected input."""
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
    elif isinstance(value, str):
        raw = value
    else:
        raise ValueError("must be a string")

    if raw == "":
        raise ValueError("must not be empty")
    if raw != raw.strip():
        raise ValueError("must not have leading or trailing whitespace")
    if contains_control_characters(raw):
        raise ValueError("must not contain control characters")
    if len(raw) < API_TOKEN_MIN_LENGTH:
        raise ValueError(f"must be at least {API_TOKEN_MIN_LENGTH} characters")
    if len(raw) > API_TOKEN_MAX_LENGTH:
        raise ValueError(f"must be at most {API_TOKEN_MAX_LENGTH} characters")
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("must be ASCII") from None
    if API_TOKEN_PATTERN.fullmatch(raw) is None:
        raise ValueError("must be a bearer-compatible token")
    return SecretStr(raw)
