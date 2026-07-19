"""Stored report load boundary — exact v3 vs immutable legacy bodies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from zigbeelens.schemas import ReportDetailV3
from zigbeelens.storage.repository import ReportRow

LegacyStoredReportBody = dict[str, Any]


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


def stored_report_version(body: dict[str, Any]) -> int:
    raw = body.get("report_version", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


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
    """
    if not row or not row.body_json:
        return None
    body = parse_stored_body_json(row.body_json)
    if body is None:
        return None
    version = stored_report_version(body)
    markdown = str(row.body_markdown or body.get("markdown_summary") or "")
    if version >= 3:
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
    return stored_report_version(value) < 3


def legacy_report_format(value: LegacyStoredReportBody) -> str:
    raw = value.get("format") or "json"
    return str(raw)


def legacy_markdown(value: LegacyStoredReportBody) -> str:
    return str(value.get("markdown_summary") or "")
