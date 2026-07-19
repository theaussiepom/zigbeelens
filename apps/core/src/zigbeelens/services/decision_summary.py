"""Aggregate DecisionCountSummary from compact decision badges."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import DecisionCountSummary, DeviceDecisionBadge

# Deterministic public overall-status order (first match wins for "worst").
DECISION_STATUS_ORDER: tuple[DecisionStatus, ...] = (
    DecisionStatus.review_first,
    DecisionStatus.worth_reviewing,
    DecisionStatus.improve_data_coverage,
    DecisionStatus.watch,
    DecisionStatus.changed,
    DecisionStatus.informational,
    DecisionStatus.no_notable_change,
    DecisionStatus.data_unavailable,
)

_PRIORITY_ORDER: tuple[DecisionPriority, ...] = (
    DecisionPriority.high,
    DecisionPriority.medium,
    DecisionPriority.low,
    DecisionPriority.none,
)

_NETWORK_HEADLINE_BY_STATUS: dict[DecisionStatus, str] = {
    DecisionStatus.review_first: "network_review_first",
    DecisionStatus.worth_reviewing: "network_worth_reviewing",
    DecisionStatus.improve_data_coverage: "network_improve_data_coverage",
    DecisionStatus.watch: "network_watch",
    DecisionStatus.changed: "network_watch",
    DecisionStatus.informational: "network_no_notable_change",
    DecisionStatus.no_notable_change: "network_no_notable_change",
    DecisionStatus.data_unavailable: "network_data_unavailable",
}


def _as_status(value: DecisionStatus | str) -> DecisionStatus:
    return value if isinstance(value, DecisionStatus) else DecisionStatus(str(value))


def _as_priority(value: DecisionPriority | str) -> DecisionPriority:
    return value if isinstance(value, DecisionPriority) else DecisionPriority(str(value))


def decision_count_summary_from_badges(
    badges: Iterable[DeviceDecisionBadge],
    *,
    coverage_warning_count: int = 0,
) -> DecisionCountSummary:
    """Fold badges into a DecisionCountSummary without repository access."""
    badge_list = [b for b in badges if b is not None]
    if not badge_list:
        return DecisionCountSummary(
            subject_count=0,
            overall_status=DecisionStatus.data_unavailable,
            highest_priority=DecisionPriority.none,
            status_counts={},
            priority_counts={},
            coverage_warning_count=coverage_warning_count,
        )

    status_counts: Counter[DecisionStatus] = Counter(
        _as_status(b.status) for b in badge_list
    )
    priority_counts: Counter[DecisionPriority] = Counter(
        _as_priority(b.priority) for b in badge_list
    )

    overall = DecisionStatus.data_unavailable
    for status in DECISION_STATUS_ORDER:
        if status_counts.get(status, 0) > 0:
            overall = status
            break

    highest = DecisionPriority.none
    for priority in _PRIORITY_ORDER:
        if priority_counts.get(priority, 0) > 0:
            highest = priority
            break

    return DecisionCountSummary(
        subject_count=len(badge_list),
        overall_status=overall,
        highest_priority=highest,
        status_counts=dict(sorted(status_counts.items(), key=lambda item: item[0].value)),
        priority_counts=dict(
            sorted(priority_counts.items(), key=lambda item: item[0].value)
        ),
        coverage_warning_count=coverage_warning_count,
    )


def network_decision_badge_from_summary(
    summary: DecisionCountSummary,
) -> DeviceDecisionBadge:
    """Project a network DecisionCountSummary onto a compact decision badge."""
    status = _as_status(summary.overall_status)
    headline = _NETWORK_HEADLINE_BY_STATUS.get(status, "network_data_unavailable")
    return DeviceDecisionBadge(
        status=status,
        priority=_as_priority(summary.highest_priority),
        headline_code=headline,
        coverage_label_codes=[],
    )


def data_unavailable_device_badge() -> DeviceDecisionBadge:
    """Canonical badge when a Device Story cannot be composed."""
    return DeviceDecisionBadge(
        status=DecisionStatus.data_unavailable,
        priority=DecisionPriority.none,
        headline_code="device_data_unavailable",
        coverage_label_codes=[],
    )
