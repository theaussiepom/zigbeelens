from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from zigbeelens.config.security_types import SecurityMode
from zigbeelens.decisions.types import (
    DECISION_PRIORITY_ORDER,
    DECISION_STATUS_ORDER,
    CoverageLabelCode,
    DecisionPriority,
    DecisionStatus,
)


class Severity(str, Enum):
    healthy = "healthy"
    watch = "watch"
    incident = "incident"
    critical = "critical"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class IncidentScope(str, Enum):
    device = "device"
    router_candidate = "router_candidate"
    mesh_segment = "mesh_segment"
    network = "network"
    multi_network = "multi_network"
    unknown = "unknown"


class IncidentStatus(str, Enum):
    open = "open"
    watching = "watching"
    resolved = "resolved"


class DeviceHealthPrimary(str, Enum):
    healthy = "healthy"
    unavailable = "unavailable"
    recently_unstable = "recently_unstable"
    weak_link = "weak_link"
    low_battery = "low_battery"
    stale_reporting = "stale_reporting"
    interview_issue = "interview_issue"
    router_risk = "router_risk"
    unknown = "unknown"


class BridgeState(str, Enum):
    online = "online"
    offline = "offline"
    unknown = "unknown"


class DeviceType(str, Enum):
    Coordinator = "Coordinator"
    Router = "Router"
    EndDevice = "EndDevice"
    Unknown = "Unknown"


class PowerSource(str, Enum):
    Battery = "Battery"
    Mains = "Mains"
    Unknown = "Unknown"


class Availability(str, Enum):
    online = "online"
    offline = "offline"
    unknown = "unknown"


class InterviewState(str, Enum):
    successful = "successful"
    failed = "failed"
    in_progress = "in_progress"
    unknown = "unknown"


class EvidenceItem(BaseModel):
    id: str
    kind: str
    summary: str
    detail: str | None = None
    timestamp: str | None = None
    network_id: str | None = None
    ieee_address: str | None = None


class LimitationItem(BaseModel):
    id: str
    summary: str
    detail: str | None = None


class DiagnosticConclusion(BaseModel):
    classification: str
    severity: Severity
    scope: IncidentScope
    confidence: Confidence
    summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[LimitationItem] = Field(default_factory=list)


class DeviceHealth(BaseModel):
    primary: DeviceHealthPrimary
    severity: Severity
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    flags: list[DeviceHealthPrimary] = Field(default_factory=list)


class CoordinatorSummary(BaseModel):
    ieee_address: str
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    channel: int | None = None
    pan_id: str | None = None
    extended_pan_id: str | None = None


class DeviceDecisionBadge(BaseModel):
    """Compact decision projection for inventory/list surfaces."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    status: DecisionStatus
    priority: DecisionPriority
    headline_code: str
    coverage_label_codes: list[CoverageLabelCode] = Field(default_factory=list)


# Public alias — same compact badge shape for devices and networks.
DecisionBadge = DeviceDecisionBadge


class DecisionCountSummary(BaseModel):
    """Pure aggregate of represented subject decision badges.

    Must not carry independently promoted network-level judgement. Counts are
    strict non-negative integers (no bool / float / numeric string coercion).
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    subject_count: StrictInt = Field(ge=0)
    overall_status: DecisionStatus
    highest_priority: DecisionPriority
    status_counts: dict[DecisionStatus, StrictInt] = Field(default_factory=dict)
    priority_counts: dict[DecisionPriority, StrictInt] = Field(default_factory=dict)
    coverage_warning_count: StrictInt = Field(default=0, ge=0)

    @field_validator("subject_count", "coverage_warning_count", mode="before")
    @classmethod
    def _strict_nonneg_int(cls, value: Any) -> Any:
        if isinstance(value, bool) or type(value) is not int:
            raise ValueError("count must be a non-negative integer")
        if value < 0:
            raise ValueError("count must be a non-negative integer")
        return value

    @field_validator("status_counts", "priority_counts", mode="before")
    @classmethod
    def _strict_count_maps(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        for key, count in value.items():
            if isinstance(count, bool) or type(count) is not int or count < 0:
                raise ValueError(f"invalid count for {key!r}")
        return value

    @model_validator(mode="after")
    def _pure_count_fold_invariants(self) -> DecisionCountSummary:
        status_total = sum(self.status_counts.values())
        priority_total = sum(self.priority_counts.values())
        if self.subject_count == 0:
            if self.status_counts or self.priority_counts:
                raise ValueError("empty subject_count requires empty count maps")
            if self.overall_status != DecisionStatus.data_unavailable:
                raise ValueError(
                    "empty subject_count requires overall_status=data_unavailable"
                )
            if self.highest_priority != DecisionPriority.none:
                raise ValueError("empty subject_count requires highest_priority=none")
            return self
        if status_total != self.subject_count:
            raise ValueError("sum(status_counts) must equal subject_count")
        if priority_total != self.subject_count:
            raise ValueError("sum(priority_counts) must equal subject_count")

        expected_overall = DecisionStatus.data_unavailable
        for status in DECISION_STATUS_ORDER:
            if self.status_counts.get(status, 0) > 0:
                expected_overall = status
                break
        if self.overall_status != expected_overall:
            raise ValueError("overall_status must match DECISION_STATUS_ORDER fold")

        expected_priority = DecisionPriority.none
        for priority in DECISION_PRIORITY_ORDER:
            if self.priority_counts.get(priority, 0) > 0:
                expected_priority = priority
                break
        if self.highest_priority != expected_priority:
            raise ValueError("highest_priority must match DECISION_PRIORITY_ORDER fold")
        return self


class NetworkSummary(BaseModel):
    id: str
    name: str
    base_topic: str
    bridge_state: BridgeState
    coordinator: CoordinatorSummary | None = None
    device_count: int
    router_count: int
    end_device_count: int
    unavailable_count: int
    active_incident_severity: Severity | None = None
    active_incident_count: int
    recent_bridge_warnings: int = 0
    recent_bridge_errors: int = 0
    decision: DeviceDecisionBadge
    decision_summary: DecisionCountSummary


class AvailabilityChange(BaseModel):
    timestamp: str
    from_state: Availability = Field(alias="from")
    to: Availability

    model_config = {"populate_by_name": True}


class BridgeLogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


class DeviceTrendPoint(BaseModel):
    timestamp: str
    linkquality: int | None = None
    battery: int | None = None
    availability: Availability | None = None


class DeviceSummary(BaseModel):
    network_id: str
    ieee_address: str
    friendly_name: str
    device_type: DeviceType
    power_source: PowerSource
    availability: Availability
    last_seen: str | None = None
    last_payload_at: str | None = None
    linkquality: int | None = None
    battery: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    interview_state: InterviewState
    incident_affected: bool = False
    decision: DeviceDecisionBadge
    ha_area: str | None = None


class DeviceDetail(DeviceSummary):
    definition: str | None = None
    supported: bool | None = None
    recent_availability_changes: list[AvailabilityChange] = Field(default_factory=list)
    recent_events: list[TimelineEvent] = Field(default_factory=list)
    recent_bridge_logs: list[BridgeLogEntry] = Field(default_factory=list)
    trends: list[DeviceTrendPoint] = Field(default_factory=list)


class RouterRisk(BaseModel):
    network_id: str
    ieee_address: str
    friendly_name: str
    availability: Availability
    linkquality: int | None = None
    last_seen: str | None = None
    possibly_dependent_devices: int | None = None
    correlated_affected_devices: int
    risk: DiagnosticConclusion


class IncidentDeviceRef(BaseModel):
    network_id: str
    ieee_address: str
    friendly_name: str
    decision: DeviceDecisionBadge


class TimelineEvent(BaseModel):
    id: str
    timestamp: str
    kind: str
    severity: Severity
    network_id: str | None = None
    ieee_address: str | None = None
    friendly_name: str | None = None
    title: str
    summary: str
    incident_id: str | None = None


class Incident(BaseModel):
    id: str
    type: str
    status: IncidentStatus
    severity: Severity
    scope: IncidentScope
    confidence: Confidence
    title: str
    summary: str
    interpretation: str
    network_ids: list[str]
    affected_device_count: int
    affected_devices: list[IncidentDeviceRef]
    opened_at: str
    updated_at: str
    resolved_at: str | None = None
    evidence: list[EvidenceItem]
    counter_evidence: list[EvidenceItem]
    limitations: list[LimitationItem]
    timeline: list[TimelineEvent]
    conclusion: DiagnosticConclusion


class HealthSnapshot(BaseModel):
    timestamp: str
    overall_severity: Severity
    overall_health: DeviceHealthPrimary
    network_count: int
    device_count: int
    unavailable_count: int
    incident_count: int
    networks: list[dict[str, Any]]


class SharedAvailabilityEventSummary(BaseModel):
    """Facts-only shared availability event for dashboard Overview."""

    event_id: str
    network_id: str
    started_at: str
    ended_at: str
    device_count: int
    duration_minutes: int
    device_ieees: list[str] = Field(default_factory=list)


class ModelPatternSummary(BaseModel):
    """Facts-only model pattern for dashboard Overview."""

    pattern_id: str
    network_id: str
    manufacturer: str | None = None
    model: str
    group_size: int
    affected_count: int
    lookback_days: int
    affected_device_ieees: list[str] = Field(default_factory=list)
    latest_supporting_evidence_at: str | None = None


class InvestigationPrioritySummary(BaseModel):
    """Top mesh investigation card flattened for dashboard Overview."""

    id: str
    network_id: str
    card_type: str
    priority: str
    score: int
    action_group: str
    title: str
    summary: str
    device_ieees: list[str] = Field(default_factory=list)
    latest_supporting_evidence_at: str | None = None


class DataCoverageWarningSummary(BaseModel):
    """Overview-relevant coverage limitation from stored evidence evaluators."""

    id: str
    network_id: str
    dimension: str
    state: str
    label_code: str
    scope_type: str = "network"
    params: dict[str, Any] = Field(default_factory=dict)


class DashboardPayload(BaseModel):
    generated_at: str
    scenario: str | None = None
    active_incident_count: int
    watching_incident_count: int
    network_count: int = 0
    device_count: int = 0
    unavailable_device_count: int = 0
    networks: list[NetworkSummary]
    router_risks: list[RouterRisk]
    recent_timeline: list[TimelineEvent]
    decision_summary: DecisionCountSummary
    shared_availability_events: list[SharedAvailabilityEventSummary] = Field(default_factory=list)
    model_patterns: list[ModelPatternSummary] = Field(default_factory=list)
    investigation_priorities: list[InvestigationPrioritySummary] = Field(default_factory=list)
    data_coverage_warnings: list[DataCoverageWarningSummary] = Field(default_factory=list)


class RedactionProfile(str, Enum):
    standard = "standard"
    strict = "strict"
    public_safe = "public_safe"


class ReportScope(str, Enum):
    full = "full"
    incident = "incident"
    network = "network"
    device = "device"


class ReportFormat(str, Enum):
    json = "json"
    yaml = "yaml"
    markdown = "markdown"


class RedactionOptions(BaseModel):
    """Per-request redaction overrides. None means "use profile default"."""

    profile: RedactionProfile = RedactionProfile.standard
    preserve_friendly_names: bool | None = None
    hash_ieee_addresses: bool | None = None
    redact_hostnames: bool | None = None
    redact_ip_addresses: bool | None = None
    redact_network_names: bool | None = None
    include_timeline: bool | None = None
    include_raw_payloads: bool | None = None


class ReportRequest(BaseModel):
    format: ReportFormat = ReportFormat.json
    scope: ReportScope = ReportScope.full
    incident_id: str | None = None
    network_id: str | None = None
    device: str | None = None
    redaction: RedactionOptions = Field(default_factory=RedactionOptions)


class ReportRedactionStatus(BaseModel):
    applied: bool
    profile: str = "standard"
    mqtt_credentials: bool = True
    secrets: bool = True
    hostnames: bool = False
    ip_addresses: bool = False
    ieee_addresses_hashed: bool = False
    friendly_names: str = "preserved"
    network_names: str = "preserved"


class ReportSummary(BaseModel):
    id: str
    generated_at: str
    redaction_applied: bool
    incident_count: int
    device_count: int
    network_count: int
    summary: str
    format: str = "json"
    scope: str = "full"
    redaction_profile: str = "standard"


class ReportDecisionSummary(BaseModel):
    """Factual Device Story decision counts for a report scope (Phase 5D)."""

    device_story_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    priority_counts: dict[str, int] = Field(default_factory=dict)


class ReportStoryTimelineItem(BaseModel):
    """Report-compatible Device Story timeline item (avoids schema cycle)."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str | None = None


class ReportDeviceStory(BaseModel):
    """Canonical Device Story payload plus report identity fields."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    network_id: str
    ieee_address: str
    friendly_name: str

    subject_type: str = "device"
    subject_id: str
    status: DecisionStatus
    priority: DecisionPriority
    headline_code: str

    reasons: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)
    suggested_checks: list[dict[str, Any]] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    related_unresolved_incident_ids: list[str] = Field(default_factory=list)
    timeline: list[ReportStoryTimelineItem] = Field(default_factory=list)


class ReportDomainDetailsV3(BaseModel):
    """Exact v3 domain inventory for one report scope."""

    model_config = ConfigDict(extra="forbid")

    networks: list[NetworkSummary] = Field(default_factory=list)
    devices: list[DeviceSummary] = Field(default_factory=list)
    device_details: list[DeviceDetail] = Field(default_factory=list)
    router_risks: list[RouterRisk] = Field(default_factory=list)
    topology_snapshot_count: int = 0


# Compatibility alias used by helpers during the Track 5 seal.
ReportDomainDetails = ReportDomainDetailsV3


class ReportDetailV3(BaseModel):
    """Exact current report contract (version 3). No legacy aliases."""

    model_config = ConfigDict(extra="forbid")

    id: str
    product: str = "ZigbeeLens"
    report_version: Literal[3] = 3
    generated_at: str
    version: str
    scope: str = "full"
    format: str = "json"
    redaction: ReportRedactionStatus
    config_summary: dict[str, Any] = Field(default_factory=dict)
    decision_summary: DecisionCountSummary
    investigation_priorities: list[InvestigationPrioritySummary] = Field(default_factory=list)
    device_stories: list[ReportDeviceStory] = Field(default_factory=list)
    data_coverage_warnings: list[DataCoverageWarningSummary] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    collector_status: dict[str, Any] = Field(default_factory=dict)
    domain_details: ReportDomainDetailsV3 = Field(default_factory=ReportDomainDetailsV3)
    events_or_timeline: list[TimelineEvent] = Field(default_factory=list)
    limitations: list[LimitationItem] = Field(default_factory=list)
    raw_counts: dict[str, int] = Field(default_factory=dict)
    markdown_summary: str = ""


# Current writers and OpenAPI advertise ReportDetail as the exact v3 model.
ReportDetail = ReportDetailV3


class BrowserSessionStatus(BaseModel):
    """Public browser-session status projection (no secrets or session IDs)."""

    model_config = ConfigDict(extra="forbid")

    authenticated: bool
    auth_method: Literal[
        "trusted_local", "bearer", "session", "home_assistant_ingress"
    ] | None
    browser_session_enabled: bool
    home_assistant_ingress_enabled: bool = False
    expires_at: str | None = None
    csrf_token: str | None = Field(default=None, repr=False)


class SecurityConfigStatus(BaseModel):
    """Secret-free security posture metadata for config/status responses."""

    mode: SecurityMode
    loopback_bind: bool
    api_token_configured: bool
    session_secret_configured: bool
    bearer_auth_enabled: bool
    browser_session_enabled: bool = False
    csrf_protection_enabled: bool = False
    session_cookie_secure: bool = False
    read_routes_require_authentication: bool = False
    mutation_routes_require_authentication: bool = False
    # Deprecated: true only when auth is required and browser sessions are off.
    read_routes_require_bearer: bool
    # Deprecated: true only when auth is required and browser sessions are off.
    mutation_routes_require_bearer: bool
    ingress_identity_enforced: bool = False
    ingress_trusted_proxy_count: int = 0
    ingress_proxy_only: bool = False
    ingress_bearer_fallback_enabled: bool = False
    trusted_local_open: bool
    # Deprecated: Track 4A mutation-only guard. Always false under bearer policy.
    legacy_mutation_guard_enabled: bool = False
    cors_allowed_origins_count: int = 0
    credentialed_cors_enabled: bool = False
    frame_ancestor_origins_count: int = 0
    external_framing_enabled: bool = False
    content_security_policy_enabled: bool = True
    session_origin_validation_enabled: bool = False


class ZigbeeLensConfigStatus(BaseModel):
    version: str
    uptime_seconds: int
    mqtt_connected: bool
    mqtt_server: str
    configured_networks: list[dict[str, str]]
    storage_path: str
    storage_ready: bool = False
    retention_days: int
    features: dict[str, bool]
    mqtt_discovery: dict[str, bool | str] = Field(default_factory=dict)
    topology: dict[str, bool | int] = Field(default_factory=dict)
    diagnostics: dict[str, int | float] = Field(default_factory=dict)
    data_mode: str
    mock_mode: bool = False
    active_scenario: str | None = None
    security: SecurityConfigStatus


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: int
    config_loaded: bool
    mock_mode: bool
    database: str
    migration_version: int
    collector: dict[str, Any] = Field(default_factory=dict)
    mqtt_discovery: dict[str, Any] = Field(default_factory=dict)
    topology: dict[str, Any] = Field(default_factory=dict)
    home_assistant_enrichment: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    limit: int | None = None
    next_cursor: str | None = None


class TopologyCaptureRequest(BaseModel):
    confirmed: StrictBool
    reason: str | None = None
