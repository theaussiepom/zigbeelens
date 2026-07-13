/**
 * Evidence coverage strip ViewModel — maps DataCoverage DTOs to UI-ready items.
 */

import type { CoverageLabelCode, DataCoverageDto } from "@/types/decisions";
import {
  coverageHelperText,
  coverageLabel,
  coverageTone,
} from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

const COVERAGE_STRIP_ORDER: CoverageLabelCode[] = [
  "availability_tracking_off",
  "availability_history_building",
  "availability_status_unknown",
  "snapshot_stale",
  "route_hints_unavailable",
  "ha_areas_not_linked",
  "battery_history_sparse",
  "lqi_history_sparse",
];

const ORDER_INDEX = new Map(
  COVERAGE_STRIP_ORDER.map((code, index) => [code, index] as const),
);

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

function sortCoverageItems(items: DataCoverageDto[]): DataCoverageDto[] {
  return [...items].sort((left, right) => {
    const leftIndex = ORDER_INDEX.get(left.label_code) ?? COVERAGE_STRIP_ORDER.length;
    const rightIndex = ORDER_INDEX.get(right.label_code) ?? COVERAGE_STRIP_ORDER.length;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return left.label_code.localeCompare(right.label_code);
  });
}

export function buildEvidenceCoverageStripViewModel(
  coverage: DataCoverageDto[],
  options?: { filterLabelCodes?: ReadonlySet<CoverageLabelCode> },
): EvidenceCoverageStripViewModel {
  const filtered = options?.filterLabelCodes
    ? coverage.filter((item) => options.filterLabelCodes!.has(item.label_code))
    : coverage;

  return {
    items: sortCoverageItems(filtered).map((item) => ({
      label: coverageLabel(item.label_code),
      helper: coverageHelperText(item.label_code),
      tone: coverageTone(item.label_code),
    })),
  };
}
