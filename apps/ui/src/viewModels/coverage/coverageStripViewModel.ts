/**
 * Evidence coverage strip ViewModel — maps DataCoverage DTOs to UI-ready items.
 */

import type { CoverageDimension, CoverageLabelCode, DataCoverageDto } from "@/types/decisions";
import {
  coverageHelperText,
  coverageLabel,
  coverageTone,
} from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

/** Network-level topology coverage strip order (Phase 3E). */
const NETWORK_COVERAGE_STRIP_ORDER: CoverageLabelCode[] = [
  "availability_tracking_off",
  "availability_history_building",
  "availability_status_unknown",
  "snapshot_stale",
  "route_hints_unavailable",
  "ha_areas_not_linked",
  "battery_history_sparse",
  "lqi_history_sparse",
];

/** Per-device coverage strip order (Phase 4C) — mirrors backend dimension order. */
const DEVICE_COVERAGE_DIMENSION_ORDER: CoverageDimension[] = [
  "availability",
  "last_seen",
  "last_payload",
  "battery",
  "linkquality",
  "historical_snapshots",
  "ha_enrichment",
];

const DEVICE_COVERAGE_LABEL_ORDER: CoverageLabelCode[] = [
  "availability_tracking_off",
  "availability_available",
  "availability_history_building",
  "availability_status_unknown",
  "last_seen_available",
  "last_seen_unknown",
  "last_payload_available",
  "last_payload_unknown",
  "battery_history_available",
  "battery_history_sparse",
  "lqi_history_available",
  "lqi_history_sparse",
  "topology_history_available",
  "topology_history_sparse",
  "topology_history_not_observed",
  "ha_area_linked",
  "ha_areas_not_linked",
];

const NETWORK_ORDER_INDEX = new Map(
  NETWORK_COVERAGE_STRIP_ORDER.map((code, index) => [code, index] as const),
);

const DEVICE_LABEL_ORDER_INDEX = new Map(
  DEVICE_COVERAGE_LABEL_ORDER.map((code, index) => [code, index] as const),
);

const DEVICE_DIMENSION_ORDER_INDEX = new Map(
  DEVICE_COVERAGE_DIMENSION_ORDER.map((dimension, index) => [dimension, index] as const),
);

/** Legacy network constraints for topology page network strip filtering. */
export const DEVICE_DRAWER_COVERAGE_LABEL_CODES = new Set<CoverageLabelCode>([
  "availability_tracking_off",
  "snapshot_stale",
  "route_hints_unavailable",
  "ha_areas_not_linked",
]);

export interface EvidenceCoverageItemViewModel {
  label: string;
  helper: string;
  tone: DecisionPillTone;
}

export interface EvidenceCoverageStripViewModel {
  items: EvidenceCoverageItemViewModel[];
}

function sortNetworkCoverageItems(items: DataCoverageDto[]): DataCoverageDto[] {
  return [...items].sort((left, right) => {
    const leftIndex = NETWORK_ORDER_INDEX.get(left.label_code) ?? NETWORK_COVERAGE_STRIP_ORDER.length;
    const rightIndex =
      NETWORK_ORDER_INDEX.get(right.label_code) ?? NETWORK_COVERAGE_STRIP_ORDER.length;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return left.label_code.localeCompare(right.label_code);
  });
}

function sortDeviceCoverageItems(items: DataCoverageDto[]): DataCoverageDto[] {
  return [...items].sort((left, right) => {
    const leftDimension =
      DEVICE_DIMENSION_ORDER_INDEX.get(left.dimension) ?? DEVICE_COVERAGE_DIMENSION_ORDER.length;
    const rightDimension =
      DEVICE_DIMENSION_ORDER_INDEX.get(right.dimension) ?? DEVICE_COVERAGE_DIMENSION_ORDER.length;
    if (leftDimension !== rightDimension) return leftDimension - rightDimension;
    const leftLabel =
      DEVICE_LABEL_ORDER_INDEX.get(left.label_code) ?? DEVICE_COVERAGE_LABEL_ORDER.length;
    const rightLabel =
      DEVICE_LABEL_ORDER_INDEX.get(right.label_code) ?? DEVICE_COVERAGE_LABEL_ORDER.length;
    if (leftLabel !== rightLabel) return leftLabel - rightLabel;
    return left.label_code.localeCompare(right.label_code);
  });
}

export function buildEvidenceCoverageStripViewModel(
  coverage: DataCoverageDto[],
  options?: {
    filterLabelCodes?: ReadonlySet<CoverageLabelCode>;
    sort?: "network" | "device";
  },
): EvidenceCoverageStripViewModel {
  const filtered = options?.filterLabelCodes
    ? coverage.filter((item) => options.filterLabelCodes!.has(item.label_code))
    : coverage;

  const sorted =
    options?.sort === "device"
      ? sortDeviceCoverageItems(filtered)
      : sortNetworkCoverageItems(filtered);

  return {
    items: sorted.map((item) => {
      const params = item.params ?? {};
      return {
        label: coverageLabel(item.label_code, params),
        helper: coverageHelperText(item.label_code, params),
        tone: coverageTone(item.label_code),
      };
    }),
  };
}

export function buildDeviceCoverageStripViewModel(
  coverage: DataCoverageDto[],
): EvidenceCoverageStripViewModel {
  return buildEvidenceCoverageStripViewModel(coverage, { sort: "device" });
}
