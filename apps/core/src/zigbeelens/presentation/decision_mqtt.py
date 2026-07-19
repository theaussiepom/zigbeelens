"""Decision-contract-v2 MQTT Discovery summary presentation.

Builds summary entity states from Dashboard DecisionCountSummary and factual
counts. Does not re-run decision logic or perform repository reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zigbeelens.schemas import DashboardPayload
from zigbeelens.storage.repository import utc_now_iso

PRODUCT = "zigbeelens"
REDACTION_PROFILE = "public_safe"

# Retained for factual continuity with the previous Lens `unavailable` entity.
UNAVAILABLE_ENTITY_KEY = "unavailable"


@dataclass(frozen=True)
class SummaryEntityState:
    key: str
    name: str
    state: str
    attributes: dict[str, Any]


def count_state(value: int | str | None, *, observable: bool) -> str:
    """Unknown when unobservable; otherwise a decimal count including zero."""
    if not observable:
        return "unknown"
    if value is None:
        return "unknown"
    return str(int(value))


def _status_count(dashboard: DashboardPayload, status: str) -> int:
    counts = dashboard.decision_summary.status_counts or {}
    try:
        return int(counts.get(status, 0))
    except (TypeError, ValueError):
        return 0


def build_summary_entities(
    dashboard: DashboardPayload,
    *,
    core_version: str,
    collector_connected: bool,
    mock_mode: bool,
) -> list[SummaryEntityState]:
    observable = mock_mode or collector_connected
    summary = dashboard.decision_summary
    overall = (
        str(summary.overall_status)
        if observable
        else "data_unavailable"
    )
    generated_at = utc_now_iso()
    coverage = int(summary.coverage_warning_count or 0)
    if coverage == 0 and dashboard.data_coverage_warnings:
        coverage = len(dashboard.data_coverage_warnings)

    base_attrs = {
        "product": PRODUCT,
        "version": core_version,
        "decision_contract_version": 2,
        "overall_decision_status": overall,
        "highest_priority": str(summary.highest_priority),
        "status_counts": dict(summary.status_counts or {}),
        "priority_counts": dict(summary.priority_counts or {}),
        "coverage_warning_count": coverage if observable else "unknown",
        "active_incident_count": (
            int(dashboard.active_incident_count) if observable else "unknown"
        ),
        "unavailable_device_count": (
            int(dashboard.unavailable_device_count) if observable else "unknown"
        ),
        "generated_at": generated_at,
        "collector_connected": collector_connected,
        "observation_reliable": observable,
        "redaction_profile": REDACTION_PROFILE,
    }

    return [
        SummaryEntityState(
            key="decision_status",
            name="ZigbeeLens Decision Status",
            state=overall,
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="review_first",
            name="ZigbeeLens Review First",
            state=count_state(_status_count(dashboard, "review_first"), observable=observable),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="worth_reviewing",
            name="ZigbeeLens Worth Reviewing",
            state=count_state(
                _status_count(dashboard, "worth_reviewing"), observable=observable
            ),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="coverage_warnings",
            name="ZigbeeLens Coverage Warnings",
            state=count_state(coverage, observable=observable),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key="active_incidents",
            name="ZigbeeLens Active Incidents",
            state=count_state(dashboard.active_incident_count, observable=observable),
            attributes=base_attrs,
        ),
        SummaryEntityState(
            key=UNAVAILABLE_ENTITY_KEY,
            name="ZigbeeLens Unavailable Devices",
            state=count_state(dashboard.unavailable_device_count, observable=observable),
            attributes=base_attrs,
        ),
    ]
