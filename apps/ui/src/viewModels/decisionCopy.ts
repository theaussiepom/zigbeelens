/**
 * User-facing copy for shared decision statuses, reasons and coverage labels.
 *
 * Backend decision services emit stable codes plus params. This module maps
 * them to approved prose for UI and reports. Do not invent diagnostic meaning
 * in components — map it here instead.
 */

import type { CoverageLabelCode, DecisionStatus } from "@zigbeelens/shared";
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
  "observed_lqi_trend",
  "reported_lqi_declining",
  "model_pattern_observed",
] as const;

export type ReasonCode = (typeof REASON_CODES)[number];

export const COVERAGE_LABEL_CODES = [
  "availability_tracking_off",
  "availability_history_building",
  "availability_status_unknown",
  "availability_available",
  "route_hints_unavailable",
  "ha_areas_not_linked",
  "snapshot_stale",
  "battery_history_sparse",
  "battery_history_available",
  "lqi_history_sparse",
  "lqi_history_available",
  "last_seen_available",
  "last_seen_unknown",
  "last_payload_available",
  "last_payload_unknown",
  "topology_history_available",
  "topology_history_sparse",
  "topology_history_not_observed",
  "ha_area_linked",
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

function stringParam(params: Record<string, unknown>, key: string): string | null {
  const value = params[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function sampleCountLabel(count: number): string {
  return `${count} sample${count === 1 ? "" : "s"}`;
}

function topologyHistoryLabel(
  params: Record<string, unknown>,
  fallback: string,
): string {
  const observed = countParam(params, "observed_snapshot_count");
  const window = countParam(params, "snapshot_window_count");
  if (observed === null || window === null) {
    return fallback;
  }
  return `Topology history: ${observed} of ${window} snapshots`;
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
    const p75 = countParam(params, "interval_minutes_p75");
    if (p25 === null || p75 === null) {
      return "Stored payload observations show a reporting rhythm for this device.";
    }
    if (p25 === p75) {
      return `Usually reports about every ${formatMinuteSpan(p25)} based on stored payload history.`;
    }
    return `Usually reports every ${formatMinuteSpan(p25)}–${formatMinuteSpan(p75)} based on stored payload history.`;
  },
  reporting_silence_beyond_expected: (params) => {
    const silenceMinutes = countParam(params, "silence_minutes");
    if (silenceMinutes === null) {
      return "Current payload silence is longer than the observed reporting cadence.";
    }
    return `No payload observed for ${formatMinuteSpan(silenceMinutes)}.`;
  },
  observed_lqi_trend: (params) => {
    const earlierMedian = countParam(params, "earlier_median");
    const recentMedian = countParam(params, "recent_median");
    if (earlierMedian !== null && recentMedian !== null) {
      return `Reported link quality median changed from ${earlierMedian} to ${recentMedian} across the compared stored observation windows.`;
    }
    const sampleCount = countParam(params, "sample_count");
    const windowSize = countParam(params, "window_size");
    if (sampleCount !== null && windowSize !== null) {
      return `Stored reported link-quality observations from ${sampleCountLabel(sampleCount)} were compared across ${windowSize}-observation windows.`;
    }
    return "Stored reported link-quality observations show a trend across compared observation windows.";
  },
  reported_lqi_declining: () =>
    "Reported link quality is lower in the recent stored observations.",
  model_pattern_observed: (params) => {
    const affectedCount = countParam(params, "affected_count");
    const groupSize = countParam(params, "group_size");
    const lookbackDays = countParam(params, "lookback_days");
    const currentDeviceAffected = params.current_device_affected === true;
    if (affectedCount !== null && groupSize !== null && lookbackDays !== null) {
      const dayWord = lookbackDays === 1 ? "day" : "days";
      if (currentDeviceAffected) {
        return `This device is one of ${affectedCount} of ${groupSize} devices with the same model that went offline in the last ${lookbackDays} ${dayWord}.`;
      }
      return `Other devices with the same model show a recent availability pattern: ${affectedCount} of ${groupSize} went offline in the last ${lookbackDays} ${dayWord}.`;
    }
    return "Multiple devices with the same stored model identity show a recent availability pattern worth reviewing.";
  },
};

/** Phase 3E network/generic coverage labels. */
const COVERAGE_LABEL_COPY: Record<CoverageLabelCode, string> = {
  availability_tracking_off: "Availability tracking off",
  availability_history_building: "Availability history building",
  availability_status_unknown: "Availability status unknown",
  availability_available: "Availability: available",
  route_hints_unavailable: "Route hints unavailable",
  ha_areas_not_linked: "HA areas not linked",
  snapshot_stale: "Snapshot stale",
  battery_history_sparse: "Battery history sparse",
  battery_history_available: "Battery history available",
  lqi_history_sparse: "LQI history sparse",
  lqi_history_available: "LQI history available",
  last_seen_available: "Last seen: available",
  last_seen_unknown: "Last seen: unknown",
  last_payload_available: "Last payload: available",
  last_payload_unknown: "Last payload: unknown",
  topology_history_available: "Topology history: available",
  topology_history_sparse: "Topology history: sparse",
  topology_history_not_observed: "Topology history: not observed",
  ha_area_linked: "HA area: linked",
};

/** Phase 3E network/generic coverage helper copy. */
const COVERAGE_HELPER_COPY: Record<CoverageLabelCode, string> = {
  availability_tracking_off:
    "Enable Zigbee2MQTT availability and last-seen reporting for offline history, passive hints and reports.",
  availability_history_building:
    "Availability tracking is enabled, but ZigbeeLens only has history from when it was turned on.",
  availability_status_unknown:
    "ZigbeeLens cannot confirm availability/last-seen coverage for this period.",
  availability_available:
    "This device currently reports an explicit online or offline availability state.",
  route_hints_unavailable:
    "Route-hint evidence was not available from the latest topology snapshot. This does not mean routes are absent or prove current routing.",
  ha_areas_not_linked:
    "Home Assistant area enrichment is not linked. Grouping and report context may be less useful. This is not a Zigbee network fault.",
  snapshot_stale:
    "The latest stored topology snapshot is older than the configured capture cadence. Interpret topology evidence as older stored evidence.",
  battery_history_sparse:
    "Battery history is sparse for this network. Battery-related interpretation may be limited.",
  battery_history_available:
    "Enough stored battery history exists for coverage interpretation.",
  lqi_history_sparse:
    "Link-quality history is sparse for this network. LQI-related interpretation may be limited.",
  lqi_history_available:
    "Enough stored link-quality history exists for coverage interpretation.",
  last_seen_available:
    "A valid last-seen timestamp is stored for this device.",
  last_seen_unknown:
    "No valid last-seen timestamp is stored for this device.",
  last_payload_available:
    "A valid last-payload timestamp is stored for this device.",
  last_payload_unknown:
    "No valid last-payload timestamp is stored for this device.",
  topology_history_available:
    "This device appeared in every considered stored topology snapshot.",
  topology_history_sparse:
    "This device was absent from some considered stored topology snapshots.",
  topology_history_not_observed:
    "This device was not observed in any considered stored topology snapshot.",
  ha_area_linked:
    "Home Assistant area enrichment is linked for this device.",
};

const DEVICE_COVERAGE_LABEL_RENDERERS: Partial<Record<CoverageLabelCode, CopyRenderer>> = {
  availability_tracking_off: () => "Availability: tracking off",
  availability_history_building: () => "Availability: building",
  availability_status_unknown: () => "Availability: unknown",
  availability_available: () => "Availability: available",
  last_seen_available: () => "Last seen: available",
  last_seen_unknown: () => "Last seen: unknown",
  last_payload_available: () => "Last payload: available",
  last_payload_unknown: () => "Last payload: unknown",
  battery_history_available: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) return "Battery history: available";
    return `Battery history: available (${sampleCountLabel(count)})`;
  },
  battery_history_sparse: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) return "Battery history: sparse";
    return `Battery history: sparse (${sampleCountLabel(count)})`;
  },
  lqi_history_available: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) return "LQI history: available";
    return `LQI history: available (${sampleCountLabel(count)})`;
  },
  lqi_history_sparse: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) return "LQI history: sparse";
    return `LQI history: sparse (${sampleCountLabel(count)})`;
  },
  topology_history_available: (params) =>
    topologyHistoryLabel(params, "Topology history: available"),
  topology_history_sparse: (params) =>
    topologyHistoryLabel(params, "Topology history: sparse"),
  topology_history_not_observed: (params) =>
    topologyHistoryLabel(params, "Topology history: not observed"),
  ha_area_linked: (params) => {
    const areaName = stringParam(params, "area_name");
    const areaId = stringParam(params, "area_id");
    if (areaName) return `HA area: ${areaName}`;
    if (areaId) return `HA area: ${areaId}`;
    return "HA area: linked";
  },
  ha_areas_not_linked: () => "HA area: missing",
};

const DEVICE_COVERAGE_LABEL_COPY: Record<CoverageLabelCode, string> = {
  ...COVERAGE_LABEL_COPY,
  availability_tracking_off: "Availability: tracking off",
  availability_history_building: "Availability: building",
  availability_status_unknown: "Availability: unknown",
  ha_areas_not_linked: "HA area: missing",
};

function deviceTopologyHistoryHelper(
  labelCode: CoverageLabelCode,
  params: Record<string, unknown>,
): string {
  const observed = countParam(params, "observed_snapshot_count");
  const window = countParam(params, "snapshot_window_count");

  if (labelCode === "topology_history_not_observed") {
    if (window === 0) {
      return "No complete stored topology snapshots are available to assess this device yet.";
    }
    if (window !== null && observed === 0) {
      return "This device was not observed in the considered stored topology snapshots.";
    }
  }

  if (labelCode === "topology_history_sparse") {
    return "This device was absent from some considered stored topology snapshots.";
  }

  if (labelCode === "topology_history_available") {
    return "This device appeared in every considered stored topology snapshot.";
  }

  return COVERAGE_HELPER_COPY[labelCode];
}

const DEVICE_COVERAGE_HELPER_COPY: Record<CoverageLabelCode, string | CopyRenderer> = {
  availability_tracking_off:
    "Availability tracking is not available for this device because usable Zigbee2MQTT availability evidence is not currently being collected.",
  availability_history_building:
    "ZigbeeLens has not stored enough availability history for this device yet.",
  availability_status_unknown:
    "ZigbeeLens has availability history for this device, but the current availability state is not confirmed.",
  availability_available:
    "This device currently reports an explicit online or offline availability state.",
  route_hints_unavailable: COVERAGE_HELPER_COPY.route_hints_unavailable,
  ha_areas_not_linked:
    "Home Assistant area enrichment is not linked for this device. Grouping and report context may be less useful. This is not a Zigbee network fault.",
  snapshot_stale: COVERAGE_HELPER_COPY.snapshot_stale,
  battery_history_sparse: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) {
      return "Battery history is sparse for this device. Battery-related interpretation may be limited.";
    }
    return `Battery history is sparse for this device (${sampleCountLabel(count)}). Battery-related interpretation may be limited.`;
  },
  battery_history_available: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) {
      return "Enough stored battery history exists for coverage interpretation on this device.";
    }
    return `Enough stored battery history exists for coverage interpretation (${sampleCountLabel(count)}).`;
  },
  lqi_history_sparse: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) {
      return "Link-quality history is sparse for this device. LQI-related interpretation may be limited.";
    }
    return `Link-quality history is sparse for this device (${sampleCountLabel(count)}). LQI-related interpretation may be limited.`;
  },
  lqi_history_available: (params) => {
    const count = countParam(params, "sample_count");
    if (count === null) {
      return "Enough stored link-quality history exists for coverage interpretation on this device.";
    }
    return `Enough stored link-quality history exists for coverage interpretation (${sampleCountLabel(count)}).`;
  },
  last_seen_available:
    "A valid last-seen timestamp is stored for this device.",
  last_seen_unknown:
    "No valid last-seen timestamp is stored for this device.",
  last_payload_available:
    "A valid last-payload timestamp is stored for this device.",
  last_payload_unknown:
    "No valid last-payload timestamp is stored for this device.",
  topology_history_available: (params) =>
    deviceTopologyHistoryHelper("topology_history_available", params),
  topology_history_sparse: (params) =>
    deviceTopologyHistoryHelper("topology_history_sparse", params),
  topology_history_not_observed: (params) =>
    deviceTopologyHistoryHelper("topology_history_not_observed", params),
  ha_area_linked: (params) => {
    const areaName = stringParam(params, "area_name");
    const areaId = stringParam(params, "area_id");
    if (areaName && areaId) {
      return `Home Assistant area enrichment is linked (${areaName}, id ${areaId}).`;
    }
    if (areaName) {
      return `Home Assistant area enrichment is linked (${areaName}).`;
    }
    if (areaId) {
      return `Home Assistant area enrichment is linked (area id ${areaId}).`;
    }
    return "Home Assistant area enrichment is linked for this device.";
  },
};

const COVERAGE_TONES: Record<CoverageLabelCode, DecisionPillTone> = {
  availability_tracking_off: "coverage",
  availability_history_building: "watch",
  availability_status_unknown: "muted",
  availability_available: "neutral",
  route_hints_unavailable: "muted",
  ha_areas_not_linked: "coverage",
  snapshot_stale: "watch",
  battery_history_sparse: "muted",
  battery_history_available: "neutral",
  lqi_history_sparse: "muted",
  lqi_history_available: "neutral",
  last_seen_available: "neutral",
  last_seen_unknown: "muted",
  last_payload_available: "neutral",
  last_payload_unknown: "muted",
  topology_history_available: "neutral",
  topology_history_sparse: "muted",
  topology_history_not_observed: "muted",
  ha_area_linked: "neutral",
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
  "reported_link_quality_changed",
] as const;

export type HeadlineCode = (typeof HEADLINE_CODES)[number];

export const LIMITATION_CODES = [
  "absence_from_latest_not_failure",
  "route_hints_not_live_routing",
  "availability_limits_interpretation",
  "extended_silence_not_failure",
  "reported_lqi_not_path_failure",
  "model_pattern_not_causal",
] as const;

export type LimitationCode = (typeof LIMITATION_CODES)[number];

export const SUGGESTED_CHECK_CODES = [
  "confirm_powered",
  "confirm_reporting_in_z2m",
  "compare_earlier_snapshot",
  "route_hints_context_only",
  "enable_availability_reporting",
  "check_battery_level",
  "compare_same_model_device_context",
  "review_same_model_availability_history",
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
  reported_link_quality_changed: "Reported link quality changed",
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
  reported_lqi_not_path_failure: () =>
    "A drop in reported link quality does not prove a Zigbee path, route, or device failure.",
  model_pattern_not_causal: () =>
    "A pattern among devices with the same stored model identity does not prove a model defect, manufacturer fault, or shared cause.",
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
  compare_same_model_device_context: () =>
    "Compare power, placement, firmware or version information where stored for devices with the same model identity.",
  review_same_model_availability_history: () =>
    "Review availability timing for affected devices with the same model identity.",
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

/** Network/generic coverage label copy (Phase 3E). */
export function coverageLabel(
  labelCode: string,
  _params: Record<string, unknown> = {},
): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage status unknown";
  }
  return COVERAGE_LABEL_COPY[labelCode];
}

/** Per-device coverage row labels (Phase 4C). */
export function deviceCoverageLabel(
  labelCode: string,
  params: Record<string, unknown> = {},
): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage status unknown";
  }
  const renderer = DEVICE_COVERAGE_LABEL_RENDERERS[labelCode];
  if (renderer) {
    return renderer(params);
  }
  return DEVICE_COVERAGE_LABEL_COPY[labelCode];
}

/** Network/generic coverage helper copy (Phase 3E). */
export function coverageHelperText(
  labelCode: string,
  _params: Record<string, unknown> = {},
): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage details are limited. Interpret other evidence conservatively.";
  }
  return COVERAGE_HELPER_COPY[labelCode];
}

/** Per-device coverage helper copy (Phase 4C). */
export function deviceCoverageHelperText(
  labelCode: string,
  params: Record<string, unknown> = {},
): string {
  if (!isKnownCoverageLabelCode(labelCode)) {
    return "Coverage details are limited. Interpret other evidence conservatively.";
  }
  const helper = DEVICE_COVERAGE_HELPER_COPY[labelCode];
  if (typeof helper === "function") {
    return helper(params);
  }
  return helper;
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
