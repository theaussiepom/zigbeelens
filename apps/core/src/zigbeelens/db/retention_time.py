"""Absolute-time helpers for retention eligibility (Track 6).

SQLite's built-in ``julianday`` truncates below milliseconds. Retention
registers a deterministic ``retention_instant`` function that returns UTC epoch
seconds as a float with microsecond precision.

Accepted forms match the portable SQLite ``julianday()`` grammar subset:

- ``YYYY-MM-DDTHH:MM:SS[.fraction]``
- ``YYYY-MM-DD HH:MM:SS[.fraction]``

with optional timezone ``Z``, ``z``, ``+HH:MM``, or ``-HH:MM`` where
``HH`` is 0..14 and ``MM`` is 0..59. Naïve values are interpreted as UTC.
Malformed values return NULL and are never eligible for deletion.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Documented grammar only. ASCII digits; no surrounding whitespace; no
# date-only; no compact offsets; no timezone seconds; offset range checked
# before fromisoformat so Python cannot normalize invalid offsets.
_RETENTION_TIMESTAMP_RE = re.compile(
    r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"(?P<sep>[T ])"
    r"(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?P<fraction>\.[0-9]{1,6})?"
    r"(?P<tz>Z|z|[+-]([0-9]{2}):([0-9]{2}))?$"
)


def parse_retention_instant(value: object) -> float | None:
    """Return UTC epoch seconds (µs precision) or None when unparseable."""
    if value is None or not isinstance(value, str):
        return None
    match = _RETENTION_TIMESTAMP_RE.fullmatch(value)
    if match is None:
        return None
    tz = match.group("tz")
    if tz is not None and tz not in ("Z", "z"):
        hour = int(tz[1:3])
        minute = int(tz[4:6])
        if hour > 14 or minute > 59:
            return None
    text = (
        f"{match.group('date')}T{match.group('time')}"
        f"{match.group('fraction') or ''}"
    )
    if tz is None or tz in ("Z", "z"):
        text = f"{text}+00:00"
    else:
        text = f"{text}{tz}"
    try:
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
