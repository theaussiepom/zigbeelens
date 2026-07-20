"""Absolute-time helpers for retention eligibility (Track 6).

SQLite's built-in ``julianday`` truncates below milliseconds. Retention
registers a deterministic ``retention_instant`` function that returns UTC epoch
seconds as a float with microsecond precision.

Accepted forms match the portable SQLite ``julianday()`` grammar subset:

- ``YYYY-MM-DDTHH:MM:SS[.fraction]``
- ``YYYY-MM-DD HH:MM:SS[.fraction]``

with optional timezone ``Z``, ``z``, ``+HH:MM``, or ``-HH:MM``. Naïve values
are interpreted as UTC. Malformed values return NULL and are never eligible
for deletion.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Documented grammar only. No leading/trailing whitespace, no date-only,
# no compact offsets, no timezone seconds, no unrestricted fromisoformat.
_RETENTION_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?P<sep>[T ])"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d{1,6})?"
    r"(?P<tz>Z|z|[+-]\d{2}:\d{2})?$"
)


def parse_retention_instant(value: object) -> float | None:
    """Return UTC epoch seconds (µs precision) or None when unparseable."""
    if value is None or not isinstance(value, str):
        return None
    match = _RETENTION_TIMESTAMP_RE.fullmatch(value)
    if match is None:
        return None
    text = (
        f"{match.group('date')}T{match.group('time')}"
        f"{match.group('fraction') or ''}"
    )
    tz = match.group("tz")
    if tz is None:
        text = f"{text}+00:00"
    elif tz in ("Z", "z"):
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
