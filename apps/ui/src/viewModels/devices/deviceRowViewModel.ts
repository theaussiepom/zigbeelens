/**
 * Devices inventory row ViewModel (Phase 5B-2).
 *
 * Owns human labels, decision sort order, safe fallbacks, and links.
 * React pages render this — they do not map decision status codes.
 */

import type { Availability, DeviceSummary } from "@zigbeelens/shared";
import {
  availabilityLabel,
  devicePath,
  deviceTypeLabel,
  formatTime,
  relativeTime,
} from "@/lib/format";
import type { DecisionStatus } from "@/types/decisions";
import {
  decisionStatusLabel,
  isKnownDecisionStatus,
} from "@/viewModels/decisionCopy";
import {
  buildDeviceDecisionBadgeViewModel,
  unknownDeviceDecisionBadgeViewModel,
  type DeviceDecisionBadgeViewModel,
} from "./deviceDecisionBadgeViewModel";

/** Stable decision-led sort order for the Devices inventory. */
export const DEVICE_DECISION_SORT_ORDER: readonly DecisionStatus[] = [
  "review_first",
  "worth_reviewing",
  "improve_data_coverage",
  "watch",
  "changed",
  "informational",
  "no_notable_change",
  "data_unavailable",
] as const;

export interface DeviceDecisionFilterOption {
  value: DecisionStatus;
  label: string;
}

export const DEVICE_DECISION_FILTER_OPTIONS: readonly DeviceDecisionFilterOption[] =
  DEVICE_DECISION_SORT_ORDER.map((value) => ({
    value,
    label: decisionStatusLabel(value),
  }));

export type DeviceAvailabilityTone = "online" | "offline" | "unknown";

export interface DeviceRowViewModel {
  key: string;
  networkId: string;
  ieeeAddress: string;
  name: string;
  secondaryLabel: string;
  decisionStatus: string | null;
  decision: DeviceDecisionBadgeViewModel;
  availability: Availability;
  availabilityLabel: string;
  availabilityTone: DeviceAvailabilityTone;
  coverageSummary: string | null;
  hasCoverageLimitations: boolean;
  batterySummary: string;
  lqiSummary: string;
  lastSeenLabel: string;
  lastSeenExact: string;
  areaLabel: string | null;
  modelLabel: string;
  areaSearchText: string | null;
  manufacturer: string | null;
  model: string | null;
  deviceHref: string;
  meshHref: string;
}

export interface DeviceInventorySummaryCounts {
  total: number;
  reviewFirst: number;
  worthReviewing: number;
  coverage: number;
}

function unknownDecisionBadge(): DeviceDecisionBadgeViewModel {
  return unknownDeviceDecisionBadgeViewModel();
}

function coverageSummaryFromLabels(labels: string[]): string | null {
  if (labels.length === 0) {
    return null;
  }
  if (labels.length === 1) {
    return labels[0];
  }
  return `${labels[0]} +${labels.length - 1} more`;
}

function availabilityTone(availability: Availability): DeviceAvailabilityTone {
  if (availability === "online") {
    return "online";
  }
  if (availability === "offline") {
    return "offline";
  }
  return "unknown";
}

function modelLabelForDevice(device: DeviceSummary): string {
  const manufacturer = device.manufacturer?.trim() || null;
  const model = device.model?.trim() || null;
  if (manufacturer && model) {
    return `${manufacturer} · ${model}`;
  }
  if (model) {
    return model;
  }
  if (manufacturer) {
    return manufacturer;
  }
  return "Model unknown";
}

function telemetrySummary(kind: "Battery" | "LQI", value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return `${kind} —`;
  }
  if (kind === "Battery") {
    return `Battery ${value}%`;
  }
  return `LQI ${value}`;
}

export function decisionSortRank(status: string | null | undefined): number {
  if (!status || !isKnownDecisionStatus(status)) {
    return DEVICE_DECISION_SORT_ORDER.length;
  }
  return DEVICE_DECISION_SORT_ORDER.indexOf(status);
}

export function compareDevicesByDecision(
  a: DeviceRowViewModel,
  b: DeviceRowViewModel,
): number {
  const rankDiff = decisionSortRank(a.decisionStatus) - decisionSortRank(b.decisionStatus);
  if (rankDiff !== 0) {
    return rankDiff;
  }
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

export function buildDeviceRowViewModel(device: DeviceSummary): DeviceRowViewModel {
  const decision =
    device.decision != null
      ? buildDeviceDecisionBadgeViewModel(device.decision)
      : unknownDecisionBadge();
  const area = device.ha_area?.trim() || null;

  return {
    key: `${device.network_id}:${device.ieee_address}`,
    networkId: device.network_id,
    ieeeAddress: device.ieee_address,
    name: device.friendly_name,
    secondaryLabel: deviceTypeLabel(device.device_type),
    decisionStatus: device.decision?.status ?? null,
    decision,
    availability: device.availability,
    availabilityLabel: availabilityLabel(device.availability),
    availabilityTone: availabilityTone(device.availability),
    coverageSummary: coverageSummaryFromLabels(decision.coverageLabels),
    hasCoverageLimitations: (device.decision?.coverage_label_codes.length ?? 0) > 0,
    batterySummary: telemetrySummary("Battery", device.battery),
    lqiSummary: telemetrySummary("LQI", device.linkquality),
    lastSeenLabel: relativeTime(device.last_seen),
    lastSeenExact: formatTime(device.last_seen),
    areaLabel: area,
    modelLabel: modelLabelForDevice(device),
    areaSearchText: area,
    manufacturer: device.manufacturer ?? null,
    model: device.model ?? null,
    deviceHref: devicePath(device.network_id, device.ieee_address),
    meshHref: `/topology/${device.network_id}`,
  };
}

export function buildDeviceInventoryRows(
  devices: DeviceSummary[],
): DeviceRowViewModel[] {
  return devices.map(buildDeviceRowViewModel).sort(compareDevicesByDecision);
}

export function deviceInventorySummaryCounts(
  rows: DeviceRowViewModel[],
): DeviceInventorySummaryCounts {
  let reviewFirst = 0;
  let worthReviewing = 0;
  let coverage = 0;
  for (const row of rows) {
    if (row.decisionStatus === "review_first") {
      reviewFirst += 1;
    } else if (row.decisionStatus === "worth_reviewing") {
      worthReviewing += 1;
    }
    if (row.hasCoverageLimitations) {
      coverage += 1;
    }
  }
  return {
    total: rows.length,
    reviewFirst,
    worthReviewing,
    coverage,
  };
}

export interface DeviceInventoryFilters {
  networkId: string;
  decisionStatus: string;
  availability: string;
  coverageFilter: "" | "limitations";
  search: string;
}

export function filterDeviceInventoryRows(
  rows: DeviceRowViewModel[],
  filters: DeviceInventoryFilters,
): DeviceRowViewModel[] {
  const q = filters.search.trim().toLowerCase();
  return rows.filter((row) => {
    if (filters.networkId && row.networkId !== filters.networkId) {
      return false;
    }
    if (filters.decisionStatus) {
      if (row.decisionStatus !== filters.decisionStatus) {
        return false;
      }
    }
    if (filters.availability && row.availability !== filters.availability) {
      return false;
    }
    if (filters.coverageFilter === "limitations" && !row.hasCoverageLimitations) {
      return false;
    }
    if (q) {
      const parts = [
        row.name,
        row.ieeeAddress,
        row.manufacturer ?? "",
        row.model ?? "",
        row.areaSearchText ?? "",
      ];
      const hay = parts.join(" ").toLowerCase();
      if (!hay.includes(q)) {
        return false;
      }
    }
    return true;
  });
}
