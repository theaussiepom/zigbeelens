/**
 * Decision contract v2 validation for live Core payloads.
 *
 * Missing required decision fields are protocol failures — React must not
 * synthesize data-unavailable badges after Core claims validity.
 */

import type {
  CoverageLabelCode,
  DashboardPayload,
  DecisionBadge,
  DecisionCountSummary,
  DecisionPriority,
  DecisionStatus,
  DeviceDetail,
  DeviceSummary,
  Incident,
  LegacyStoredReportBody,
  NetworkSummary,
  ReportDetailV3,
} from "@zigbeelens/shared";
import { ApiError } from "@/lib/api";

const DECISION_STATUSES: readonly DecisionStatus[] = [
  "informational",
  "no_notable_change",
  "changed",
  "watch",
  "worth_reviewing",
  "review_first",
  "improve_data_coverage",
  "data_unavailable",
];

const DECISION_PRIORITIES: readonly DecisionPriority[] = ["none", "low", "medium", "high"];

export function isDecisionStatus(value: unknown): value is DecisionStatus {
  return typeof value === "string" && (DECISION_STATUSES as readonly string[]).includes(value);
}

export function isDecisionPriority(value: unknown): value is DecisionPriority {
  return typeof value === "string" && (DECISION_PRIORITIES as readonly string[]).includes(value);
}

function protocolFailure(): never {
  throw new ApiError("Core returned a malformed decision contract.", 0, {
    kind: "protocol",
    detail: "malformed",
  });
}

function nonNegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && !Number.isNaN(value) && value >= 0;
}

export function parseDecisionBadge(value: unknown): DecisionBadge {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const badge = value as Record<string, unknown>;
  if (!isDecisionStatus(badge.status)) {
    protocolFailure();
  }
  if (!isDecisionPriority(badge.priority)) {
    protocolFailure();
  }
  if (typeof badge.headline_code !== "string" || !badge.headline_code) {
    protocolFailure();
  }
  if (!Array.isArray(badge.coverage_label_codes)) {
    protocolFailure();
  }
  const coverage_label_codes = badge.coverage_label_codes.map((code) => {
    if (typeof code !== "string") {
      protocolFailure();
    }
    return code as CoverageLabelCode;
  });
  return {
    status: badge.status,
    priority: badge.priority,
    headline_code: badge.headline_code,
    coverage_label_codes,
  };
}

export function parseDecisionCountSummary(value: unknown): DecisionCountSummary {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const summary = value as Record<string, unknown>;
  if (!nonNegativeInt(summary.subject_count)) {
    protocolFailure();
  }
  if (!isDecisionStatus(summary.overall_status)) {
    protocolFailure();
  }
  if (!isDecisionPriority(summary.highest_priority)) {
    protocolFailure();
  }
  if (!nonNegativeInt(summary.coverage_warning_count)) {
    protocolFailure();
  }
  if (!summary.status_counts || typeof summary.status_counts !== "object") {
    protocolFailure();
  }
  if (!summary.priority_counts || typeof summary.priority_counts !== "object") {
    protocolFailure();
  }

  const status_counts: Partial<Record<DecisionStatus, number>> = {};
  let statusTotal = 0;
  for (const [key, count] of Object.entries(summary.status_counts as Record<string, unknown>)) {
    if (!isDecisionStatus(key) || !nonNegativeInt(count)) {
      protocolFailure();
    }
    status_counts[key] = count;
    statusTotal += count;
  }

  const priority_counts: Partial<Record<DecisionPriority, number>> = {};
  let priorityTotal = 0;
  for (const [key, count] of Object.entries(summary.priority_counts as Record<string, unknown>)) {
    if (!isDecisionPriority(key) || !nonNegativeInt(count)) {
      protocolFailure();
    }
    priority_counts[key] = count;
    priorityTotal += count;
  }

  const subject_count = summary.subject_count;
  if (subject_count === 0) {
    if (statusTotal !== 0 || priorityTotal !== 0) {
      protocolFailure();
    }
  } else if (statusTotal !== subject_count || priorityTotal !== subject_count) {
    protocolFailure();
  }

  return {
    subject_count,
    overall_status: summary.overall_status,
    highest_priority: summary.highest_priority,
    status_counts,
    priority_counts,
    coverage_warning_count: summary.coverage_warning_count,
  };
}

export function parseDeviceSummary(value: unknown): DeviceSummary {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const device = value as DeviceSummary;
  parseDecisionBadge(device.decision);
  return device;
}

export function parseDeviceDetail(value: unknown): DeviceDetail {
  return parseDeviceSummary(value) as DeviceDetail;
}

export function parseNetworkSummary(value: unknown): NetworkSummary {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const network = value as NetworkSummary;
  parseDecisionBadge(network.decision);
  parseDecisionCountSummary(network.decision_summary);
  return network;
}

export function parseIncident(value: unknown): Incident {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const incident = value as Incident;
  for (const ref of incident.affected_devices ?? []) {
    parseDecisionBadge(ref.decision);
  }
  return incident;
}

export function validateDashboardPayload(value: unknown): DashboardPayload {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const payload = value as DashboardPayload;
  parseDecisionCountSummary(payload.decision_summary);
  for (const network of payload.networks ?? []) {
    parseNetworkSummary(network);
  }
  return payload;
}

export function validateDeviceSummaries(items: unknown): DeviceSummary[] {
  if (!Array.isArray(items)) {
    protocolFailure();
  }
  return items.map(parseDeviceSummary);
}

export function validateNetworkSummaries(items: unknown): NetworkSummary[] {
  if (!Array.isArray(items)) {
    protocolFailure();
  }
  return items.map(parseNetworkSummary);
}

export function validateIncidents(items: unknown): Incident[] {
  if (!Array.isArray(items)) {
    protocolFailure();
  }
  return items.map(parseIncident);
}

export function storedReportVersion(body: LegacyStoredReportBody): number {
  const raw = body.report_version;
  if (typeof raw === "number" && Number.isInteger(raw)) {
    return raw;
  }
  return 1;
}

export function isLegacyStoredReportBody(body: unknown): body is LegacyStoredReportBody {
  if (!body || typeof body !== "object") {
    return false;
  }
  return storedReportVersion(body as LegacyStoredReportBody) < 3;
}

export function validateReportDetailV3(value: unknown): ReportDetailV3 {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  const report = value as Record<string, unknown>;
  if (report.report_version !== 3) {
    protocolFailure();
  }
  parseDecisionCountSummary(report.decision_summary);
  for (const story of (report.device_stories as unknown[]) ?? []) {
    if (!story || typeof story !== "object") {
      protocolFailure();
    }
    const row = story as Record<string, unknown>;
    if (!isDecisionStatus(row.status) || !isDecisionPriority(row.priority)) {
      protocolFailure();
    }
  }
  const domain = report.domain_details;
  if (domain && typeof domain === "object") {
    for (const network of (domain as { networks?: unknown[] }).networks ?? []) {
      parseNetworkSummary(network);
    }
    for (const device of (domain as { devices?: unknown[] }).devices ?? []) {
      parseDeviceSummary(device);
    }
  }
  return value as ReportDetailV3;
}

export function parseStoredReport(value: unknown): ReportDetailV3 | LegacyStoredReportBody {
  if (!value || typeof value !== "object") {
    protocolFailure();
  }
  if (isLegacyStoredReportBody(value)) {
    return value;
  }
  return validateReportDetailV3(value);
}
