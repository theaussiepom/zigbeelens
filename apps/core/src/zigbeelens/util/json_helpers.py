"""Shared JSON parsing helpers."""

from __future__ import annotations

import json


def parse_json_list(raw: str | None) -> list:
    """Parse a JSON array stored in SQLite text columns; return [] on empty/invalid."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
