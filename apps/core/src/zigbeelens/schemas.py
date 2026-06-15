from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, StrictBool


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
    recently_unstable_count: int
    weak_link_count: int
    low_battery_count: int
    stale_count: int
    interview_issue_count: int = 0
    incident_state: Severity
    active_incident_count: int
    recent_bridge_warnings: int = 0
    recent_bridge_errors: int = 0
    health: DeviceHealth


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
    interview_state: InterviewState
    health: DeviceHealth
    incident_affected: bool = False
    sort_priority: int = 100


class DeviceDetail(DeviceSummary):
    manufacturer: str | None = None
    model: str | None = None
    definition: str | None = None
    supported: bool | None = None
    recent_availability_changes: list[AvailabilityChange] = Field(default_factory=list)
    recent_events: list[TimelineEvent] = Field(default_factory=list)
    recent_bridge_logs: list[BridgeLogEntry] = Field(default_factory=list)
    diagnostic: DiagnosticConclusion
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
    health_primary: DeviceHealthPrimary


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


class DashboardPayload(BaseModel):
    generated_at: str
    scenario: str | None = None
    overall_severity: Severity
    current_finding: DiagnosticConclusion
    active_incident_count: int
    watching_incident_count: int
    networks: list[NetworkSummary]
    top_affected_devices: list[DeviceSummary]
    router_risks: list[RouterRisk]
    recently_unstable: list[DeviceSummary]
    weak_links: list[DeviceSummary]
    low_batteries: list[DeviceSummary]
    stale_devices: list[DeviceSummary]
    recent_timeline: list[TimelineEvent]
    health_snapshot: HealthSnapshot


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


class ReportSummaryBlock(BaseModel):
    overall_state: Severity
    current_finding: str
    networks_monitored: int
    total_devices: int
    active_incidents: int
    watching_incidents: int
    unavailable_devices: int
    router_risks: int
    stale_devices: int
    weak_links: int
    low_battery_devices: int


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


class ReportDetail(BaseModel):
    id: str
    product: str = "ZigbeeLens"
    report_version: int = 1
    generated_at: str
    version: str
    scope: str = "full"
    format: str = "json"
    redaction: ReportRedactionStatus
    summary: ReportSummaryBlock | None = None
    config_summary: dict[str, Any]
    collector: dict[str, Any] = Field(default_factory=dict)
    networks: list[NetworkSummary]
    devices: list[DeviceSummary]
    device_details: list[DeviceDetail] = Field(default_factory=list)
    router_risks: list[RouterRisk]
    incidents: list[Incident]
    timeline: list[TimelineEvent] = Field(default_factory=list)
    health_snapshot: HealthSnapshot
    diagnostic_conclusions: list[DiagnosticConclusion]
    limitations: list[LimitationItem] = Field(default_factory=list)
    raw_counts: dict[str, int] = Field(default_factory=dict)
    markdown_summary: str


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


class TopologyCaptureRequest(BaseModel):
    confirmed: StrictBool
    reason: str | None = None
