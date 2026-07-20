"""Generic decision-engine types shared across ZigbeeLens surfaces."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DecisionStatus(StrEnum):
    informational = "informational"
    no_notable_change = "no_notable_change"
    changed = "changed"
    watch = "watch"
    worth_reviewing = "worth_reviewing"
    review_first = "review_first"
    improve_data_coverage = "improve_data_coverage"
    data_unavailable = "data_unavailable"


class DecisionPriority(StrEnum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


# Deterministic fold order for DecisionCountSummary.overall_status (first match wins).
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

# Deterministic fold order for DecisionCountSummary.highest_priority (first match wins).
DECISION_PRIORITY_ORDER: tuple[DecisionPriority, ...] = (
    DecisionPriority.high,
    DecisionPriority.medium,
    DecisionPriority.low,
    DecisionPriority.none,
)


class CoverageDimension(StrEnum):
    availability = "availability"
    last_seen = "last_seen"
    last_payload = "last_payload"
    battery = "battery"
    linkquality = "linkquality"
    topology_snapshot = "topology_snapshot"
    route_hints = "route_hints"
    historical_snapshots = "historical_snapshots"
    passive_history = "passive_history"
    ha_enrichment = "ha_enrichment"
    incidents = "incidents"
    reports = "reports"


class CoverageState(StrEnum):
    available = "available"
    off = "off"
    building = "building"
    unknown = "unknown"
    stale = "stale"
    not_configured = "not_configured"
    not_observed = "not_observed"
    sparse = "sparse"


class CoverageLabelCode(StrEnum):
    """Stable presenter codes for coverage labels — not final user prose."""

    availability_tracking_off = "availability_tracking_off"
    availability_history_building = "availability_history_building"
    availability_status_unknown = "availability_status_unknown"
    availability_available = "availability_available"
    route_hints_unavailable = "route_hints_unavailable"
    ha_areas_not_linked = "ha_areas_not_linked"
    snapshot_stale = "snapshot_stale"
    battery_history_sparse = "battery_history_sparse"
    lqi_history_sparse = "lqi_history_sparse"
    last_seen_available = "last_seen_available"
    last_seen_unknown = "last_seen_unknown"
    last_payload_available = "last_payload_available"
    last_payload_unknown = "last_payload_unknown"
    battery_history_available = "battery_history_available"
    lqi_history_available = "lqi_history_available"
    topology_history_available = "topology_history_available"
    topology_history_sparse = "topology_history_sparse"
    topology_history_not_observed = "topology_history_not_observed"
    ha_area_linked = "ha_area_linked"


class EvidenceFact(BaseModel):
    """Neutral statement derived from stored evidence — not a decision."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvidenceReference(BaseModel):
    """Pointer to supporting stored evidence."""

    source: str
    id: str | None = None
    captured_at: datetime | None = None
    label: str | None = None


class DecisionReason(BaseModel):
    """Structured reason for a decision — copy is mapped by presenters."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class DecisionLimitation(BaseModel):
    """What the evidence cannot prove or why interpretation is constrained."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class SuggestedCheck(BaseModel):
    """Practical, non-causal next action suggested from evidence."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class DataCoverage(BaseModel):
    """Structured statement about whether enough data exists for a decision."""

    dimension: CoverageDimension
    state: CoverageState
    label_code: CoverageLabelCode
    params: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    """Reusable diagnostic judgement for a subject."""

    subject_type: str
    subject_id: str
    status: DecisionStatus
    priority: DecisionPriority = DecisionPriority.none
    reasons: list[DecisionReason] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[DecisionLimitation] = Field(default_factory=list)
    suggested_checks: list[SuggestedCheck] = Field(default_factory=list)
    coverage: list[DataCoverage] = Field(default_factory=list)


class DecisionBundle(BaseModel):
    """Grouped decisions for one subject, e.g. device story or investigation card."""

    subject_type: str
    subject_id: str
    decisions: list[Decision] = Field(default_factory=list)


class InvestigationActionGroup(StrEnum):
    """Action-led grouping for problem-first investigation cards."""

    check_power_reporting = "check_power_reporting"
    review_observed_router_area = "review_observed_router_area"
    review_model_pattern = "review_model_pattern"
    investigate_shared_event = "investigate_shared_event"
    improve_data_coverage = "improve_data_coverage"
    watch_only = "watch_only"
