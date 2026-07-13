/** Canonical diagnostic severity levels */
export type Severity = "healthy" | "watch" | "incident" | "critical";

/** Confidence in a diagnostic conclusion */
export type Confidence = "low" | "medium" | "high";

/** Scope of an incident or finding */
export type IncidentScope =
  | "device"
  | "router_candidate"
  | "mesh_segment"
  | "network"
  | "multi_network"
  | "unknown";

/** Incident lifecycle state */
export type IncidentStatus = "open" | "watching" | "resolved";

/** Device health primary classification */
export type DeviceHealthPrimary =
  | "healthy"
  | "unavailable"
  | "recently_unstable"
  | "weak_link"
  | "low_battery"
  | "stale_reporting"
  | "interview_issue"
  | "router_risk"
  | "unknown";

/** Lens family presentation-layer health bucket (shared across Lens tools) */
export type LensBucket =
  | "healthy"
  | "recently_unstable"
  | "needs_attention"
  | "unavailable"
  | "diagnostics_limited"
  | "informational"
  | "unknown";

/** Bridge online state */
export type BridgeState = "online" | "offline" | "unknown";

/** Device type from Zigbee2MQTT */
export type DeviceType = "Coordinator" | "Router" | "EndDevice" | "Unknown";

/** Power source hint */
export type PowerSource = "Battery" | "Mains" | "Unknown";

/** Availability state */
export type Availability = "online" | "offline" | "unknown";

/** Interview state */
export type InterviewState = "successful" | "failed" | "in_progress" | "unknown";

/** Evidence item supporting or countering a conclusion */
export interface EvidenceItem {
  id: string;
  kind: string;
  summary: string;
  detail?: string;
  timestamp?: string;
  network_id?: string;
  ieee_address?: string;
}

/** Known limitation of a diagnostic conclusion */
export interface LimitationItem {
  id: string;
  summary: string;
  detail?: string;
}

/** Standard diagnostic conclusion shape */
export interface DiagnosticConclusion {
  classification: string;
  severity: Severity;
  scope: IncidentScope;
  confidence: Confidence;
  summary: string;
  evidence: EvidenceItem[];
  counter_evidence: EvidenceItem[];
  limitations: LimitationItem[];
}

/** Device health classification result */
export interface DeviceHealth {
  primary: DeviceHealthPrimary;
  severity: Severity;
  confidence: Confidence;
  evidence: string[];
  counter_evidence: string[];
  limitations: string[];
  flags?: DeviceHealthPrimary[];
}

/** Network summary for dashboard and network pages */
export interface NetworkSummary {
  id: string;
  name: string;
  base_topic: string;
  bridge_state: BridgeState;
  coordinator?: CoordinatorSummary;
  device_count: number;
  router_count: number;
  end_device_count: number;
  unavailable_count: number;
  recently_unstable_count: number;
  weak_link_count: number;
  low_battery_count: number;
  stale_count: number;
  interview_issue_count: number;
  incident_state: Severity;
  active_incident_count: number;
  recent_bridge_warnings: number;
  recent_bridge_errors: number;
  health: DeviceHealth;
}

/** Coordinator info */
export interface CoordinatorSummary {
  ieee_address: string;
  manufacturer?: string;
  model?: string;
  firmware?: string;
  channel?: number;
  pan_id?: string;
  extended_pan_id?: string;
}

/** Device list row */
export interface DeviceSummary {
  network_id: string;
  ieee_address: string;
  friendly_name: string;
  device_type: DeviceType;
  power_source: PowerSource;
  availability: Availability;
  last_seen?: string;
  last_payload_at?: string;
  linkquality?: number;
  battery?: number;
  manufacturer?: string | null;
  model?: string | null;
  interview_state: InterviewState;
  health: DeviceHealth;
  incident_affected: boolean;
  sort_priority: number;
  lens_bucket: LensBucket;
  lens_bucket_label: string;
  lens_bucket_reason: string;
  lens_reasons: string[];
}

/** Full device detail for drilldown */
export interface DeviceDetail extends DeviceSummary {
  definition?: string;
  supported?: boolean;
  recent_availability_changes: AvailabilityChange[];
  recent_events: TimelineEvent[];
  recent_bridge_logs: BridgeLogEntry[];
  diagnostic: DiagnosticConclusion;
  trends?: DeviceTrendPoint[];
}

export interface AvailabilityChange {
  timestamp: string;
  from: Availability;
  to: Availability;
}

export interface BridgeLogEntry {
  timestamp: string;
  level: "warning" | "error" | "info";
  message: string;
}

export interface DeviceTrendPoint {
  timestamp: string;
  linkquality?: number;
  battery?: number;
  availability?: Availability;
}

/** Router risk candidate */
export interface RouterRisk {
  network_id: string;
  ieee_address: string;
  friendly_name: string;
  availability: Availability;
  linkquality?: number;
  last_seen?: string;
  possibly_dependent_devices?: number;
  correlated_affected_devices: number;
  risk: DiagnosticConclusion;
}

/** Incident record */
export interface Incident {
  id: string;
  type: string;
  status: IncidentStatus;
  severity: Severity;
  scope: IncidentScope;
  confidence: Confidence;
  title: string;
  summary: string;
  interpretation: string;
  network_ids: string[];
  affected_device_count: number;
  affected_devices: IncidentDeviceRef[];
  opened_at: string;
  updated_at: string;
  resolved_at?: string;
  evidence: EvidenceItem[];
  counter_evidence: EvidenceItem[];
  limitations: LimitationItem[];
  timeline: TimelineEvent[];
  conclusion: DiagnosticConclusion;
}

export interface IncidentDeviceRef {
  network_id: string;
  ieee_address: string;
  friendly_name: string;
  health_primary: DeviceHealthPrimary;
  lens_bucket: LensBucket;
  lens_bucket_label: string;
  lens_bucket_reason: string;
}

/** Alias for clarity in API responses */
export type IncidentEvidence = EvidenceItem;
export type IncidentLimitation = LimitationItem;

/** Timeline event */
export interface TimelineEvent {
  id: string;
  timestamp: string;
  kind: string;
  severity: Severity;
  network_id?: string;
  ieee_address?: string;
  friendly_name?: string;
  title: string;
  summary: string;
  incident_id?: string;
}

/** Point-in-time health snapshot */
export interface HealthSnapshot {
  timestamp: string;
  overall_severity: Severity;
  overall_health: DeviceHealthPrimary;
  network_count: number;
  device_count: number;
  unavailable_count: number;
  incident_count: number;
  networks: Array<{
    network_id: string;
    severity: Severity;
    unavailable_count: number;
  }>;
}

/** Facts-only shared availability event for dashboard Overview */
export interface SharedAvailabilityEventSummary {
  event_id: string;
  network_id: string;
  started_at: string;
  ended_at: string;
  device_count: number;
  duration_minutes: number;
  device_ieees: string[];
}

/** Dashboard payload — primary API response for overview */
export interface DashboardPayload {
  generated_at: string;
  scenario?: string;
  overall_severity: Severity;
  current_finding: DiagnosticConclusion;
  active_incident_count: number;
  watching_incident_count: number;
  networks: NetworkSummary[];
  top_affected_devices: DeviceSummary[];
  router_risks: RouterRisk[];
  recently_unstable: DeviceSummary[];
  weak_links: DeviceSummary[];
  low_batteries: DeviceSummary[];
  stale_devices: DeviceSummary[];
  recent_timeline: TimelineEvent[];
  health_snapshot: HealthSnapshot;
  shared_availability_events: SharedAvailabilityEventSummary[];
}

/** Redaction profile presets */
export type RedactionProfile = "standard" | "strict" | "public_safe";

/** Report scopes */
export type ReportScope = "full" | "incident" | "network" | "device";

/** Report serialization formats */
export type ReportFormat = "json" | "yaml" | "markdown";

/** How an identifier class was treated in a report */
export type RedactionMode = "preserved" | "labeled" | "hashed" | "redacted";

/** Per-request redaction overrides (null = use profile default) */
export interface RedactionOptions {
  profile: RedactionProfile;
  preserve_friendly_names?: boolean | null;
  hash_ieee_addresses?: boolean | null;
  redact_hostnames?: boolean | null;
  redact_ip_addresses?: boolean | null;
  redact_network_names?: boolean | null;
  include_timeline?: boolean | null;
  include_raw_payloads?: boolean | null;
}

/** Request body for generating a report */
export interface ReportRequest {
  format: ReportFormat;
  scope: ReportScope;
  incident_id?: string | null;
  network_id?: string | null;
  device?: string | null;
  redaction: RedactionOptions;
}

/** Report list item */
export interface ReportSummary {
  id: string;
  generated_at: string;
  redaction_applied: boolean;
  incident_count: number;
  device_count: number;
  network_count: number;
  summary: string;
  format: ReportFormat;
  scope: ReportScope;
  redaction_profile: RedactionProfile;
}

/** High-level numeric summary block */
export interface ReportSummaryBlock {
  overall_state: Severity;
  current_finding: string;
  networks_monitored: number;
  total_devices: number;
  active_incidents: number;
  watching_incidents: number;
  unavailable_devices: number;
  router_risks: number;
  stale_devices: number;
  weak_links: number;
  low_battery_devices: number;
}

/** Full report detail */
export interface ReportDetail {
  id: string;
  product: string;
  report_version: number;
  generated_at: string;
  version: string;
  scope: ReportScope;
  format: ReportFormat;
  redaction: ReportRedactionStatus;
  summary?: ReportSummaryBlock | null;
  config_summary: Record<string, unknown>;
  collector: Record<string, unknown>;
  networks: NetworkSummary[];
  devices: DeviceSummary[];
  device_details: DeviceDetail[];
  router_risks: RouterRisk[];
  incidents: Incident[];
  timeline: TimelineEvent[];
  health_snapshot: HealthSnapshot;
  diagnostic_conclusions: DiagnosticConclusion[];
  limitations: LimitationItem[];
  raw_counts: Record<string, number>;
  markdown_summary: string;
}

export interface ReportRedactionStatus {
  applied: boolean;
  profile: RedactionProfile;
  mqtt_credentials: boolean;
  secrets: boolean;
  hostnames: boolean;
  ip_addresses: boolean;
  ieee_addresses_hashed: boolean;
  friendly_names: RedactionMode;
  network_names: RedactionMode;
}

/** Config / connection status */
export interface ZigbeeLensConfigStatus {
  version: string;
  uptime_seconds: number;
  mqtt_connected: boolean;
  mqtt_server: string;
  configured_networks: Array<{
    id: string;
    name: string;
    base_topic: string;
  }>;
  storage_path: string;
  storage_ready?: boolean;
  retention_days: number;
  features: Record<string, boolean>;
  mqtt_discovery?: Record<string, boolean | string>;
  topology?: TopologyStatus;
  diagnostics?: Record<string, number>;
  data_mode: "mock" | "live";
  mock_mode?: boolean;
  active_scenario?: string;
}

/** Per-network collector subscription status */
export interface CollectorNetworkStatus {
  network_id: string;
  subscribed: boolean;
}

/** MQTT collector status reported by Core */
export interface CollectorStatus {
  enabled?: boolean;
  connected?: boolean;
  subscribed_topics_count?: number;
  last_message_at?: string | null;
  last_error?: string | null;
  networks?: CollectorNetworkStatus[];
}

/** MQTT discovery publisher status reported by Core */
export interface MqttDiscoveryStatus {
  enabled?: boolean;
  connected?: boolean;
  published_entities_count?: number;
  last_publish_at?: string | null;
  last_error?: string | null;
}

/** Topology capture status reported by Core */
export interface TopologyStatus {
  enabled?: boolean;
  manual_capture_enabled?: boolean;
  automatic_capture_enabled?: boolean;
  capture_in_progress?: boolean;
  last_capture_error?: string | null;
}

/** Home Assistant enrichment status reported by Core */
export interface HaEnrichmentStatus {
  enabled?: boolean;
  matched_devices?: number;
  last_push_at?: string | null;
  source?: string | null;
}

/** Core health/liveness response */
export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  config_loaded: boolean;
  mock_mode: boolean;
  database: string;
  migration_version: number;
  collector: CollectorStatus;
  mqtt_discovery?: MqttDiscoveryStatus;
  topology?: TopologyStatus;
  home_assistant_enrichment?: HaEnrichmentStatus;
}

/** API list wrappers */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export type MockScenarioId =
  | "all_ok_single_network"
  | "all_ok_multi_network"
  | "single_device_unavailable"
  | "four_devices_same_room_unavailable"
  | "bridge_offline"
  | "one_network_incident_other_network_ok"
  | "router_risk_candidate"
  | "stale_battery_devices"
  | "low_battery_cluster"
  | "interview_failures"
  | "unknown_insufficient_data"
  | "multiple_networks_unstable"
  | "weak_link_devices"
  | "stale_reporting_cluster";

export const MOCK_SCENARIO_IDS: MockScenarioId[] = [
  "all_ok_single_network",
  "all_ok_multi_network",
  "single_device_unavailable",
  "four_devices_same_room_unavailable",
  "bridge_offline",
  "one_network_incident_other_network_ok",
  "router_risk_candidate",
  "stale_battery_devices",
  "low_battery_cluster",
  "interview_failures",
  "unknown_insufficient_data",
  "multiple_networks_unstable",
  "weak_link_devices",
  "stale_reporting_cluster",
];
