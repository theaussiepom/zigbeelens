"""Redact sensitive values from MQTT JSON payloads before storage."""

from __future__ import annotations

import json
import re
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(password|pass|token|secret|network_key|install_code|auth|api_key|key)$",
    re.IGNORECASE,
)

REDACTED = "***"


def redact_payload_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_payload_dict(value)
    if isinstance(value, list):
        return [redact_payload_value(item) for item in value]
    return value


def redact_payload_dict(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if SECRET_KEY_PATTERN.search(key):
            out[key] = REDACTED
        elif isinstance(value, dict):
            out[key] = redact_payload_dict(value)
        elif isinstance(value, list):
            out[key] = [redact_payload_value(item) for item in value]
        else:
            out[key] = value
    return out


def redact_payload_text(payload: bytes | str) -> str:
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    else:
        text = payload
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed, dict):
        return json.dumps(redact_payload_dict(parsed))
    if isinstance(parsed, list):
        return json.dumps(redact_payload_value(parsed))
    return text


def extract_online_state(parsed: Any) -> str | None:
    if isinstance(parsed, str):
        value = parsed.strip().lower()
        if value in {"online", "offline"}:
            return value
        return None
    if isinstance(parsed, dict):
        for key in ("state", "availability"):
            if key in parsed:
                value = str(parsed[key]).strip().lower()
                if value in {"online", "offline"}:
                    return value
    return None


def safe_parse_json(payload: bytes | str) -> tuple[Any | None, str | None]:
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace").strip()
    else:
        text = payload.strip()
    if not text:
        return None, None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return text, str(exc)
