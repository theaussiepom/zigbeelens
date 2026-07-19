"""Canonical request-local network decision projection (Track 5 seal).

Pure composition over already-loaded facts — no repository access.
Used by Dashboard, Networks collection/detail, reports, and mock projections.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import (
    BridgeState,
    CoordinatorSummary,
    DataCoverageWarningSummary,
    DecisionCountSummary,
    DeviceDecisionBadge,
    InvestigationPrioritySummary,
    NetworkSummary,
    Severity,
)
from zigbeelens.services.decision_summary import (
    DECISION_STATUS_ORDER,
    decision_count_summary_from_badges,
    network_decision_badge_from_summary,
)
from zigbeelens.services.report_active_severity import pick_active_incident_severity
from zigbeelens.storage.repository import DeviceRow, NetworkRow

# Network headline promotion precedence (documented):
# 1. device-badge overall status is the baseline subject_count fold;
# 2. an active incident not already represented by a stronger device badge
#    must not leave the network as no_notable_change;
# 3. a review_first investigation priority must not leave no_notable_change;
# 4. actionable coverage warnings promote improve_data_coverage when weaker;
# 5. empty/unobserved networks remain data_unavailable.


def _promote(
    current: DecisionStatus,
    candidate: DecisionStatus,
) -> DecisionStatus:
    order = {status: index for index, status in enumerate(DECISION_STATUS_ORDER)}
    if order.get(candidate, 99) < order.get(current, 99):
        return candidate
    return current


def compose_network_decision(
    *,
    device_badges: Sequence[DeviceDecisionBadge],
    coverage_warning_count: int = 0,
    has_active_incident: bool = False,
    has_review_first_priority: bool = False,
) -> tuple[DeviceDecisionBadge, DecisionCountSummary]:
    """Fold device badges + network facts into one network decision pair."""
    summary = decision_count_summary_from_badges(
        device_badges,
        coverage_warning_count=coverage_warning_count,
    )
    if summary.subject_count == 0 and not has_active_incident:
        # Empty / unobserved network.
        empty = DecisionCountSummary(
            subject_count=0,
            overall_status=DecisionStatus.data_unavailable,
            highest_priority=DecisionPriority.none,
            status_counts={},
            priority_counts={},
            coverage_warning_count=coverage_warning_count,
        )
        return network_decision_badge_from_summary(empty), empty

    overall = summary.overall_status
    if isinstance(overall, str):
        overall = DecisionStatus(overall)

    if has_active_incident:
        overall = _promote(overall, DecisionStatus.worth_reviewing)
    if has_review_first_priority:
        overall = _promote(overall, DecisionStatus.review_first)
    if coverage_warning_count > 0:
        overall = _promote(overall, DecisionStatus.improve_data_coverage)

    adjusted = DecisionCountSummary(
        subject_count=summary.subject_count,
        overall_status=overall,
        highest_priority=summary.highest_priority,
        status_counts=summary.status_counts,
        priority_counts=summary.priority_counts,
        coverage_warning_count=coverage_warning_count,
    )
    return network_decision_badge_from_summary(adjusted), adjusted


def compose_network_summary(
    row: NetworkRow,
    *,
    device_rows: Sequence[DeviceRow],
    device_decision_badges: Sequence[DeviceDecisionBadge],
    active_incident_count: int,
    active_incident_severity: Severity | None,
    coverage_warning_count: int,
    investigation_priorities: Sequence[InvestigationPrioritySummary] = (),
    coordinator: CoordinatorSummary | None = None,
    recent_bridge_warnings: int = 0,
    recent_bridge_errors: int = 0,
) -> NetworkSummary:
    """Build one NetworkSummary from already-loaded facts (no repository reads)."""
    bridge = (
        BridgeState(row.bridge_state)
        if row.bridge_state in {s.value for s in BridgeState}
        else BridgeState.unknown
    )
    routers = sum(1 for d in device_rows if d.device_type == "Router")
    ends = sum(1 for d in device_rows if d.device_type == "EndDevice")
    unavailable = sum(1 for d in device_rows if d.availability == "offline")

    has_review_first = any(
        p.network_id == row.id and str(p.priority) == "Review first"
        for p in investigation_priorities
    )
    decision, decision_summary = compose_network_decision(
        device_badges=device_decision_badges,
        coverage_warning_count=coverage_warning_count,
        has_active_incident=active_incident_count > 0,
        has_review_first_priority=has_review_first,
    )
    return NetworkSummary(
        id=row.id,
        name=row.name,
        base_topic=row.base_topic,
        bridge_state=bridge,
        coordinator=coordinator,
        device_count=len(device_rows),
        router_count=routers,
        end_device_count=ends,
        unavailable_count=unavailable,
        active_incident_severity=active_incident_severity,
        active_incident_count=active_incident_count,
        recent_bridge_warnings=recent_bridge_warnings,
        recent_bridge_errors=recent_bridge_errors,
        decision=decision,
        decision_summary=decision_summary,
    )


def coverage_counts_by_network(
    warnings: Iterable[DataCoverageWarningSummary],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for warning in warnings:
        counts[warning.network_id] = counts.get(warning.network_id, 0) + 1
    return counts


def priorities_by_network(
    priorities: Iterable[InvestigationPrioritySummary],
) -> dict[str, list[InvestigationPrioritySummary]]:
    grouped: dict[str, list[InvestigationPrioritySummary]] = {}
    for item in priorities:
        grouped.setdefault(item.network_id, []).append(item)
    return grouped


def severity_from_active_context(
    network_id: str,
    *,
    active_severity_by_network_id: Mapping[str, Severity] | None,
) -> Severity | None:
    if not active_severity_by_network_id:
        return None
    return active_severity_by_network_id.get(network_id)


def pick_network_active_incident_severity(
    active_rows_for_network: Sequence,
) -> Severity | None:
    """Factual active-incident severity for one network (open before watching)."""
    return pick_active_incident_severity(list(active_rows_for_network))
