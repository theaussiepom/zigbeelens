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
    route_hints_unavailable = "route_hints_unavailable"
    ha_areas_not_linked = "ha_areas_not_linked"
    snapshot_stale = "snapshot_stale"
    battery_history_sparse = "battery_history_sparse"
    lqi_history_sparse = "lqi_history_sparse"


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
    investigate_shared_event = "investigate_shared_event"
    improve_data_coverage = "improve_data_coverage"
    watch_only = "watch_only"
