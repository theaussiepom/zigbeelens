/**
 * API DTO types for the shared decision engine.
 *
 * Canonical unions live in @zigbeelens/shared. This module re-exports them and
 * adds UI-only DTO shapes that are not part of the compact public contract.
 */

import type {
  DataCoverage,
  DecisionPriority,
  DecisionStatus,
  DeviceSnapshotComparisonFact,
  DeviceSnapshotLatestFact,
} from "@zigbeelens/shared";

export type {
  CoverageDimension,
  CoverageLabelCode,
  CoverageState,
  DataCoverage,
  DecisionBadge,
  DecisionCountSummary,
  DecisionPriority,
  DecisionStatus,
  DeviceDecisionBadge,
  TopologyHistoryCoverageParams,
} from "@zigbeelens/shared";

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
  device_facts: DeviceSnapshotLatestFact[];
  comparison_facts_by_snapshot_id: Record<
    string,
    DeviceSnapshotComparisonFact[]
  >;
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

export type DataCoverageDto = DataCoverage;

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
