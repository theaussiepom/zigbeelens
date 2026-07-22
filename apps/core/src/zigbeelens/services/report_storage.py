"""Stored report load boundary — exact ReportDetailV3 only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from zigbeelens.schemas import ReportDetailV3
from zigbeelens.storage.repository import ReportRow


@dataclass(frozen=True)
class StoredReportEnvelope:
    """Request-local view of one stored report row without mutating the body."""

    row_id: str
    format: str
    report_version: int
    raw_body_json: str
    body: ReportDetailV3
    markdown: str
    scope: str
    generated_at: str


def parse_stored_body_json(raw_body_json: str) -> dict[str, Any] | None:
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


def _is_exact_v3_version(raw: Any) -> bool:
    return type(raw) is int and raw == 3


def load_stored_report_envelope(row: ReportRow) -> StoredReportEnvelope | None:
    """Load a stored report as exact ReportDetailV3, or None when fail-closed.

    Requires non-empty body_json, a JSON object, exact integer report_version 3,
    and successful ReportDetailV3 validation. All other bodies fail closed.
    """
    if not row or not row.body_json:
        return None
    body = parse_stored_body_json(row.body_json)
    if body is None:
        return None
    if not _is_exact_v3_version(body.get("report_version")):
        return None
    try:
        detail = ReportDetailV3.model_validate(body)
    except Exception:
        return None
    markdown = str(row.body_markdown or detail.markdown_summary or "")
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


def load_stored_report_body(row: ReportRow) -> ReportDetailV3 | None:
    """Compatibility loader returning the validated body only."""
    envelope = load_stored_report_envelope(row)
    if envelope is None:
        return None
    return envelope.body
