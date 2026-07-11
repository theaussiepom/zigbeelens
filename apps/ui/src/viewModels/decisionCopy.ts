/**
 * User-facing copy for shared decision statuses, reasons and coverage labels.
 *
 * Backend decision services emit stable codes plus params. This module maps
 * them to approved prose for UI and reports. Do not invent diagnostic meaning
 * in components — map it here instead.
 */

import type { CoverageLabelCode, DecisionStatus } from "@/types/decisions";
import type { DecisionPillTone } from "@/viewModels/types";

export const REASON_CODES = [
  "latest_snapshot_no_links",
  "selected_snapshot_had_links",
  "snapshot_link_count_changed",
  "route_hints_changed",
  "availability_tracking_off",
  "availability_history_building",
  "availability_status_unknown",
  "route_hints_unavailable",
  "ha_areas_not_linked",
  "snapshot_stale",
  "current_issue_present",
  "battery_low",
  "last_seen_stale",
  "reported_lqi_low",
  "recent_missing_links_present",
  "last_known_links_present",
  "passive_instability_hint_present",
  "shared_availability_event",
  "insufficient_history",
] as const;

export type ReasonCode = (typeof REASON_CODES)[number];

export const COVERAGE_LABEL_CODES = [
  "availability_tracking_off",
  "availability_history_building",
  "availability_status_unknown",
  "route_hints_unavailable",
  "ha_areas_not_linked",
  "snapshot_stale",
  "battery_history_sparse",
  "lqi_history_sparse",
] as const;

type CopyRenderer = (params: Record<string, unknown>) => string;

function countParam(params: Record<string, unknown>, key: string): number | null {
  const value = params[key];
  return typeof value === "number" ? value : null;
}

const REASON_COPY: Record<ReasonCode, CopyRenderer> = {
  latest_snapshot_no_links: () =>
    "Latest snapshot shows no links for this device.",
  selected_snapshot_had_links: (params) => {
    const count = countParam(params, "selected_snapshot_link_count");
    if (count === null) {
      return "Selected snapshot showed links for this device.";
    }
    return `Selected snapshot showed ${count} link${count === 1 ? "" : "s"} for this device.`;
  },
  snapshot_link_count_changed: (params) => {
    const latest = countParam(params, "latest_link_count");
    const selected = countParam(params, "selected_link_count");
    if (latest === null || selected === null) {
      return "Link counts differ between the selected snapshot and the latest snapshot.";
    }
    return `Link count changed from ${selected} in the selected snapshot to ${latest} in the latest snapshot.`;
  },
  route_hints_changed: () =>
    "Route-hint counts differ between snapshots. Route hints do not prove live routing changed.",
  availability_tracking_off: () =>
    "Availability tracking was off for the selected period.",
  availability_history_building: () =>
    "Availability history started after the selected snapshot.",
  availability_status_unknown: () =>
    "Availability status could not be confirmed for the selected period.",
  route_hints_unavailable: () => "Route hints are unavailable for this network.",
  ha_areas_not_linked: () => "Home Assistant areas are not linked for this device.",
  snapshot_stale: () => "Latest topology snapshot is stale.",
  current_issue_present: () =>
    "This device currently needs attention based on existing issue signals.",
  battery_low: () => "Battery is currently reported low.",
  last_seen_stale: () => "Last-seen reporting looks stale.",
  reported_lqi_low: () => "Reported link quality is low.",
  recent_missing_links_present: () =>
    "Recent missing links are shown for this device in the mesh view.",
  last_known_links_present: () =>
    "Last-known links are shown for this device in the mesh view.",
  passive_instability_hint_present: () =>
    "Passive investigation hints suggest instability worth checking.",
  shared_availability_event: () =>
    "Multiple devices changed availability around the same time.",
  insufficient_history: () => "Not enough history is available yet for a stronger judgement.",
};

const COVERAGE_LABEL_COPY: Record<CoverageLabelCode, string> = {
  availability_tracking_off: "Availability tracking off",
  availability_history_building: "Availability history building",
  availability_status_unknown: "Availability status unknown",
  route_hints_unavailable: "Route hints unavailable",
  ha_areas_not_linked: "HA areas not linked",
  snapshot_stale: "Snapshot stale",
  battery_history_sparse: "Battery history sparse",
  lqi_history_sparse: "LQI history sparse",
};

const DECISION_STATUS_LABELS: Record<DecisionStatus, string> = {
  informational: "Informational",
  no_notable_change: "No notable change",
  changed: "Changed",
  watch: "Watch",
  worth_reviewing: "Worth reviewing",
  review_first: "Review first",
  improve_data_coverage: "Improve data coverage",
  data_unavailable: "Data unavailable",
};

const DECISION_STATUS_COMPACT_LABELS: Record<DecisionStatus, string> = {
  informational: "Info",
  no_notable_change: "Similar",
  changed: "Changed",
  watch: "Watch",
  worth_reviewing: "Worth reviewing",
  review_first: "Review first",
  improve_data_coverage: "Coverage",
  data_unavailable: "Unavailable",
};

const DECISION_STATUS_TONES: Record<DecisionStatus, DecisionPillTone> = {
  informational: "info",
  no_notable_change: "neutral",
  changed: "neutral",
  watch: "watch",
  worth_reviewing: "action",
  review_first: "action",
  improve_data_coverage: "coverage",
  data_unavailable: "muted",
};

export function isKnownReasonCode(code: string): code is ReasonCode {
  return (REASON_CODES as readonly string[]).includes(code);
}

export function isKnownCoverageLabelCode(
  labelCode: string,
): labelCode is CoverageLabelCode {
  return (COVERAGE_LABEL_CODES as readonly string[]).includes(labelCode);
}

export function isKnownDecisionStatus(status: string): status is DecisionStatus {
  return status in DECISION_STATUS_LABELS;
}

export function reasonText(
  code: string,
  params: Record<string, unknown> = {},
): string {
  if (!isKnownReasonCode(code)) {
    return "Details unavailable.";
  }
  return REASON_COPY[code](params);
}

export function coverageLabel(labelCode: string): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage status unknown";
  }
  return COVERAGE_LABEL_COPY[labelCode];
}

export function decisionStatusLabel(status: string): string {
  if (!isKnownDecisionStatus(status)) {
    return "Status unknown";
  }
  return DECISION_STATUS_LABELS[status];
}

export function decisionStatusCompactLabel(status: string): string {
  if (!isKnownDecisionStatus(status)) {
    return "Unknown";
  }
  return DECISION_STATUS_COMPACT_LABELS[status];
}

export function decisionStatusTone(status: string): DecisionPillTone {
  if (!isKnownDecisionStatus(status)) {
    return "muted";
  }
  return DECISION_STATUS_TONES[status];
}
