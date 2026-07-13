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
  "observed_reporting_rhythm",
  "reporting_silence_beyond_expected",
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

function formatMinuteSpan(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `${hours} hour${hours === 1 ? "" : "s"} ${remainder} minute${remainder === 1 ? "" : "s"}`;
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
  availability_tracking_off: () => "Availability tracking is off.",
  availability_history_building: () => "Availability history is still building.",
  availability_status_unknown: () =>
    "Availability status could not be confirmed from stored evidence.",
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
  observed_reporting_rhythm: (params) => {
    const p25 = countParam(params, "interval_minutes_p25");
    const median = countParam(params, "interval_minutes_median");
    const p75 = countParam(params, "interval_minutes_p75");
    if (p25 === null || p75 === null || median === null) {
      return "Stored payload observations show a reporting rhythm for this device.";
    }
    if (p25 === p75) {
      return `Usually reports about every ${formatMinuteSpan(p25)} based on stored payload history.`;
    }
    return `Usually reports every ${formatMinuteSpan(p25)}–${formatMinuteSpan(p75)} based on stored payload history (median ${formatMinuteSpan(median)}).`;
  },
  reporting_silence_beyond_expected: (params) => {
    const silenceMinutes = countParam(params, "silence_minutes");
    const thresholdMinutes = countParam(params, "extended_silence_threshold_minutes");
    if (silenceMinutes === null || thresholdMinutes === null) {
      return "Current payload silence is longer than the observed reporting cadence.";
    }
    return `No payload observed for ${formatMinuteSpan(silenceMinutes)}, beyond the extended-silence threshold of ${formatMinuteSpan(thresholdMinutes)}.`;
  },
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

const COVERAGE_HELPER_COPY: Record<CoverageLabelCode, string> = {
  availability_tracking_off:
    "Enable Zigbee2MQTT availability and last-seen reporting for offline history, passive hints and reports.",
  availability_history_building:
    "Availability tracking is enabled, but ZigbeeLens only has history from when it was turned on.",
  availability_status_unknown:
    "ZigbeeLens cannot confirm availability/last-seen coverage for this period.",
  route_hints_unavailable:
    "Route-hint evidence was not available from the latest topology snapshot. This does not mean routes are absent or prove current routing.",
  ha_areas_not_linked:
    "Home Assistant area enrichment is not linked. Grouping and report context may be less useful. This is not a Zigbee network fault.",
  snapshot_stale:
    "The latest stored topology snapshot is older than the configured capture cadence. Interpret topology evidence as older stored evidence.",
  battery_history_sparse:
    "Battery history is sparse for this network. Battery-related interpretation may be limited.",
  lqi_history_sparse:
    "Link-quality history is sparse for this network. LQI-related interpretation may be limited.",
};

const COVERAGE_TONES: Record<CoverageLabelCode, DecisionPillTone> = {
  availability_tracking_off: "coverage",
  availability_history_building: "watch",
  availability_status_unknown: "muted",
  route_hints_unavailable: "muted",
  ha_areas_not_linked: "coverage",
  snapshot_stale: "watch",
  battery_history_sparse: "muted",
  lqi_history_sparse: "muted",
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

export const HEADLINE_CODES = [
  "current_issue_present",
  "topology_evidence_gap",
  "availability_tracking_needed",
  "stale_last_seen",
  "low_battery",
  "data_coverage_gaps",
  "no_notable_signals",
  "extended_reporting_silence",
] as const;

export type HeadlineCode = (typeof HEADLINE_CODES)[number];

export const LIMITATION_CODES = [
  "absence_from_latest_not_failure",
  "route_hints_not_live_routing",
  "availability_limits_interpretation",
  "extended_silence_not_failure",
] as const;

export type LimitationCode = (typeof LIMITATION_CODES)[number];

export const SUGGESTED_CHECK_CODES = [
  "confirm_powered",
  "confirm_reporting_in_z2m",
  "compare_earlier_snapshot",
  "route_hints_context_only",
  "enable_availability_reporting",
  "check_battery_level",
] as const;

export type SuggestedCheckCode = (typeof SUGGESTED_CHECK_CODES)[number];

const HEADLINE_COPY: Record<HeadlineCode, string> = {
  current_issue_present: "Current issue needs attention",
  topology_evidence_gap: "Topology evidence gap",
  availability_tracking_needed: "Availability tracking needed",
  stale_last_seen: "Last seen looks stale",
  low_battery: "Battery reported low",
  data_coverage_gaps: "Data coverage gaps",
  no_notable_signals: "No notable signals",
  extended_reporting_silence: "Extended reporting silence",
};

const LIMITATION_COPY: Record<LimitationCode, CopyRenderer> = {
  absence_from_latest_not_failure: () =>
    "Absence from the latest snapshot does not prove the device failed or left the network.",
  route_hints_not_live_routing: () =>
    "Route hints describe stored snapshot evidence. They do not prove live routing paths.",
  availability_limits_interpretation: () =>
    "Availability and last-seen evidence is limited for this period, so offline or stale interpretation is constrained.",
  extended_silence_not_failure: () =>
    "Silence longer than the observed reporting rhythm does not prove the device failed, lost power, or left the network.",
};

const SUGGESTED_CHECK_COPY: Record<SuggestedCheckCode, CopyRenderer> = {
  confirm_powered: () => "Confirm the device is powered.",
  confirm_reporting_in_z2m: () => "Confirm the device is reporting in Zigbee2MQTT.",
  compare_earlier_snapshot: () =>
    "Compare an earlier topology snapshot for this device.",
  route_hints_context_only: () =>
    "Treat route hints as context only — they do not prove current routing.",
  enable_availability_reporting: () =>
    "Enable Zigbee2MQTT availability and last-seen reporting.",
  check_battery_level: (params) => {
    const percent = countParam(params, "battery_percent");
    if (percent === null) return "Check the reported battery level.";
    return `Check the reported battery level (${percent}%).`;
  },
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
  return Object.prototype.hasOwnProperty.call(DECISION_STATUS_LABELS, status);
}

export function isKnownHeadlineCode(code: string): code is HeadlineCode {
  return (HEADLINE_CODES as readonly string[]).includes(code);
}

export function isKnownLimitationCode(code: string): code is LimitationCode {
  return (LIMITATION_CODES as readonly string[]).includes(code);
}

export function isKnownSuggestedCheckCode(code: string): code is SuggestedCheckCode {
  return (SUGGESTED_CHECK_CODES as readonly string[]).includes(code);
}

export function headlineText(code: string): string {
  if (!isKnownHeadlineCode(code)) {
    return "Device story summary unavailable.";
  }
  return HEADLINE_COPY[code];
}

export function limitationText(
  code: string,
  params: Record<string, unknown> = {},
): string {
  if (!isKnownLimitationCode(code)) {
    return "Interpretation is limited for this evidence.";
  }
  return LIMITATION_COPY[code](params);
}

export function suggestedCheckText(
  code: string,
  params: Record<string, unknown> = {},
): string {
  if (!isKnownSuggestedCheckCode(code)) {
    return "Review stored evidence before taking action.";
  }
  return SUGGESTED_CHECK_COPY[code](params);
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

export function coverageHelperText(labelCode: string): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage details are limited. Interpret other evidence conservatively.";
  }
  return COVERAGE_HELPER_COPY[labelCode];
}

export function coverageTone(labelCode: string): DecisionPillTone {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "muted";
  }
  return COVERAGE_TONES[labelCode];
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
