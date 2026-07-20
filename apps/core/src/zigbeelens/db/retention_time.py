"""Absolute-time helpers for retention eligibility (Track 6).

SQLite's built-in ``julianday`` truncates below milliseconds. Retention
registers a deterministic ``retention_instant`` function that returns UTC epoch
seconds as a float with microsecond precision for:

- ISO-8601 with ``+00:00`` / ``Z`` / ``z`` / explicit offsets
- SQLite ``YYYY-MM-DD HH:MM:SS`` (treated as UTC)
- SQLite-style strings with offsets: ``YYYY-MM-DD HH:MM:SS+10:00``

Malformed values return NULL and are never eligible for deletion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_retention_instant(value: object) -> float | None:
    """Return UTC epoch seconds (µs precision) or None when unparseable."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        if "T" not in text and " " in text:
            # SQLite datetime form, with or without an explicit offset.
            # Replace the date/time separator only; do not invent an offset here.
            text = text.replace(" ", "T", 1)
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def register_retention_sql_functions(conn: Any) -> None:
    """Register ``retention_instant`` on an open sqlite3 connection."""
    conn.create_function(
        "retention_instant",
        1,
        parse_retention_instant,
        deterministic=True,
    )
