"""Stored report load boundary — exact v3 vs immutable legacy bodies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from zigbeelens.schemas import ReportDetailV3
from zigbeelens.storage.repository import ReportRow

LegacyStoredReportBody = dict[str, Any]


class StoredReportVersionKind(StrEnum):
    """Classification of a stored report_version claim."""

    legacy = "legacy"
    current = "current"
    protocol_error = "protocol_error"


@dataclass(frozen=True)
class StoredReportVersionClassification:
    kind: StoredReportVersionKind
    version: int | None = None


@dataclass(frozen=True)
class StoredReportEnvelope:
    """Request-local view of one stored report row without mutating the body."""

    row_id: str
    format: str
    report_version: int
    raw_body_json: str
    body: ReportDetailV3 | LegacyStoredReportBody
    markdown: str
    scope: str
    generated_at: str


def classify_stored_report_version(body: dict[str, Any]) -> StoredReportVersionClassification:
    """Distinguish historical absence from a malformed current-version claim.

    - missing report_version → legacy v1
    - integer 1 or 2 → legacy
    - historically tolerated string "1" or "2" → legacy
    - exact integer 3 → current (exact ReportDetailV3)
    - string "3", bool, float, object, array, negative, or version >3 → protocol error
    """
    if "report_version" not in body:
        return StoredReportVersionClassification(StoredReportVersionKind.legacy, 1)

    raw = body["report_version"]
    if type(raw) is int:
        if raw in (1, 2):
            return StoredReportVersionClassification(StoredReportVersionKind.legacy, raw)
        if raw == 3:
            return StoredReportVersionClassification(StoredReportVersionKind.current, 3)
        return StoredReportVersionClassification(StoredReportVersionKind.protocol_error)

    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped in ("1", "2"):
            return StoredReportVersionClassification(
                StoredReportVersionKind.legacy, int(stripped)
            )
        return StoredReportVersionClassification(StoredReportVersionKind.protocol_error)

    return StoredReportVersionClassification(StoredReportVersionKind.protocol_error)


def stored_report_version(body: dict[str, Any]) -> int | None:
    """Return the classified legacy/current version, or None for protocol errors."""
    classification = classify_stored_report_version(body)
    if classification.kind == StoredReportVersionKind.protocol_error:
        return None
    return classification.version


def parse_stored_body_json(raw_body_json: str) -> LegacyStoredReportBody | None:
    """Parse stored JSON without mutating the resulting dict."""
    if not raw_body_json:
        return None
    try:
        body = json.loads(raw_body_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return body


def load_stored_report_envelope(row: ReportRow) -> StoredReportEnvelope | None:
    """Load a stored report without rewriting historical bodies.

    Version 3 is validated as ReportDetailV3.
    Versions 1–2 remain opaque dicts exactly as stored (no id injection).
    Malformed current-version claims fail safely (not displayed as legacy).
    """
    if not row or not row.body_json:
        return None
    body = parse_stored_body_json(row.body_json)
    if body is None:
        return None
    classification = classify_stored_report_version(body)
    if classification.kind == StoredReportVersionKind.protocol_error:
        return None
    markdown = str(row.body_markdown or body.get("markdown_summary") or "")
    if classification.kind == StoredReportVersionKind.current:
        try:
            detail = ReportDetailV3.model_validate(body)
        except Exception:
            # Malformed v3 fails safely without becoming a new report.
            return None
        return StoredReportEnvelope(
            row_id=row.id,
            format=row.format,
            report_version=3,
            raw_body_json=row.body_json,
            body=detail,
            markdown=markdown if markdown else detail.markdown_summary,
            scope=row.scope,
            generated_at=row.generated_at,
        )
    version = classification.version if classification.version is not None else 1
    return StoredReportEnvelope(
        row_id=row.id,
        format=row.format,
        report_version=version,
        raw_body_json=row.body_json,
        body=body,
        markdown=markdown,
        scope=row.scope,
        generated_at=row.generated_at,
    )


def load_stored_report_body(row: ReportRow) -> ReportDetailV3 | LegacyStoredReportBody | None:
    """Compatibility loader returning the body only."""
    envelope = load_stored_report_envelope(row)
    if envelope is None:
        return None
    return envelope.body


def is_legacy_stored_report(value: ReportDetailV3 | LegacyStoredReportBody) -> bool:
    if isinstance(value, ReportDetailV3):
        return False
    classification = classify_stored_report_version(value)
    return classification.kind == StoredReportVersionKind.legacy


def legacy_report_format(value: LegacyStoredReportBody) -> str:
    raw = value.get("format") or "json"
    return str(raw)


def legacy_markdown(value: LegacyStoredReportBody) -> str:
    return str(value.get("markdown_summary") or "")
