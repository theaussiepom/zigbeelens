"""Typed incident collection query, cursor codec, and page result (Track 3E)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

INCIDENT_COLLECTION_CURSOR_VERSION = 1
DEFAULT_INCIDENT_COLLECTION_LIMIT = 50
MAX_INCIDENT_COLLECTION_LIMIT = 100
ALL_INCIDENT_STATUSES: tuple[str, ...] = ("open", "watching", "resolved")
_LIFECYCLE_RANK: dict[str, int] = {"open": 0, "watching": 1, "resolved": 2}
_RANK_TO_LIFECYCLE: dict[int, str] = {0: "open", 1: "watching", 2: "resolved"}

# Must match the expression index in migration 010 exactly.
LIFECYCLE_RANK_SQL = (
    "CASE lifecycle_state WHEN 'open' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END"
)

_URLSAFE_B64_RE = re.compile(r"^[A-Za-z0-9_-]*={0,2}$")


class IncidentCollectionQueryError(ValueError):
    """Invalid incident collection query parameters."""


class IncidentCollectionCursorError(ValueError):
    """Invalid or mismatched incident collection cursor."""


@dataclass(frozen=True)
class IncidentCollectionQuery:
    """Validated, immutable collection query for paginated incident reads."""

    status_filter: tuple[str, ...]
    updated_after: str | None
    network_id: str | None
    device_ieee: str | None
    limit: int
    cursor: str | None = None

    @property
    def filter_signature(self) -> str:
        canonical = json.dumps(
            {
                "device_ieee": self.device_ieee,
                "network_id": self.network_id,
                "status": list(self.status_filter),
                "updated_after": self.updated_after,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IncidentCollectionCursor:
    version: int
    lifecycle_rank: int
    updated_at: str
    incident_id: str
    filter_signature: str


@dataclass(frozen=True)
class IncidentCollectionPage:
    rows: tuple[dict[str, Any], ...]
    total: int
    limit: int
    next_cursor: str | None


def lifecycle_rank(lifecycle_state: str) -> int:
    try:
        return _LIFECYCLE_RANK[lifecycle_state]
    except KeyError as exc:
        raise IncidentCollectionQueryError(
            f"Invalid incident status: {lifecycle_state!r}"
        ) from exc


def canonicalize_utc_iso(value: str) -> str:
    """Parse ISO-8601 (Z or offset) to UTC ISO, preserving sub-second precision."""
    text = value.strip()
    if not text:
        raise IncidentCollectionQueryError("timestamp must be a non-empty ISO-8601 datetime")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncidentCollectionQueryError(
            "timestamp must be a valid ISO-8601 datetime"
        ) from exc
    if parsed.tzinfo is None:
        raise IncidentCollectionQueryError("timestamp must include a timezone offset or Z")
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_updated_after(value: str) -> str:
    """Canonical UTC ISO for query bounds; preserves microsecond precision."""
    return canonicalize_utc_iso(value)


def validate_cursor_timestamp(value: str) -> str:
    """Require a canonical UTC +00:00 timestamp matching DB lexical form."""
    if not isinstance(value, str) or not value:
        raise IncidentCollectionCursorError("Invalid incident collection cursor timestamp")
    if "Z" in value or value.endswith("z"):
        raise IncidentCollectionCursorError("Invalid incident collection cursor timestamp")
    if not value.endswith("+00:00"):
        raise IncidentCollectionCursorError("Invalid incident collection cursor timestamp")
    try:
        canonical = canonicalize_utc_iso(value)
    except IncidentCollectionQueryError as exc:
        raise IncidentCollectionCursorError(
            "Invalid incident collection cursor timestamp"
        ) from exc
    if canonical != value:
        raise IncidentCollectionCursorError("Invalid incident collection cursor timestamp")
    return value


def build_incident_collection_query(
    *,
    status: list[str] | tuple[str, ...] | None = None,
    updated_after: str | None = None,
    network_id: str | None = None,
    device_ieee: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> IncidentCollectionQuery:
    if status is None or len(status) == 0:
        statuses = ALL_INCIDENT_STATUSES
    else:
        seen: set[str] = set()
        for raw in status:
            value = str(raw).strip()
            if value not in _LIFECYCLE_RANK:
                raise IncidentCollectionQueryError(f"Invalid incident status: {raw!r}")
            if value not in seen:
                seen.add(value)
        # Preserve lifecycle presentation order rather than request order.
        statuses = tuple(state for state in ALL_INCIDENT_STATUSES if state in seen)

    if device_ieee is not None and not str(device_ieee).strip():
        raise IncidentCollectionQueryError("device_ieee must be non-empty when provided")
    if network_id is not None and not str(network_id).strip():
        raise IncidentCollectionQueryError("network_id must be non-empty when provided")
    device = str(device_ieee).strip() if device_ieee is not None else None
    network = str(network_id).strip() if network_id is not None else None
    if device is not None and network is None:
        raise IncidentCollectionQueryError("device_ieee requires network_id")

    if limit is None:
        resolved_limit = DEFAULT_INCIDENT_COLLECTION_LIMIT
    else:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise IncidentCollectionQueryError("limit must be an integer")
        if limit < 1 or limit > MAX_INCIDENT_COLLECTION_LIMIT:
            raise IncidentCollectionQueryError(
                f"limit must be between 1 and {MAX_INCIDENT_COLLECTION_LIMIT}"
            )
        resolved_limit = limit

    ua = normalize_updated_after(updated_after) if updated_after is not None else None
    cursor_text = cursor.strip() if cursor is not None and cursor.strip() else None

    return IncidentCollectionQuery(
        status_filter=statuses,
        updated_after=ua,
        network_id=network,
        device_ieee=device,
        limit=resolved_limit,
        cursor=cursor_text,
    )


def encode_incident_collection_cursor(cursor: IncidentCollectionCursor) -> str:
    payload = {
        "v": cursor.version,
        "lr": cursor.lifecycle_rank,
        "u": cursor.updated_at,
        "id": cursor.incident_id,
        "fs": cursor.filter_signature,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_urlsafe_b64_strict(token: str) -> bytes:
    """Decode URL-safe Base64; reject non-alphabet and ignored trailing characters."""
    if not token or not _URLSAFE_B64_RE.fullmatch(token):
        raise IncidentCollectionCursorError("Invalid incident collection cursor")
    pad_len = (-len(token)) % 4
    padded = token + ("=" * pad_len)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except binascii.Error as exc:
        raise IncidentCollectionCursorError("Invalid incident collection cursor") from exc
    # Round-trip: ignore only the padding we would ourselves add/strip.
    reencoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    provided = token.rstrip("=")
    if reencoded != provided:
        raise IncidentCollectionCursorError("Invalid incident collection cursor")
    if token.endswith("="):
        expected_padded = reencoded + ("=" * ((4 - len(reencoded) % 4) % 4))
        if token != expected_padded:
            raise IncidentCollectionCursorError("Invalid incident collection cursor")
    return raw


def decode_incident_collection_cursor(
    token: str,
    *,
    expected_filter_signature: str,
) -> IncidentCollectionCursor:
    try:
        raw = _decode_urlsafe_b64_strict(token)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IncidentCollectionCursorError("Invalid incident collection cursor") from exc

    if not isinstance(payload, dict):
        raise IncidentCollectionCursorError("Invalid incident collection cursor")

    allowed = {"v", "lr", "u", "id", "fs"}
    if set(payload) != allowed:
        raise IncidentCollectionCursorError("Invalid incident collection cursor")

    version = payload["v"]
    lifecycle_rank_value = payload["lr"]
    updated_at = payload["u"]
    incident_id = payload["id"]
    filter_signature = payload["fs"]

    if version != INCIDENT_COLLECTION_CURSOR_VERSION:
        raise IncidentCollectionCursorError("Unsupported incident collection cursor version")
    if not isinstance(lifecycle_rank_value, int) or isinstance(lifecycle_rank_value, bool):
        raise IncidentCollectionCursorError("Invalid incident collection cursor")
    if lifecycle_rank_value not in _RANK_TO_LIFECYCLE:
        raise IncidentCollectionCursorError("Invalid incident collection cursor lifecycle")
    updated_at = validate_cursor_timestamp(updated_at)
    if not isinstance(incident_id, str) or not incident_id:
        raise IncidentCollectionCursorError("Invalid incident collection cursor id")
    if not isinstance(filter_signature, str) or not filter_signature:
        raise IncidentCollectionCursorError("Invalid incident collection cursor")
    if filter_signature != expected_filter_signature:
        raise IncidentCollectionCursorError("Incident collection cursor does not match filters")

    return IncidentCollectionCursor(
        version=version,
        lifecycle_rank=lifecycle_rank_value,
        updated_at=updated_at,
        incident_id=incident_id,
        filter_signature=filter_signature,
    )


def cursor_from_incident_row(
    row: Mapping[str, Any],
    *,
    filter_signature: str,
) -> IncidentCollectionCursor:
    # Keep the exact DB timestamp text so keyset equality remains lexical.
    updated_at = validate_cursor_timestamp(str(row["updated_at"]))
    return IncidentCollectionCursor(
        version=INCIDENT_COLLECTION_CURSOR_VERSION,
        lifecycle_rank=lifecycle_rank(str(row["lifecycle_state"])),
        updated_at=updated_at,
        incident_id=str(row["id"]),
        filter_signature=filter_signature,
    )
