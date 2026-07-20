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

/** Canonical decision status for Device Story and estate summaries. */
export type DecisionStatus =
  | "informational"
  | "no_notable_change"
  | "changed"
  | "watch"
  | "worth_reviewing"
  | "review_first"
  | "improve_data_coverage"
  | "data_unavailable";

/** Canonical decision priority. */
export type DecisionPriority = "none" | "low" | "medium" | "high";

/** Stable coverage label codes mapped by UI/report presenters. */
export type CoverageLabelCode =
  | "availability_tracking_off"
  | "availability_history_building"
  | "availability_status_unknown"
  | "availability_available"
  | "route_hints_unavailable"
  | "ha_areas_not_linked"
  | "snapshot_stale"
  | "battery_history_sparse"
  | "battery_history_available"
  | "lqi_history_sparse"
  | "lqi_history_available"
  | "last_seen_available"
  | "last_seen_unknown"
  | "last_payload_available"
  | "last_payload_unknown"
  | "topology_history_available"
  | "topology_history_sparse"
  | "topology_history_not_observed"
  | "ha_area_linked";

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
  detail?: string | null;
  timestamp?: string | null;
  network_id?: string | null;
  ieee_address?: string | null;
}

/** Known limitation of a diagnostic conclusion */
export interface LimitationItem {
  id: string;
  summary: string;
  detail?: string | null;
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

/** Compact Device Story projection for inventory badges. */
export interface DecisionBadge {
  status: DecisionStatus;
  priority: DecisionPriority;
  headline_code: string;
  coverage_label_codes: CoverageLabelCode[];
}

/** Compatibility alias — same shape as DecisionBadge. */
export type DeviceDecisionBadge = DecisionBadge;

/** Aggregated decision counts for Dashboard / network / report / MQTT / HACS. */
export interface DecisionCountSummary {
  subject_count: number;
  overall_status: DecisionStatus;
  highest_priority: DecisionPriority;
  status_counts: Partial<Record<DecisionStatus, number>>;
  priority_counts: Partial<Record<DecisionPriority, number>>;
  coverage_warning_count: number;
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
  active_incident_severity: Severity | null;
  active_incident_count: number;
  recent_bridge_warnings: number;
  recent_bridge_errors: number;
  decision: DeviceDecisionBadge;
  decision_summary: DecisionCountSummary;
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
  incident_affected: boolean;
  decision: DeviceDecisionBadge;
  /** Home Assistant area name when enrichment is linked */
  ha_area?: string | null;
}

/** Full device detail for drilldown */
export interface DeviceDetail extends DeviceSummary {
  definition?: string;
  supported?: boolean;
  recent_availability_changes: AvailabilityChange[];
  recent_events: TimelineEvent[];
  recent_bridge_logs: BridgeLogEntry[];
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
  resolved_at: string | null;
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
  decision: DeviceDecisionBadge;
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
  network_id?: string | null;
  ieee_address?: string | null;
  friendly_name?: string | null;
  title: string;
  summary: string;
  incident_id?: string | null;
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

export interface ModelPatternSummary {
  pattern_id: string;
  network_id: string;
  manufacturer?: string | null;
  model: string;
  group_size: number;
  affected_count: number;
  lookback_days: number;
  affected_device_ieees: string[];
  latest_supporting_evidence_at?: string | null;
}

export interface InvestigationPrioritySummary {
  id: string;
  network_id: string;
  card_type: string;
  priority: string;
  score: number;
  action_group: string;
  title: string;
  summary: string;
  device_ieees: string[];
  latest_supporting_evidence_at?: string | null;
}

export interface DataCoverageWarningSummary {
  id: string;
  network_id: string;
  dimension: string;
  state: string;
  label_code: string;
  scope_type: string;
  params?: Record<string, unknown>;
}

/** Dashboard payload — primary API response for overview */
export interface DashboardPayload {
  generated_at: string;
  scenario?: string;
  active_incident_count: number;
  watching_incident_count: number;
  network_count: number;
  device_count: number;
  unavailable_device_count: number;
  networks: NetworkSummary[];
  router_risks: RouterRisk[];
  recent_timeline: TimelineEvent[];
  decision_summary: DecisionCountSummary;
  shared_availability_events: SharedAvailabilityEventSummary[];
  model_patterns: ModelPatternSummary[];
  investigation_priorities: InvestigationPrioritySummary[];
  data_coverage_warnings: DataCoverageWarningSummary[];
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

/** Canonical Device Story fields plus report identity (Phase 5D). */
export interface ReportDeviceStory {
  network_id: string;
  ieee_address: string;
  friendly_name: string;
  subject_type: string;
  subject_id: string;
  status: DecisionStatus;
  priority: DecisionPriority;
  headline_code: string;
  reasons: Array<{ code: string; params?: Record<string, unknown> }>;
  evidence: Array<Record<string, unknown>>;
  limitations: Array<{ code: string; params?: Record<string, unknown> }>;
  suggested_checks: Array<{ code: string; params?: Record<string, unknown> }>;
  coverage: Array<Record<string, unknown>>;
  related_unresolved_incident_ids: string[];
  timeline: Array<{
    code: string;
    params?: Record<string, unknown>;
    occurred_at?: string | null;
  }>;
}

/** Exact v3 report domain inventory. */
export interface ReportDomainDetailsV3 {
  networks: NetworkSummary[];
  devices: DeviceSummary[];
  device_details: DeviceDetail[];
  router_risks: RouterRisk[];
  topology_snapshot_count: number;
}

/** Compatibility alias for helpers during the Track 5 seal. */
export type ReportDomainDetails = ReportDomainDetailsV3;

/** Exact current report contract (version 3). No legacy aliases. */
export interface ReportDetailV3 {
  id: string;
  product: string;
  report_version: 3;
  generated_at: string;
  version: string;
  scope: ReportScope;
  format: ReportFormat;
  redaction: ReportRedactionStatus;
  config_summary: Record<string, unknown>;
  decision_summary: DecisionCountSummary;
  investigation_priorities: InvestigationPrioritySummary[];
  device_stories: ReportDeviceStory[];
  data_coverage_warnings: DataCoverageWarningSummary[];
  incidents: Incident[];
  collector_status: Record<string, unknown>;
  domain_details: ReportDomainDetailsV3;
  events_or_timeline: TimelineEvent[];
  limitations: LimitationItem[];
  raw_counts: Record<string, number>;
  markdown_summary: string;
}

/** Current writers and OpenAPI advertise ReportDetail as the exact v3 model. */
export type ReportDetail = ReportDetailV3;

/** Opaque stored report body for historical v1/v2 rows. */
export type LegacyStoredReportBody = Record<string, unknown>;

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

/** Secret-free security posture from Core config/status */
export type SecurityMode = "local" | "authenticated" | "home_assistant_ingress";

/** Public browser-session status from GET/POST /api/auth/session */
export interface BrowserSessionStatus {
  authenticated: boolean;
  auth_method: "trusted_local" | "bearer" | "session" | "home_assistant_ingress" | null;
  browser_session_enabled: boolean;
  home_assistant_ingress_enabled: boolean;
  expires_at: string | null;
  csrf_token: string | null;
}

export interface SecurityConfigStatus {
  mode: SecurityMode;
  loopback_bind: boolean;
  api_token_configured: boolean;
  session_secret_configured: boolean;
  bearer_auth_enabled: boolean;
  browser_session_enabled: boolean;
  csrf_protection_enabled: boolean;
  session_cookie_secure: boolean;
  read_routes_require_authentication: boolean;
  mutation_routes_require_authentication: boolean;
  /**
   * @deprecated True only when authentication is required and browser sessions
   * are not enabled. Prefer read_routes_require_authentication.
   */
  read_routes_require_bearer: boolean;
  /**
   * @deprecated True only when authentication is required and browser sessions
   * are not enabled. Prefer mutation_routes_require_authentication.
   */
  mutation_routes_require_bearer: boolean;
  ingress_identity_enforced: boolean;
  ingress_trusted_proxy_count: number;
  ingress_proxy_only: boolean;
  ingress_bearer_fallback_enabled: boolean;
  trusted_local_open: boolean;
  /** @deprecated Always false under bearer policy; retained for compatibility. */
  legacy_mutation_guard_enabled: boolean;
  cors_allowed_origins_count: number;
  credentialed_cors_enabled: boolean;
  frame_ancestor_origins_count: number;
  external_framing_enabled: boolean;
  content_security_policy_enabled: boolean;
  session_origin_validation_enabled: boolean;
}

/** Config / connection status */
/** Track 6 storage policy / maintenance / footprint projection. */
export interface StoragePolicyStatus {
  policy_version: number;
  telemetry_retention_days: number;
  resolved_incident_retention_days: number | null;
  report_retention_days: number | null;
  maintenance_interval_hours: number;
  topology_max_snapshots_per_network: number;
}

export interface StorageMaintenanceStatus {
  running: boolean;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_successful_at: string | null;
  next_scheduled_at: string | null;
  last_error_code: string | null;
  failure_category?: string | null;
  total_rows_deleted: number | null;
  rows_deleted_by_category?: Record<string, number>;
  rows_updated_by_category?: Record<string, number>;
  malformed_timestamps_by_category?: Record<string, number>;
  future_timestamps_by_category?: Record<string, number>;
  more_work_pending: boolean;
  duration_ms: number | null;
  telemetry_cutoff?: string | null;
  resolved_incident_cutoff?: string | null;
  report_cutoff?: string | null;
  wal_checkpoint?: Record<string, number | boolean | null>;
}

export interface StorageFootprintStatus {
  database_bytes: number | null;
  wal_bytes: number | null;
  shm_bytes: number | null;
  total_sqlite_bytes: number | null;
  page_size: number | null;
  page_count: number | null;
  freelist_page_count: number | null;
  reusable_bytes: number | null;
  schema_version: number | null;
}

export interface StorageCheckFact {
  status: string | null;
  checked_at: string | null;
  violation_count: number | null;
}

export interface StorageIntegrityStatus {
  startup_gates: string;
  quick_check: StorageCheckFact;
  foreign_key_check: StorageCheckFact;
}

export interface StorageStatus {
  policy: StoragePolicyStatus;
  maintenance: StorageMaintenanceStatus;
  footprint: StorageFootprintStatus;
  integrity: StorageIntegrityStatus;
}

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
  /** Telemetry history retention (compatibility field). */
  retention_days: number;
  resolved_incident_retention_days?: number | null;
  report_retention_days?: number | null;
  maintenance_interval_hours?: number | null;
  storage?: StorageStatus;
  features: Record<string, boolean>;
  mqtt_discovery?: Record<string, boolean | string>;
  topology?: TopologyStatus;
  diagnostics?: Record<string, number>;
  data_mode: "mock" | "live";
  mock_mode?: boolean;
  active_scenario?: string;
  security: SecurityConfigStatus;
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
  limit?: number | null;
  next_cursor?: string | null;
}

/** Incident collection query (Track 3E) */
export interface IncidentCollectionQuery {
  scenario?: string;
  status?: IncidentStatus | IncidentStatus[];
  updated_after?: string;
  network_id?: string;
  device_ieee?: string;
  limit?: number;
  cursor?: string;
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
