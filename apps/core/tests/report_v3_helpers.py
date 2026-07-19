"""Helpers for report tests after the exact v3 decision-only contract."""

from __future__ import annotations

from typing import Any

from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import (
    DecisionCountSummary,
    ReportDetailV3,
    ReportDomainDetailsV3,
    ReportRedactionStatus,
)


def empty_decision_summary(*, coverage_warning_count: int = 0) -> DecisionCountSummary:
    return DecisionCountSummary(
        subject_count=0,
        overall_status=DecisionStatus.data_unavailable,
        highest_priority=DecisionPriority.none,
        status_counts={},
        priority_counts={},
        coverage_warning_count=coverage_warning_count,
    )


def minimal_report_v3(**overrides: Any) -> ReportDetailV3:
    """Build a valid exact ReportDetailV3 for unit tests."""
    base: dict[str, Any] = {
        "id": "r",
        "product": "ZigbeeLens",
        "report_version": 3,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "version": "0.1.0",
        "scope": "full",
        "format": "json",
        "redaction": ReportRedactionStatus(
            applied=True, profile="standard", mqtt_credentials=True
        ),
        "config_summary": {"mode": "mock"},
        "decision_summary": empty_decision_summary(),
        "investigation_priorities": [],
        "device_stories": [],
        "data_coverage_warnings": [],
        "incidents": [],
        "collector_status": {},
        "domain_details": ReportDomainDetailsV3(),
        "events_or_timeline": [],
        "limitations": [],
        "raw_counts": {},
        "markdown_summary": "",
    }
    base.update(overrides)
    return ReportDetailV3.model_validate(base)


def _domain(detail: ReportDetailV3 | dict[str, Any]) -> ReportDomainDetailsV3 | dict[str, Any]:
    if isinstance(detail, dict):
        return detail.get("domain_details") or {}
    return detail.domain_details


def _domain_list(domain: ReportDomainDetailsV3 | dict[str, Any], key: str):
    if isinstance(domain, ReportDomainDetailsV3):
        return getattr(domain, key) or []
    return domain.get(key) or []


def report_networks(detail: ReportDetailV3 | dict[str, Any]):
    return _domain_list(_domain(detail), "networks")


def report_devices(detail: ReportDetailV3 | dict[str, Any]):
    return _domain_list(_domain(detail), "devices")


def report_device_details(detail: ReportDetailV3 | dict[str, Any]):
    return _domain_list(_domain(detail), "device_details")


def report_router_risks(detail: ReportDetailV3 | dict[str, Any]):
    return _domain_list(_domain(detail), "router_risks")


def report_timeline(detail: ReportDetailV3 | dict[str, Any]):
    if isinstance(detail, dict):
        return detail.get("events_or_timeline") or []
    return detail.events_or_timeline


def report_active_incidents(detail: ReportDetailV3 | dict[str, Any]):
    """Active (non-resolved) incidents from the canonical incidents list."""
    if isinstance(detail, dict):
        incidents = detail.get("incidents") or []
        out = []
        for inc in incidents:
            status = inc.get("status") if isinstance(inc, dict) else getattr(inc, "status", None)
            value = getattr(status, "value", status)
            if value != "resolved":
                out.append(inc)
        return out
    return [inc for inc in detail.incidents if str(inc.status.value) != "resolved"]
