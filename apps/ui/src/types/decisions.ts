/**
 * API DTO types for the shared decision engine.
 *
 * Canonical unions live in @zigbeelens/shared. This module re-exports them and
 * adds UI-only DTO shapes that are not part of the compact public contract.
 */

import type {
  CoverageLabelCode,
  DecisionPriority,
  DecisionStatus,
} from "@zigbeelens/shared";

export type {
  CoverageLabelCode,
  DecisionBadge,
  DecisionCountSummary,
  DecisionPriority,
  DecisionStatus,
  DeviceDecisionBadge,
} from "@zigbeelens/shared";

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
