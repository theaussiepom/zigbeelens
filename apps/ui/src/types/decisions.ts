/**
 * API DTO types for the shared decision engine.
 *
 * These mirror backend `zigbeelens.decisions` models. Screens should prefer
 * ViewModels built from these DTOs rather than interpreting raw fields.
 */

export type DecisionStatus =
  | "informational"
  | "no_notable_change"
  | "changed"
  | "watch"
  | "worth_reviewing"
  | "review_first"
  | "improve_data_coverage"
  | "data_unavailable";

export type DecisionPriority = "none" | "low" | "medium" | "high";

export type CoverageDimension =
  | "availability"
  | "last_seen"
  | "last_payload"
  | "battery"
  | "linkquality"
  | "topology_snapshot"
  | "route_hints"
  | "historical_snapshots"
  | "passive_history"
  | "ha_enrichment"
  | "incidents"
  | "reports";

export type CoverageState =
  | "available"
  | "off"
  | "building"
  | "unknown"
  | "stale"
  | "not_configured"
  | "not_observed"
  | "sparse";

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

export interface EvidenceFactDto {
  code: string;
  params?: Record<string, unknown>;
}

export interface TopologyNetworkFactsDto {
  stale_threshold_hours: number | null;
  network_facts: EvidenceFactDto[];
  coverage: DataCoverageDto[];
}

export interface TopologyDeviceFactsDto {
  stale_threshold_hours: number | null;
  device_facts: EvidenceFactDto[];
  comparison_facts_by_snapshot_id: Record<string, EvidenceFactDto[]>;
}

export interface DecisionReasonDto {
  code: string;
  params?: Record<string, unknown>;
}

export interface EvidenceReferenceDto {
  source: string;
  id?: string | null;
  captured_at?: string | null;
  label?: string | null;
}

export interface DecisionLimitationDto {
  code: string;
  params?: Record<string, unknown>;
}

export interface SuggestedCheckDto {
  code: string;
  params?: Record<string, unknown>;
}

export interface DataCoverageDto {
  dimension: CoverageDimension;
  state: CoverageState;
  label_code: CoverageLabelCode;
  params?: Record<string, unknown>;
}

export interface DecisionDto {
  subject_type: string;
  subject_id: string;
  status: DecisionStatus;
  priority?: DecisionPriority;
  reasons?: DecisionReasonDto[];
  evidence?: EvidenceReferenceDto[];
  limitations?: DecisionLimitationDto[];
  suggested_checks?: SuggestedCheckDto[];
  coverage?: DataCoverageDto[];
}

export interface DecisionBundleDto {
  subject_type: string;
  subject_id: string;
  decisions: DecisionDto[];
}
