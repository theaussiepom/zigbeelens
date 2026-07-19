"""Stored report load boundary — current v3 vs immutable legacy bodies."""

from __future__ import annotations

import json
from typing import Any

from zigbeelens.schemas import ReportDetail
from zigbeelens.storage.repository import ReportRow


def stored_report_version(body: dict[str, Any]) -> int:
    raw = body.get("report_version", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def load_stored_report_body(row: ReportRow) -> ReportDetail | dict[str, Any] | None:
    """Load a stored report without rewriting historical bodies.

    Version 3+ is validated as the current ReportDetail contract.
    Versions 1–2 remain opaque dicts exactly as stored.
    """
    if not row or not row.body_json:
        return None
    try:
        body = json.loads(row.body_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    body = dict(body)
    body["id"] = row.id
    version = stored_report_version(body)
    if version >= 3:
        try:
            detail = ReportDetail.model_validate(body)
        except Exception:
            # Malformed v3 fails safely without becoming a new report.
            return None
        detail.id = row.id
        return detail
    return body


def is_legacy_stored_report(value: ReportDetail | dict[str, Any]) -> bool:
    if isinstance(value, ReportDetail):
        return value.report_version < 3
    return stored_report_version(value) < 3


def legacy_report_format(value: dict[str, Any]) -> str:
    raw = value.get("format") or "json"
    return str(raw)


def legacy_markdown(value: dict[str, Any]) -> str:
    return str(value.get("markdown_summary") or "")
