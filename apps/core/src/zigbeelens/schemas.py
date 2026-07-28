from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
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


HOME_ASSISTANT_ENRICHMENT_CONTRACT_VERSION = 1
HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES = 5000


class HomeAssistantEnrichmentDeviceV1(BaseModel):
    """One exact Home Assistant registry row linked to a Core device identity."""

    model_config = ConfigDict(extra="forbid")

    network_id: StrictStr = Field(min_length=1, max_length=128)
    ieee_address: StrictStr = Field(
        min_length=18,
        max_length=18,
        pattern=r"^0x[0-9a-f]{16}$",
    )
    ha_device_id: StrictStr = Field(min_length=1, max_length=255)
    ha_device_name: StrictStr | None = Field(default=None, max_length=255)
    area_id: StrictStr | None = Field(default=None, max_length=255)
    area_name: StrictStr | None = Field(default=None, max_length=255)
    entity_id: StrictStr | None = Field(default=None, max_length=255)

    @field_validator("network_id", "ha_device_id", mode="before")
    @classmethod
    def _trim_required_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ieee_address", mode="before")
    @classmethod
    def _normalize_ieee_address(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "ha_device_name",
        "area_id",
        "area_name",
        "entity_id",
        mode="before",
    )
    @classmethod
    def _trim_optional_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class HomeAssistantEnrichmentRequestV1(BaseModel):
    """Exact complete-snapshot request accepted by the Core enrichment endpoint."""

    model_config = ConfigDict(extra="forbid")

    home_assistant_enrichment_contract_version: Literal[1]
    devices: list[HomeAssistantEnrichmentDeviceV1] = Field(
        max_length=HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES
    )

    @field_validator("home_assistant_enrichment_contract_version", mode="before")
    @classmethod
    def _exact_contract_version(cls, value: Any) -> Any:
        if isinstance(value, bool) or type(value) is not int:
            raise ValueError("home_assistant_enrichment_contract_version must be integer 1")
        return value

    @model_validator(mode="after")
    def _reject_duplicate_or_conflicting_rows(self) -> HomeAssistantEnrichmentRequestV1:
        seen_identities: set[tuple[str, str]] = set()
        ha_device_owners: dict[str, tuple[str, str]] = {}
        entity_owners: dict[str, tuple[str, str]] = {}
        for device in self.devices:
            identity = (device.network_id, device.ieee_address)
            if identity in seen_identities:
                raise ValueError(
                    "duplicate Home Assistant enrichment identity "
                    f"{device.network_id}/{device.ieee_address}"
                )
            seen_identities.add(identity)

            ha_device_owner = ha_device_owners.get(device.ha_device_id)
            if ha_device_owner is not None and ha_device_owner != identity:
                raise ValueError(
                    "one Home Assistant device registry ID cannot target "
                    "multiple Core identities"
                )
            ha_device_owners[device.ha_device_id] = identity

            if device.entity_id is None:
                continue
            entity_owner = entity_owners.get(device.entity_id)
            if entity_owner is not None and entity_owner != identity:
                raise ValueError(
                    "one representative entity ID cannot target "
                    "multiple Core identities"
                )
            entity_owners[device.entity_id] = identity
        return self


class HomeAssistantEnrichmentResultV1(BaseModel):
    """Deterministic factual result for one accepted complete snapshot."""

    model_config = ConfigDict(extra="forbid")

    home_assistant_enrichment_contract_version: Literal[1]
    submitted: StrictInt = Field(ge=0)
    matched: StrictInt = Field(ge=0)
    unmatched: StrictInt = Field(ge=0)
    ambiguous: StrictInt = Field(ge=0)
    stored: StrictInt = Field(ge=0)
    last_push_at: StrictStr = Field(
        min_length=1,
        max_length=64,
        json_schema_extra={"format": "date-time"},
    )

    @field_validator("home_assistant_enrichment_contract_version", mode="before")
    @classmethod
    def _exact_contract_version(cls, value: Any) -> Any:
        if isinstance(value, bool) or type(value) is not int:
            raise ValueError("home_assistant_enrichment_contract_version must be integer 1")
        return value

    @field_validator("last_push_at")
    @classmethod
    def _timezone_aware_iso_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "last_push_at must be a timezone-aware ISO timestamp"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("last_push_at must be a timezone-aware ISO timestamp")
        return value

    @model_validator(mode="after")
    def _validate_counts(self) -> HomeAssistantEnrichmentResultV1:
        if self.submitted != self.matched + self.unmatched + self.ambiguous:
            raise ValueError("submitted must equal matched + unmatched + ambiguous")
        if self.stored != self.matched:
            raise ValueError("stored must equal matched")
        return self


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
    coverage_label_codes: list[CoverageLabelCode]


# Public alias — same compact badge shape for devices and networks.
DecisionBadge = DeviceDecisionBadge


class DecisionCountSummary(BaseModel):
    """Pure aggregate of represented subject decision badges.

    Must not carry independently promoted network-level judgement. Counts are
    strict non-negative integers (no bool / float / numeric string coercion).
    Every field is required on input — no count-map or coverage defaults.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    subject_count: StrictInt = Field(ge=0)
    overall_status: DecisionStatus
    highest_priority: DecisionPriority
    status_counts: dict[DecisionStatus, StrictInt]
    priority_counts: dict[DecisionPriority, StrictInt]
    coverage_warning_count: StrictInt = Field(ge=0)

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
    home_assistant_name: str | None = None
    home_assistant_area_name: str | None = None
    # Backward-compatible public alias retained for existing 0.1.x consumers.
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


class RedactionMode(str, Enum):
    preserved = "preserved"
    labeled = "labeled"
    hashed = "hashed"
    redacted = "redacted"


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

    model_config = ConfigDict(extra="forbid")

    profile: RedactionProfile | None = None
    preserve_friendly_names: bool | None = None
    hash_ieee_addresses: bool | None = None
    redact_hostnames: bool | None = None
    redact_ip_addresses: bool | None = None
    redact_network_names: bool | None = None
    include_timeline: bool | None = None


class ReportRequest(BaseModel):
    format: ReportFormat = ReportFormat.json
    scope: ReportScope = ReportScope.full
    incident_id: str | None = None
    network_id: str | None = None
    device: str | None = None
    redaction: RedactionOptions = Field(default_factory=RedactionOptions)


class ReportRedactionStatus(BaseModel):
    """Exact redaction status block for report-v3 bodies."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    applied: bool
    profile: RedactionProfile
    mqtt_credentials: bool
    secrets: bool
    hostnames: bool
    ip_addresses: bool
    ieee_addresses_hashed: bool
    friendly_names: RedactionMode
    network_names: RedactionMode


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

    subject_type: Literal["device"]
    subject_id: str
    status: DecisionStatus
    priority: DecisionPriority
    headline_code: str

    reasons: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    limitations: list[dict[str, Any]]
    suggested_checks: list[dict[str, Any]]
    coverage: list[dict[str, Any]]
    related_unresolved_incident_ids: list[str]
    timeline: list[ReportStoryTimelineItem]


class ReportDomainDetailsV3(BaseModel):
    """Exact v3 domain inventory for one report scope."""

    model_config = ConfigDict(extra="forbid")

    networks: list[NetworkSummary]
    devices: list[DeviceSummary]
    device_details: list[DeviceDetail]
    router_risks: list[RouterRisk]
    topology_snapshot_count: StrictInt = Field(ge=0)

    @field_validator("topology_snapshot_count", mode="before")
    @classmethod
    def _strict_topology_count(cls, value: Any) -> Any:
        if isinstance(value, bool) or type(value) is not int:
            raise ValueError("topology_snapshot_count must be a non-negative integer")
        if value < 0:
            raise ValueError("topology_snapshot_count must be a non-negative integer")
        return value


# Compatibility alias used by helpers during the Track 5 seal.
ReportDomainDetails = ReportDomainDetailsV3


class ReportDetailV3(BaseModel):
    """Exact current report contract (version 3). No legacy aliases.

    Every canonical field is required on input — stored/API bodies must not be
    completed from model defaults.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: str
    product: Literal["ZigbeeLens"]
    report_version: Literal[3]
    generated_at: str
    version: str
    scope: ReportScope
    format: ReportFormat
    redaction: ReportRedactionStatus
    config_summary: dict[str, Any]
    decision_summary: DecisionCountSummary
    investigation_priorities: list[InvestigationPrioritySummary]
    device_stories: list[ReportDeviceStory]
    data_coverage_warnings: list[DataCoverageWarningSummary]
    incidents: list[Incident]
    collector_status: dict[str, Any]
    domain_details: ReportDomainDetailsV3
    events_or_timeline: list[TimelineEvent]
    limitations: list[LimitationItem]
    raw_counts: dict[str, StrictInt]
    markdown_summary: str

    @field_validator("raw_counts", mode="before")
    @classmethod
    def _strict_raw_counts(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        for key, count in value.items():
            if isinstance(count, bool) or type(count) is not int or count < 0:
                raise ValueError(f"invalid raw_counts value for {key!r}")
        return value


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


class StoragePolicyStatus(BaseModel):
    policy_version: int = 2
    telemetry_retention_days: int
    resolved_incident_retention_days: int | None = None
    report_retention_days: int | None = None
    maintenance_interval_hours: int
    topology_max_snapshots_per_network: int


class StorageMaintenanceStatus(BaseModel):
    running: bool = False
    last_started_at: str | None = None
    last_completed_at: str | None = None
    last_successful_at: str | None = None
    next_scheduled_at: str | None = None
    last_error_code: str | None = None
    failure_category: str | None = None
    total_rows_deleted: int | None = None
    rows_deleted_by_category: dict[str, int] = Field(default_factory=dict)
    rows_updated_by_category: dict[str, int] = Field(default_factory=dict)
    malformed_timestamps_by_category: dict[str, int] = Field(default_factory=dict)
    future_timestamps_by_category: dict[str, int] = Field(default_factory=dict)
    more_work_pending: bool = False
    duration_ms: int | None = None
    telemetry_cutoff: str | None = None
    resolved_incident_cutoff: str | None = None
    report_cutoff: str | None = None
    wal_checkpoint: dict[str, int | bool | None] = Field(default_factory=dict)


class StorageFootprintStatus(BaseModel):
    database_bytes: int | None = None
    wal_bytes: int | None = None
    shm_bytes: int | None = None
    total_sqlite_bytes: int | None = None
    page_size: int | None = None
    page_count: int | None = None
    freelist_page_count: int | None = None
    reusable_bytes: int | None = None
    schema_version: int | None = None


class StorageCheckFact(BaseModel):
    status: str | None = None
    checked_at: str | None = None
    violation_count: int | None = None


class StorageIntegrityStatus(BaseModel):
    startup_gates: str = "quick_and_foreign_keys"
    quick_check: StorageCheckFact = Field(default_factory=StorageCheckFact)
    foreign_key_check: StorageCheckFact = Field(default_factory=StorageCheckFact)


class StorageStatus(BaseModel):
    policy: StoragePolicyStatus
    maintenance: StorageMaintenanceStatus
    footprint: StorageFootprintStatus
    integrity: StorageIntegrityStatus


class ZigbeeLensConfigStatus(BaseModel):
    version: str
    uptime_seconds: int
    mqtt_connected: bool
    mqtt_server: str
    configured_networks: list[dict[str, str]]
    storage_path: str
    storage_ready: bool = False
    retention_days: int
    resolved_incident_retention_days: int | None = None
    report_retention_days: int | None = None
    maintenance_interval_hours: int | None = None
    storage: StorageStatus | None = None
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


class DeviceSnapshotCompareCounts(BaseModel):
    """Exact non-negative pair counts for one available-layout comparison."""

    model_config = ConfigDict(extra="forbid")

    latest_count: StrictInt = Field(ge=0)
    selected_count: StrictInt = Field(ge=0)
    latest_only_count: StrictInt = Field(ge=0)
    selected_only_count: StrictInt = Field(ge=0)
    changed_count: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _validate_pair_arithmetic(self) -> DeviceSnapshotCompareCounts:
        if (
            self.latest_only_count > self.latest_count
            or self.selected_only_count > self.selected_count
        ):
            raise ValueError("only-in counts cannot exceed total counts")
        latest_common = self.latest_count - self.latest_only_count
        selected_common = self.selected_count - self.selected_only_count
        if latest_common != selected_common or self.changed_count > latest_common:
            raise ValueError("snapshot comparison pair counts are inconsistent")
        return self


class DeviceSnapshotPresenceComparison(BaseModel):
    """Observed-device presence in two available stored layouts."""

    model_config = ConfigDict(extra="forbid")

    latest: StrictBool
    selected: StrictBool
    changed: StrictBool

    @model_validator(mode="after")
    def _validate_changed(self) -> DeviceSnapshotPresenceComparison:
        if self.changed != (self.latest != self.selected):
            raise ValueError("device presence changed must equal latest != selected")
        return self


class DeviceSnapshotComparison(BaseModel):
    """Typed comparison of one selected available layout with the latest."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "no_notable_change",
        "changed",
        "watch",
        "worth_reviewing",
    ]
    reasons: list[StrictStr]
    suggested_checks: list[StrictStr]
    device_presence: DeviceSnapshotPresenceComparison
    link_counts: DeviceSnapshotCompareCounts
    route_hint_counts: DeviceSnapshotCompareCounts

    @model_validator(mode="after")
    def _reject_no_change_with_presence_difference(
        self,
    ) -> DeviceSnapshotComparison:
        difference_count = (
            int(self.device_presence.changed)
            + self.link_counts.latest_only_count
            + self.link_counts.selected_only_count
            + self.link_counts.changed_count
            + self.route_hint_counts.latest_only_count
            + self.route_hint_counts.selected_only_count
            + self.route_hint_counts.changed_count
        )
        if (difference_count == 0) != (self.status == "no_notable_change"):
            raise ValueError(
                "no_notable_change must exactly match an unchanged comparison"
            )
        return self


class _DeviceSnapshotHistoryRowBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: StrictStr = Field(min_length=1)
    captured_at: StrictStr | None
    is_latest: StrictBool
    availability_coverage_status: Literal["off", "building", "tracked", "unknown"]
    availability_state_near_snapshot: Literal["online", "offline"] | None


class DeviceSnapshotHistoryAvailableRow(_DeviceSnapshotHistoryRowBase):
    layout_state: Literal["available"]
    is_usable: Literal[True]
    device_present_in_snapshot: StrictBool
    links_for_device_count: StrictInt = Field(ge=0)
    route_hints_for_device_count: StrictInt = Field(ge=0)
    comparison_to_latest: DeviceSnapshotComparison | None

    @model_validator(mode="after")
    def _validate_absence_counts(self) -> DeviceSnapshotHistoryAvailableRow:
        if not self.device_present_in_snapshot and (
            self.links_for_device_count != 0
            or self.route_hints_for_device_count != 0
        ):
            raise ValueError("an absent device cannot have link or route counts")
        return self


class DeviceSnapshotHistoryLimitedRow(_DeviceSnapshotHistoryRowBase):
    layout_state: Literal["limited"]
    is_usable: Literal[False]
    device_present_in_snapshot: None
    links_for_device_count: None
    route_hints_for_device_count: None
    comparison_to_latest: None


DeviceSnapshotHistoryRow = Annotated[
    DeviceSnapshotHistoryAvailableRow | DeviceSnapshotHistoryLimitedRow,
    Field(discriminator="layout_state"),
]


class DeviceSnapshotAvailabilityTracking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    earliest_observation_at: StrictStr | None


class DeviceSnapshotLatestPresenceFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)
    snapshot_id: StrictStr = Field(min_length=1)


class DeviceSnapshotSeenLatestFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_seen_in_latest_snapshot"]
    params: DeviceSnapshotLatestPresenceFactParams


class DeviceSnapshotAbsentLatestFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_absent_from_latest_snapshot"]
    params: DeviceSnapshotLatestPresenceFactParams


class DeviceSnapshotLatestLinksFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)
    link_count: StrictInt = Field(ge=0)


class DeviceSnapshotHasLatestLinksFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_has_latest_links"]
    params: DeviceSnapshotLatestLinksFactParams


class DeviceSnapshotNoLatestLinksFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)


class DeviceSnapshotNoLatestLinksFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_no_latest_links"]
    params: DeviceSnapshotNoLatestLinksFactParams


DeviceSnapshotLatestFact = Annotated[
    DeviceSnapshotSeenLatestFact
    | DeviceSnapshotAbsentLatestFact
    | DeviceSnapshotHasLatestLinksFact
    | DeviceSnapshotNoLatestLinksFact,
    Field(discriminator="code"),
]


class DeviceSnapshotSelectedLinksFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)
    snapshot_id: StrictStr = Field(min_length=1)
    link_count: StrictInt = Field(ge=0)


class DeviceSnapshotSelectedLinksFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_has_selected_snapshot_links"]
    params: DeviceSnapshotSelectedLinksFactParams


class DeviceSnapshotChangedFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)
    comparison_status: Literal["changed", "watch", "worth_reviewing"]
    snapshot_id: StrictStr = Field(min_length=1)
    latest_device_present_in_snapshot: StrictBool
    selected_device_present_in_snapshot: StrictBool
    device_presence_changed: StrictBool


class DeviceSnapshotChangedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["device_latest_vs_selected_changed"]
    params: DeviceSnapshotChangedFactParams


class DeviceSnapshotAvailabilityCoverageFactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ieee: StrictStr = Field(min_length=1)
    availability_coverage_status: Literal["off", "building", "unknown"]
    snapshot_id: StrictStr = Field(min_length=1)


class DeviceSnapshotAvailabilityCoverageFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["availability_coverage_affects_snapshot_comparison"]
    params: DeviceSnapshotAvailabilityCoverageFactParams


DeviceSnapshotComparisonFact = Annotated[
    DeviceSnapshotSelectedLinksFact
    | DeviceSnapshotChangedFact
    | DeviceSnapshotAvailabilityCoverageFact,
    Field(discriminator="code"),
]


class DeviceSnapshotTopologyFacts(BaseModel):
    """Topology facts aligned with the same device snapshot-history rows."""

    model_config = ConfigDict(extra="forbid")

    stale_threshold_hours: StrictInt | None = Field(ge=0)
    device_facts: list[DeviceSnapshotLatestFact]
    comparison_facts_by_snapshot_id: dict[
        StrictStr,
        list[DeviceSnapshotComparisonFact],
    ]

    @field_validator("comparison_facts_by_snapshot_id")
    @classmethod
    def _require_snapshot_ids(
        cls,
        value: dict[str, list[DeviceSnapshotComparisonFact]],
    ) -> dict[str, list[DeviceSnapshotComparisonFact]]:
        if any(not snapshot_id for snapshot_id in value):
            raise ValueError("comparison fact snapshot IDs must be non-empty")
        return value


class DeviceSnapshotHistoryDetail(BaseModel):
    """Exact response contract for device-led topology snapshot history."""

    model_config = ConfigDict(extra="forbid")

    network_id: StrictStr = Field(min_length=1)
    device_ieee: StrictStr = Field(min_length=1)
    friendly_name: StrictStr | None
    has_current_issue: StrictBool
    availability_tracking: DeviceSnapshotAvailabilityTracking
    latest_snapshot: DeviceSnapshotHistoryRow | None
    snapshots: list[DeviceSnapshotHistoryRow]
    topology_facts: DeviceSnapshotTopologyFacts

    @model_validator(mode="after")
    def _validate_snapshot_comparisons(self) -> DeviceSnapshotHistoryDetail:
        latest = self.latest_snapshot
        if latest is None:
            if self.snapshots:
                raise ValueError("earlier snapshots require a latest snapshot")
            if self.topology_facts.device_facts:
                raise ValueError("latest device facts require an available layout")
            if self.topology_facts.comparison_facts_by_snapshot_id:
                raise ValueError("comparison facts require snapshot history")
            return self
        if not latest.is_latest or latest.comparison_to_latest is not None:
            raise ValueError("latest snapshot ownership is invalid")
        latest_facts = self.topology_facts.device_facts
        if latest.layout_state == "limited":
            if latest_facts:
                raise ValueError("limited latest layouts cannot emit device facts")
        else:
            presence_facts = [
                fact
                for fact in latest_facts
                if fact.code
                in {
                    "device_seen_in_latest_snapshot",
                    "device_absent_from_latest_snapshot",
                }
            ]
            link_facts = [
                fact
                for fact in latest_facts
                if fact.code
                in {
                    "device_has_latest_links",
                    "device_no_latest_links",
                }
            ]
            if len(presence_facts) != 1 or len(link_facts) != 1:
                raise ValueError(
                    "available latest layouts require exact presence and link facts"
                )
            expected_presence_code = (
                "device_seen_in_latest_snapshot"
                if latest.device_present_in_snapshot
                else "device_absent_from_latest_snapshot"
            )
            if presence_facts[0].code != expected_presence_code:
                raise ValueError("latest presence fact contradicts snapshot evidence")
            presence_params = presence_facts[0].params
            if (
                not isinstance(
                    presence_params,
                    DeviceSnapshotLatestPresenceFactParams,
                )
                or presence_params.device_ieee != self.device_ieee
                or presence_params.snapshot_id != latest.snapshot_id
            ):
                raise ValueError("latest presence fact identity is inconsistent")
            expected_link_code = (
                "device_has_latest_links"
                if latest.links_for_device_count > 0
                else "device_no_latest_links"
            )
            if link_facts[0].code != expected_link_code:
                raise ValueError("latest link fact contradicts snapshot evidence")
            link_params = link_facts[0].params
            if expected_link_code == "device_has_latest_links":
                if (
                    not isinstance(
                        link_params,
                        DeviceSnapshotLatestLinksFactParams,
                    )
                    or link_params.device_ieee != self.device_ieee
                    or link_params.link_count != latest.links_for_device_count
                ):
                    raise ValueError("latest link fact evidence is inconsistent")
            elif (
                not isinstance(
                    link_params,
                    DeviceSnapshotNoLatestLinksFactParams,
                )
                or link_params.device_ieee != self.device_ieee
            ):
                raise ValueError("latest no-links fact identity is inconsistent")

        snapshot_ids = {latest.snapshot_id}
        selected_by_id: dict[str, DeviceSnapshotHistoryRow] = {}
        for selected in self.snapshots:
            if selected.is_latest or selected.snapshot_id in snapshot_ids:
                raise ValueError("earlier snapshot ownership is invalid")
            snapshot_ids.add(selected.snapshot_id)
            selected_by_id[selected.snapshot_id] = selected
            comparable = (
                latest.layout_state == "available"
                and selected.layout_state == "available"
            )
            if comparable != (selected.comparison_to_latest is not None):
                raise ValueError(
                    "comparisons require available latest and selected layouts"
                )
            comparison = selected.comparison_to_latest
            if comparison is not None:
                presence = comparison.device_presence
                if (
                    presence.latest != latest.device_present_in_snapshot
                    or presence.selected != selected.device_present_in_snapshot
                    or comparison.link_counts.latest_count
                    != latest.links_for_device_count
                    or comparison.link_counts.selected_count
                    != selected.links_for_device_count
                    or comparison.route_hint_counts.latest_count
                    != latest.route_hints_for_device_count
                    or comparison.route_hint_counts.selected_count
                    != selected.route_hints_for_device_count
                ):
                    raise ValueError(
                        "comparison evidence must equal its snapshot rows"
                    )
                link_differences = (
                    comparison.link_counts.latest_only_count
                    + comparison.link_counts.selected_only_count
                    + comparison.link_counts.changed_count
                )
                route_differences = (
                    comparison.route_hint_counts.latest_only_count
                    + comparison.route_hint_counts.selected_only_count
                    + comparison.route_hint_counts.changed_count
                )
                any_difference = (
                    presence.changed
                    or link_differences > 0
                    or route_differences > 0
                )
                if (
                    (comparison.status == "worth_reviewing")
                    != (self.has_current_issue and any_difference)
                ):
                    raise ValueError(
                        "worth_reviewing must exactly match a current issue plus change"
                    )
                if (
                    presence.changed
                    and not self.has_current_issue
                    and link_differences == 0
                    and route_differences == 0
                    and comparison.status != "changed"
                ):
                    raise ValueError(
                        "presence-only change without a current issue must be changed"
                    )

        changed_fact_code = "device_latest_vs_selected_changed"
        for fact_snapshot_id in self.topology_facts.comparison_facts_by_snapshot_id:
            if fact_snapshot_id not in selected_by_id:
                raise ValueError("comparison facts reference an unknown snapshot")
        for snapshot_id, selected in selected_by_id.items():
            facts = self.topology_facts.comparison_facts_by_snapshot_id.get(
                snapshot_id,
                [],
            )
            for fact in facts:
                if (
                    fact.params.device_ieee != self.device_ieee
                    or fact.params.snapshot_id != snapshot_id
                ):
                    raise ValueError(
                        "comparison fact identity contradicts snapshot history"
                    )
            changed_facts = [
                fact for fact in facts if fact.code == changed_fact_code
            ]
            comparison = selected.comparison_to_latest
            expects_changed_fact = (
                comparison is not None
                and comparison.status != "no_notable_change"
            )
            if len(changed_facts) != int(expects_changed_fact):
                raise ValueError(
                    "comparison changed fact must exactly match comparison status"
                )
            selected_link_facts = [
                fact
                for fact in facts
                if fact.code == "device_has_selected_snapshot_links"
            ]
            expects_selected_links_fact = (
                comparison is not None
                and selected.layout_state == "available"
                and selected.links_for_device_count > 0
            )
            if len(selected_link_facts) != int(expects_selected_links_fact):
                raise ValueError(
                    "selected-link fact must exactly match snapshot link evidence"
                )
            if selected_link_facts:
                params = selected_link_facts[0].params
                if (
                    not isinstance(params, DeviceSnapshotSelectedLinksFactParams)
                    or params.link_count != selected.links_for_device_count
                ):
                    raise ValueError(
                        "selected-link fact contradicts snapshot link evidence"
                    )
            coverage_facts = [
                fact
                for fact in facts
                if fact.code
                == "availability_coverage_affects_snapshot_comparison"
            ]
            expects_coverage_fact = (
                comparison is not None
                and selected.availability_coverage_status
                in {"off", "building", "unknown"}
            )
            if len(coverage_facts) != int(expects_coverage_fact):
                raise ValueError(
                    "comparison coverage fact must exactly match snapshot coverage"
                )
            if coverage_facts:
                params = coverage_facts[0].params
                if (
                    not isinstance(
                        params,
                        DeviceSnapshotAvailabilityCoverageFactParams,
                    )
                    or params.availability_coverage_status
                    != selected.availability_coverage_status
                ):
                    raise ValueError(
                        "comparison coverage fact contradicts snapshot coverage"
                    )
            if not changed_facts:
                continue
            assert comparison is not None
            params = changed_facts[0].params
            if not isinstance(params, DeviceSnapshotChangedFactParams):
                raise ValueError("comparison changed fact params are not exact")
            if (
                params.device_ieee != self.device_ieee
                or params.comparison_status != comparison.status
                or params.snapshot_id != snapshot_id
                or params.latest_device_present_in_snapshot
                is not comparison.device_presence.latest
                or params.selected_device_present_in_snapshot
                is not comparison.device_presence.selected
                or params.device_presence_changed
                is not comparison.device_presence.changed
            ):
                raise ValueError(
                    "comparison changed fact params contradict comparison evidence"
                )
        return self


class TopologyCaptureRequest(BaseModel):
    confirmed: StrictBool
    reason: str | None = None
