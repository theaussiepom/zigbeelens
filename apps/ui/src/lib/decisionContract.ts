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
  NetworkSummary,
  ReportDetailV3,
  ReportDomainDetailsV3,
  ReportFormat,
  ReportRedactionStatus,
  ReportScope,
} from "@zigbeelens/shared";
import { ApiError } from "@/lib/api";
import { COVERAGE_LABEL_CODES } from "@/viewModels/decisionCopy";

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

const DECISION_STATUS_ORDER: readonly DecisionStatus[] = [
  "review_first",
  "worth_reviewing",
  "improve_data_coverage",
  "watch",
  "changed",
  "informational",
  "no_notable_change",
  "data_unavailable",
];

/** Wire DecisionPriority values — not a user-facing label catalogue. */
export const DECISION_PRIORITIES: readonly DecisionPriority[] = [
  "none",
  "low",
  "medium",
  "high",
];

/**
 * Stable highest-priority resolution order (high → none).
 * DecisionPriority is ordering/contract metadata, not primary UI copy.
 */
export const DECISION_PRIORITY_ORDER: readonly DecisionPriority[] = [
  "high",
  "medium",
  "low",
  "none",
];

/** Rank for stable sorting/comparison; lower = higher urgency. */
export function decisionPriorityRank(priority: DecisionPriority): number {
  return DECISION_PRIORITY_ORDER.indexOf(priority);
}

const REPORT_SCOPES: readonly ReportScope[] = ["full", "incident", "network", "device"];
const REPORT_FORMATS: readonly ReportFormat[] = ["json", "yaml", "markdown"];
const REDACTION_PROFILES = ["standard", "strict", "public_safe"] as const;
const REDACTION_MODES = ["preserved", "labeled", "hashed", "redacted"] as const;

const REPORT_DETAIL_V3_KEYS = [
  "id",
  "product",
  "report_version",
  "generated_at",
  "version",
  "scope",
  "format",
  "redaction",
  "config_summary",
  "decision_summary",
  "investigation_priorities",
  "device_stories",
  "data_coverage_warnings",
  "incidents",
  "collector_status",
  "domain_details",
  "events_or_timeline",
  "limitations",
  "raw_counts",
  "markdown_summary",
] as const;

const DOMAIN_DETAILS_KEYS = [
  "networks",
  "devices",
  "device_details",
  "router_risks",
  "topology_snapshot_count",
] as const;

const DEVICE_STORY_KEYS = [
  "network_id",
  "ieee_address",
  "friendly_name",
  "subject_type",
  "subject_id",
  "status",
  "priority",
  "headline_code",
  "reasons",
  "evidence",
  "limitations",
  "suggested_checks",
  "coverage",
  "related_unresolved_incident_ids",
  "timeline",
] as const;

const INCIDENT_STATUSES = ["open", "watching", "resolved"] as const;
const SEVERITIES = ["healthy", "watch", "incident", "critical"] as const;
const INCIDENT_SCOPES = [
  "device",
  "router_candidate",
  "mesh_segment",
  "network",
  "multi_network",
  "unknown",
] as const;
const CONFIDENCES = ["low", "medium", "high"] as const;

const INCIDENT_REQUIRED_KEYS = [
  "id",
  "type",
  "status",
  "severity",
  "scope",
  "confidence",
  "title",
  "summary",
  "interpretation",
  "network_ids",
  "affected_device_count",
  "affected_devices",
  "opened_at",
  "updated_at",
  "resolved_at",
  "evidence",
  "counter_evidence",
  "limitations",
  "timeline",
  "conclusion",
] as const;

export function isDecisionStatus(value: unknown): value is DecisionStatus {
  return typeof value === "string" && (DECISION_STATUSES as readonly string[]).includes(value);
}

export function isDecisionPriority(value: unknown): value is DecisionPriority {
  return typeof value === "string" && (DECISION_PRIORITIES as readonly string[]).includes(value);
}

export function isCoverageLabelCode(value: unknown): value is CoverageLabelCode {
  return typeof value === "string" && (COVERAGE_LABEL_CODES as readonly string[]).includes(value);
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

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function exactKeySet(value: Record<string, unknown>, keys: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length) {
    protocolFailure();
  }
  for (let i = 0; i < expected.length; i += 1) {
    if (actual[i] !== expected[i]) {
      protocolFailure();
    }
  }
}

export function parseDecisionBadge(value: unknown): DecisionBadge {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  if (!isDecisionStatus(value.status)) {
    protocolFailure();
  }
  if (!isDecisionPriority(value.priority)) {
    protocolFailure();
  }
  if (typeof value.headline_code !== "string" || !value.headline_code) {
    protocolFailure();
  }
  if (!Array.isArray(value.coverage_label_codes)) {
    protocolFailure();
  }
  const coverage_label_codes = value.coverage_label_codes.map((code) => {
    if (!isCoverageLabelCode(code)) {
      protocolFailure();
    }
    return code;
  });
  return {
    status: value.status,
    priority: value.priority,
    headline_code: value.headline_code,
    coverage_label_codes,
  };
}

export function parseDecisionCountSummary(value: unknown): DecisionCountSummary {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  if (!nonNegativeInt(value.subject_count)) {
    protocolFailure();
  }
  if (!isDecisionStatus(value.overall_status)) {
    protocolFailure();
  }
  if (!isDecisionPriority(value.highest_priority)) {
    protocolFailure();
  }
  if (!nonNegativeInt(value.coverage_warning_count)) {
    protocolFailure();
  }
  if (!isPlainObject(value.status_counts) || !isPlainObject(value.priority_counts)) {
    protocolFailure();
  }

  const status_counts: Partial<Record<DecisionStatus, number>> = {};
  let statusTotal = 0;
  for (const [key, count] of Object.entries(value.status_counts)) {
    if (!isDecisionStatus(key) || !nonNegativeInt(count)) {
      protocolFailure();
    }
    status_counts[key] = count;
    statusTotal += count;
  }

  const priority_counts: Partial<Record<DecisionPriority, number>> = {};
  let priorityTotal = 0;
  for (const [key, count] of Object.entries(value.priority_counts)) {
    if (!isDecisionPriority(key) || !nonNegativeInt(count)) {
      protocolFailure();
    }
    priority_counts[key] = count;
    priorityTotal += count;
  }

  const subject_count = value.subject_count;
  if (subject_count === 0) {
    if (statusTotal !== 0 || priorityTotal !== 0) {
      protocolFailure();
    }
    if (value.overall_status !== "data_unavailable" || value.highest_priority !== "none") {
      protocolFailure();
    }
  } else {
    if (statusTotal !== subject_count || priorityTotal !== subject_count) {
      protocolFailure();
    }
    let expectedOverall: DecisionStatus = "data_unavailable";
    for (const status of DECISION_STATUS_ORDER) {
      if ((status_counts[status] ?? 0) > 0) {
        expectedOverall = status;
        break;
      }
    }
    if (value.overall_status !== expectedOverall) {
      protocolFailure();
    }
    let expectedPriority: DecisionPriority = "none";
    for (const priority of DECISION_PRIORITY_ORDER) {
      if ((priority_counts[priority] ?? 0) > 0) {
        expectedPriority = priority;
        break;
      }
    }
    if (value.highest_priority !== expectedPriority) {
      protocolFailure();
    }
  }

  return {
    subject_count,
    overall_status: value.overall_status,
    highest_priority: value.highest_priority,
    status_counts,
    priority_counts,
    coverage_warning_count: value.coverage_warning_count,
  };
}

export function parseDeviceSummary(value: unknown): DeviceSummary {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  parseDecisionBadge(value.decision);
  return value as unknown as DeviceSummary;
}

export function parseDeviceDetail(value: unknown): DeviceDetail {
  return parseDeviceSummary(value) as DeviceDetail;
}

export function parseNetworkSummary(value: unknown): NetworkSummary {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  parseDecisionBadge(value.decision);
  parseDecisionCountSummary(value.decision_summary);
  return value as unknown as NetworkSummary;
}

function requireNonEmptyString(value: unknown): string {
  if (typeof value !== "string" || !value) {
    protocolFailure();
  }
  return value;
}

function parseCodedItem(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.code);
  if (value.params !== undefined && !isPlainObject(value.params)) {
    protocolFailure();
  }
}

/** Device-story evidence reference (source pointer), not Incident EvidenceItem. */
function parseEvidenceReference(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.source);
  if (value.id !== undefined && value.id !== null && typeof value.id !== "string") {
    protocolFailure();
  }
  if (
    value.captured_at !== undefined &&
    value.captured_at !== null &&
    typeof value.captured_at !== "string"
  ) {
    protocolFailure();
  }
}

function optionalStringOrNull(value: unknown): void {
  if (value !== undefined && value !== null && typeof value !== "string") {
    protocolFailure();
  }
}

/** Recorded Incident / conclusion EvidenceItem (id/kind/summary). */
function parseIncidentEvidenceItem(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.id);
  requireNonEmptyString(value.kind);
  if (typeof value.summary !== "string") {
    protocolFailure();
  }
  optionalStringOrNull(value.detail);
  optionalStringOrNull(value.timestamp);
  optionalStringOrNull(value.network_id);
  optionalStringOrNull(value.ieee_address);
}

function parseCoverageItem(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  if (!isCoverageLabelCode(value.label_code)) {
    protocolFailure();
  }
  if (value.params !== undefined && !isPlainObject(value.params)) {
    protocolFailure();
  }
}

function parseStoryTimelineItem(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.code);
  if (value.params !== undefined && !isPlainObject(value.params)) {
    protocolFailure();
  }
  if (
    value.occurred_at !== undefined &&
    value.occurred_at !== null &&
    typeof value.occurred_at !== "string"
  ) {
    protocolFailure();
  }
}

export function parseDeviceStory(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  exactKeySet(value, DEVICE_STORY_KEYS);
  for (const key of [
    "network_id",
    "ieee_address",
    "friendly_name",
    "subject_id",
    "headline_code",
  ] as const) {
    requireNonEmptyString(value[key]);
  }
  if (value.subject_type !== "device") {
    protocolFailure();
  }
  if (!isDecisionStatus(value.status) || !isDecisionPriority(value.priority)) {
    protocolFailure();
  }
  for (const key of [
    "reasons",
    "evidence",
    "limitations",
    "suggested_checks",
    "coverage",
    "related_unresolved_incident_ids",
    "timeline",
  ] as const) {
    if (!Array.isArray(value[key])) {
      protocolFailure();
    }
  }
  for (const item of value.reasons as unknown[]) {
    parseCodedItem(item);
  }
  for (const item of value.evidence as unknown[]) {
    parseEvidenceReference(item);
  }
  for (const item of value.limitations as unknown[]) {
    parseCodedItem(item);
  }
  for (const item of value.suggested_checks as unknown[]) {
    parseCodedItem(item);
  }
  for (const item of value.coverage as unknown[]) {
    parseCoverageItem(item);
  }
  for (const id of value.related_unresolved_incident_ids as unknown[]) {
    if (typeof id !== "string") {
      protocolFailure();
    }
  }
  for (const item of value.timeline as unknown[]) {
    parseStoryTimelineItem(item);
  }
}

function parseLimitationItem(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.id);
  if (typeof value.summary !== "string") {
    protocolFailure();
  }
  optionalStringOrNull(value.detail);
}

function parseTimelineEvent(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.id);
  requireNonEmptyString(value.timestamp);
  requireNonEmptyString(value.kind);
  if (
    typeof value.severity !== "string" ||
    !(SEVERITIES as readonly string[]).includes(value.severity)
  ) {
    protocolFailure();
  }
  requireNonEmptyString(value.title);
  requireNonEmptyString(value.summary);
  optionalStringOrNull(value.network_id);
  optionalStringOrNull(value.ieee_address);
  optionalStringOrNull(value.friendly_name);
  optionalStringOrNull(value.incident_id);
}

function parseDiagnosticConclusion(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  if (typeof value.classification !== "string") {
    protocolFailure();
  }
  if (
    typeof value.severity !== "string" ||
    !(SEVERITIES as readonly string[]).includes(value.severity)
  ) {
    protocolFailure();
  }
  if (
    typeof value.scope !== "string" ||
    !(INCIDENT_SCOPES as readonly string[]).includes(value.scope)
  ) {
    protocolFailure();
  }
  if (
    typeof value.confidence !== "string" ||
    !(CONFIDENCES as readonly string[]).includes(value.confidence)
  ) {
    protocolFailure();
  }
  if (typeof value.summary !== "string") {
    protocolFailure();
  }
  if (!Array.isArray(value.evidence) || !Array.isArray(value.counter_evidence)) {
    protocolFailure();
  }
  if (!Array.isArray(value.limitations)) {
    protocolFailure();
  }
  for (const item of value.evidence) {
    parseIncidentEvidenceItem(item);
  }
  for (const item of value.counter_evidence) {
    parseIncidentEvidenceItem(item);
  }
  for (const item of value.limitations) {
    parseLimitationItem(item);
  }
}

export function parseIncident(value: unknown): Incident {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  for (const key of INCIDENT_REQUIRED_KEYS) {
    if (!(key in value)) {
      protocolFailure();
    }
  }

  requireNonEmptyString(value.id);
  requireNonEmptyString(value.type);
  if (
    typeof value.status !== "string" ||
    !(INCIDENT_STATUSES as readonly string[]).includes(value.status)
  ) {
    protocolFailure();
  }
  if (
    typeof value.severity !== "string" ||
    !(SEVERITIES as readonly string[]).includes(value.severity)
  ) {
    protocolFailure();
  }
  if (
    typeof value.scope !== "string" ||
    !(INCIDENT_SCOPES as readonly string[]).includes(value.scope)
  ) {
    protocolFailure();
  }
  if (
    typeof value.confidence !== "string" ||
    !(CONFIDENCES as readonly string[]).includes(value.confidence)
  ) {
    protocolFailure();
  }
  requireNonEmptyString(value.title);
  if (typeof value.summary !== "string" || !value.summary) {
    protocolFailure();
  }
  if (typeof value.interpretation !== "string") {
    protocolFailure();
  }
  if (!Array.isArray(value.network_ids) || !value.network_ids.every((id) => typeof id === "string")) {
    protocolFailure();
  }
  if (!nonNegativeInt(value.affected_device_count)) {
    protocolFailure();
  }
  requireNonEmptyString(value.opened_at);
  requireNonEmptyString(value.updated_at);
  if (value.resolved_at !== null && typeof value.resolved_at !== "string") {
    protocolFailure();
  }
  if (!Array.isArray(value.affected_devices)) {
    protocolFailure();
  }
  if (value.affected_device_count !== value.affected_devices.length) {
    protocolFailure();
  }
  for (const ref of value.affected_devices) {
    if (!isPlainObject(ref)) {
      protocolFailure();
    }
    requireNonEmptyString(ref.network_id);
    requireNonEmptyString(ref.ieee_address);
    if (typeof ref.friendly_name !== "string") {
      protocolFailure();
    }
    parseDecisionBadge(ref.decision);
  }
  if (!Array.isArray(value.evidence) || !Array.isArray(value.counter_evidence)) {
    protocolFailure();
  }
  if (!Array.isArray(value.limitations) || !Array.isArray(value.timeline)) {
    protocolFailure();
  }
  for (const item of value.evidence) {
    parseIncidentEvidenceItem(item);
  }
  for (const item of value.counter_evidence) {
    parseIncidentEvidenceItem(item);
  }
  for (const item of value.limitations) {
    parseLimitationItem(item);
  }
  for (const item of value.timeline) {
    parseTimelineEvent(item);
  }
  parseDiagnosticConclusion(value.conclusion);
  return value as unknown as Incident;
}

function parseInvestigationPriority(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  for (const key of ["id", "network_id", "priority", "action_group", "title", "summary"] as const) {
    requireNonEmptyString(value[key]);
  }
}

function parseDataCoverageWarning(value: unknown): void {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  requireNonEmptyString(value.id);
  requireNonEmptyString(value.network_id);
  requireNonEmptyString(value.label_code);
  if (!isPlainObject(value.params)) {
    protocolFailure();
  }
}

function parseLimitation(value: unknown): void {
  parseLimitationItem(value);
}

export function validateDashboardPayload(value: unknown): DashboardPayload {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  parseDecisionCountSummary(value.decision_summary);
  if (!Array.isArray(value.networks)) {
    protocolFailure();
  }
  for (const network of value.networks) {
    parseNetworkSummary(network);
  }
  return value as unknown as DashboardPayload;
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

function parseRedaction(value: unknown): ReportRedactionStatus {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  if (typeof value.applied !== "boolean") {
    protocolFailure();
  }
  if (
    typeof value.profile !== "string" ||
    !(REDACTION_PROFILES as readonly string[]).includes(value.profile)
  ) {
    protocolFailure();
  }
  for (const key of [
    "mqtt_credentials",
    "secrets",
    "hostnames",
    "ip_addresses",
    "ieee_addresses_hashed",
  ] as const) {
    if (typeof value[key] !== "boolean") {
      protocolFailure();
    }
  }
  for (const key of ["friendly_names", "network_names"] as const) {
    if (
      typeof value[key] !== "string" ||
      !(REDACTION_MODES as readonly string[]).includes(value[key] as string)
    ) {
      protocolFailure();
    }
  }
  return value as unknown as ReportRedactionStatus;
}

function parseDomainDetails(value: unknown): ReportDomainDetailsV3 {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  exactKeySet(value, DOMAIN_DETAILS_KEYS);
  if (!Array.isArray(value.networks) || !Array.isArray(value.devices)) {
    protocolFailure();
  }
  if (!Array.isArray(value.device_details) || !Array.isArray(value.router_risks)) {
    protocolFailure();
  }
  if (!nonNegativeInt(value.topology_snapshot_count)) {
    protocolFailure();
  }
  for (const network of value.networks) {
    parseNetworkSummary(network);
  }
  for (const device of value.devices) {
    parseDeviceSummary(device);
  }
  for (const detail of value.device_details) {
    parseDeviceDetail(detail);
  }
  return value as unknown as ReportDomainDetailsV3;
}

export function validateReportDetailV3(value: unknown): ReportDetailV3 {
  if (!isPlainObject(value)) {
    protocolFailure();
  }
  exactKeySet(value, REPORT_DETAIL_V3_KEYS);

  requireNonEmptyString(value.id);
  if (value.product !== "ZigbeeLens") {
    protocolFailure();
  }
  if (typeof value.report_version !== "number" || !Number.isInteger(value.report_version)) {
    protocolFailure();
  }
  if (value.report_version !== 3) {
    protocolFailure();
  }
  requireNonEmptyString(value.generated_at);
  if (typeof value.version !== "string") {
    protocolFailure();
  }
  if (
    typeof value.scope !== "string" ||
    !(REPORT_SCOPES as readonly string[]).includes(value.scope)
  ) {
    protocolFailure();
  }
  if (
    typeof value.format !== "string" ||
    !(REPORT_FORMATS as readonly string[]).includes(value.format)
  ) {
    protocolFailure();
  }
  parseRedaction(value.redaction);
  if (!isPlainObject(value.config_summary)) {
    protocolFailure();
  }
  parseDecisionCountSummary(value.decision_summary);

  if (!Array.isArray(value.investigation_priorities)) {
    protocolFailure();
  }
  for (const item of value.investigation_priorities) {
    parseInvestigationPriority(item);
  }
  if (!Array.isArray(value.device_stories)) {
    protocolFailure();
  }
  for (const story of value.device_stories) {
    parseDeviceStory(story);
  }
  if (!Array.isArray(value.data_coverage_warnings)) {
    protocolFailure();
  }
  for (const warning of value.data_coverage_warnings) {
    parseDataCoverageWarning(warning);
  }
  if (!Array.isArray(value.incidents)) {
    protocolFailure();
  }
  for (const incident of value.incidents) {
    parseIncident(incident);
  }
  if (!isPlainObject(value.collector_status)) {
    protocolFailure();
  }
  parseDomainDetails(value.domain_details);
  if (!Array.isArray(value.events_or_timeline)) {
    protocolFailure();
  }
  for (const event of value.events_or_timeline) {
    parseTimelineEvent(event);
  }
  if (!Array.isArray(value.limitations)) {
    protocolFailure();
  }
  for (const limitation of value.limitations) {
    parseLimitation(limitation);
  }
  if (!isPlainObject(value.raw_counts)) {
    protocolFailure();
  }
  for (const count of Object.values(value.raw_counts)) {
    if (!nonNegativeInt(count)) {
      protocolFailure();
    }
  }
  if (typeof value.markdown_summary !== "string") {
    protocolFailure();
  }
  return value as unknown as ReportDetailV3;
}

export function parseStoredReport(value: unknown): ReportDetailV3 {
  return validateReportDetailV3(value);
}
