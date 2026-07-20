import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import {
  classifyStoredReportVersion,
  isCoverageLabelCode,
  isDecisionPriority,
  isDecisionStatus,
  parseDecisionBadge,
  parseDecisionCountSummary,
  parseDeviceStory,
  parseDeviceSummary,
  parseIncident,
  parseStoredReport,
  validateDashboardPayload,
  validateReportDetailV3,
} from "@/lib/decisionContract";

const EMPTY_STORY_COLLECTIONS = {
  reasons: [] as unknown[],
  evidence: [] as unknown[],
  limitations: [] as unknown[],
  suggested_checks: [] as unknown[],
  coverage: [] as unknown[],
  related_unresolved_incident_ids: [] as string[],
  timeline: [] as unknown[],
};

function validDeviceStory(overrides: Record<string, unknown> = {}) {
  return {
    network_id: "home",
    ieee_address: "0x1",
    friendly_name: "Sensor",
    subject_type: "device",
    subject_id: "home:0x1",
    status: "watch",
    priority: "low",
    headline_code: "device_watch",
    ...EMPTY_STORY_COLLECTIONS,
    ...overrides,
  };
}

function validIncident(overrides: Record<string, unknown> = {}) {
  return {
    id: "inc-1",
    status: "open",
    title: "Incident",
    summary: "Summary",
    network_ids: ["home"],
    affected_device_count: 1,
    opened_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    affected_devices: [
      {
        network_id: "home",
        ieee_address: "0x1",
        friendly_name: "Sensor",
        decision: {
          status: "watch",
          priority: "low",
          headline_code: "device_watch",
          coverage_label_codes: [],
        },
      },
    ],
    ...overrides,
  };
}

describe("decisionContract", () => {
  it("accepts a valid decision badge", () => {
    expect(
      parseDecisionBadge({
        status: "review_first",
        priority: "high",
        headline_code: "current_issue_present",
        coverage_label_codes: ["availability_tracking_off"],
      }),
    ).toEqual({
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: ["availability_tracking_off"],
    });
  });

  it("rejects a missing decision badge as protocol failure", () => {
    expect(() => parseDecisionBadge(null)).toThrow(ApiError);
    try {
      parseDecisionBadge(null);
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).kind).toBe("protocol");
    }
  });

  it("rejects malformed decision summary count maps", () => {
    expect(() =>
      parseDecisionCountSummary({
        subject_count: 2,
        overall_status: "watch",
        highest_priority: "low",
        status_counts: { watch: 1 },
        priority_counts: { low: 2 },
        coverage_warning_count: 0,
      }),
    ).toThrow(ApiError);
  });

  it("rejects devices missing required decision fields", () => {
    expect(() =>
      parseDeviceSummary({
        network_id: "home",
        ieee_address: "0x1",
        friendly_name: "Sensor",
        device_type: "EndDevice",
        power_source: "Battery",
        availability: "online",
        interview_state: "successful",
        incident_affected: false,
      }),
    ).toThrow(ApiError);
  });

  it("validates dashboard decision summaries and network badges", () => {
    const payload = validateDashboardPayload({
      generated_at: "2026-07-06T12:00:00+00:00",
      active_incident_count: 0,
      watching_incident_count: 0,
      network_count: 1,
      device_count: 0,
      unavailable_device_count: 0,
      networks: [
        {
          id: "home",
          name: "Home",
          base_topic: "zigbee2mqtt",
          bridge_state: "online",
          device_count: 0,
          router_count: 0,
          end_device_count: 0,
          unavailable_count: 0,
          active_incident_severity: null,
          active_incident_count: 0,
          recent_bridge_warnings: 0,
          recent_bridge_errors: 0,
          decision: {
            status: "data_unavailable",
            priority: "none",
            headline_code: "network_data_unavailable",
            coverage_label_codes: [],
          },
          decision_summary: {
            subject_count: 0,
            overall_status: "data_unavailable",
            highest_priority: "none",
            status_counts: {},
            priority_counts: {},
            coverage_warning_count: 0,
          },
        },
      ],
      router_risks: [],
      recent_timeline: [],
      decision_summary: {
        subject_count: 0,
        overall_status: "data_unavailable",
        highest_priority: "none",
        status_counts: {},
        priority_counts: {},
        coverage_warning_count: 0,
      },
      shared_availability_events: [],
      model_patterns: [],
      investigation_priorities: [],
      data_coverage_warnings: [],
    });

    expect(payload.networks[0].decision.status).toBe("data_unavailable");
  });

  it("rejects unknown coverage label codes", () => {
    expect(() =>
      parseDecisionBadge({
        status: "watch",
        priority: "low",
        headline_code: "device_watch",
        coverage_label_codes: ["future_backend_label"],
      }),
    ).toThrow(ApiError);
  });

  it("rejects empty summaries that are not data_unavailable", () => {
    expect(() =>
      parseDecisionCountSummary({
        subject_count: 0,
        overall_status: "no_notable_change",
        highest_priority: "none",
        status_counts: {},
        priority_counts: {},
        coverage_warning_count: 0,
      }),
    ).toThrow(ApiError);
  });

  it("rejects string or non-integer float counts", () => {
    expect(() =>
      parseDecisionCountSummary({
        subject_count: "1",
        overall_status: "watch",
        highest_priority: "low",
        status_counts: { watch: 1 },
        priority_counts: { low: 1 },
        coverage_warning_count: 0,
      }),
    ).toThrow(ApiError);
    expect(() =>
      parseDecisionCountSummary({
        subject_count: 1.5,
        overall_status: "watch",
        highest_priority: "low",
        status_counts: { watch: 1 },
        priority_counts: { low: 1 },
        coverage_warning_count: 0,
      }),
    ).toThrow(ApiError);
  });

  it("classifies stored report versions exactly", () => {
    expect(classifyStoredReportVersion({}).kind).toBe("legacy");
    expect(classifyStoredReportVersion({ report_version: 1 }).kind).toBe("legacy");
    expect(classifyStoredReportVersion({ report_version: "2" }).kind).toBe("legacy");
    expect(classifyStoredReportVersion({ report_version: 3 }).kind).toBe("current");
    expect(classifyStoredReportVersion({ report_version: "3" }).kind).toBe("protocol_error");
    expect(classifyStoredReportVersion({ report_version: 3.5 }).kind).toBe("protocol_error");
    expect(classifyStoredReportVersion({ report_version: true }).kind).toBe("protocol_error");
    expect(classifyStoredReportVersion({ report_version: 4 }).kind).toBe("protocol_error");
    expect(() => parseStoredReport({ report_version: "3" })).toThrow(ApiError);
  });

  it("requires the exact ReportDetailV3 top-level key set", () => {
    const base = {
      id: "r1",
      product: "ZigbeeLens",
      report_version: 3,
      generated_at: "2026-01-01T00:00:00+00:00",
      version: "0.1.0",
      scope: "full",
      format: "json",
      redaction: {
        applied: true,
        profile: "standard",
        mqtt_credentials: true,
        secrets: true,
        hostnames: false,
        ip_addresses: false,
        ieee_addresses_hashed: false,
        friendly_names: "preserved",
        network_names: "preserved",
      },
      config_summary: {},
      decision_summary: {
        subject_count: 0,
        overall_status: "data_unavailable",
        highest_priority: "none",
        status_counts: {},
        priority_counts: {},
        coverage_warning_count: 0,
      },
      investigation_priorities: [],
      device_stories: [],
      data_coverage_warnings: [],
      incidents: [],
      collector_status: {},
      domain_details: {
        networks: [],
        devices: [],
        device_details: [],
        router_risks: [],
        topology_snapshot_count: 0,
      },
      events_or_timeline: [],
      limitations: [],
      raw_counts: {},
      markdown_summary: "",
    };
    expect(validateReportDetailV3(base).id).toBe("r1");

    const { domain_details: _dd, ...missingDomain } = base;
    expect(() => validateReportDetailV3(missingDomain)).toThrow(ApiError);
    const { redaction: _r, ...missingRedaction } = base;
    expect(() => validateReportDetailV3(missingRedaction)).toThrow(ApiError);
    const { incidents: _i, ...missingIncidents } = base;
    expect(() => validateReportDetailV3(missingIncidents)).toThrow(ApiError);
    expect(() =>
      validateReportDetailV3({ ...base, health_snapshot: { overall: "ok" } }),
    ).toThrow(ApiError);
    expect(() =>
      validateReportDetailV3({ ...base, executive_summary: "legacy" }),
    ).toThrow(ApiError);
    expect(() => validateReportDetailV3({ ...base, unknown_field: 1 })).toThrow(ApiError);
    expect(() => validateReportDetailV3({ ...base, scope: "all" })).toThrow(ApiError);
    expect(() => validateReportDetailV3({ ...base, format: "xml" })).toThrow(ApiError);
    expect(() =>
      validateReportDetailV3({
        ...base,
        device_stories: [
          {
            network_id: "home",
            ieee_address: "0x1",
            friendly_name: "s",
            subject_type: "device",
            subject_id: "home:0x1",
            status: "not_a_status",
            priority: "low",
            headline_code: "x",
            reasons: [],
            evidence: [],
            limitations: [],
            suggested_checks: [],
            coverage: [],
            related_unresolved_incident_ids: [],
            timeline: [],
          },
        ],
      }),
    ).toThrow(ApiError);
  });

  it.each([
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
  ] as const)("rejects device stories missing required key %s", (key) => {
    const story = validDeviceStory();
    delete (story as Record<string, unknown>)[key];
    expect(() => parseDeviceStory(story)).toThrow(ApiError);
  });

  it("rejects malformed device story collections and subject_type", () => {
    expect(() => parseDeviceStory(validDeviceStory({ timeline: undefined }))).toThrow(ApiError);
    expect(() => parseDeviceStory(validDeviceStory({ timeline: "nope" }))).toThrow(ApiError);
    expect(() => parseDeviceStory(validDeviceStory({ reasons: undefined }))).toThrow(ApiError);
    expect(() =>
      parseDeviceStory(
        validDeviceStory({
          coverage: [{ label_code: "future_backend_label", params: {} }],
        }),
      ),
    ).toThrow(ApiError);
    expect(() =>
      parseDeviceStory(validDeviceStory({ related_unresolved_incident_ids: [1] })),
    ).toThrow(ApiError);
    expect(() => parseDeviceStory(validDeviceStory({ subject_type: "network" }))).toThrow(
      ApiError,
    );
    expect(() => parseDeviceStory(validDeviceStory())).not.toThrow();
  });

  it("requires affected_devices and exact incident identity fields", () => {
    expect(() => parseIncident(validIncident())).not.toThrow();
    const { affected_devices: _a, ...missingAffected } = validIncident();
    expect(() => parseIncident(missingAffected)).toThrow(ApiError);
    expect(() => parseIncident(validIncident({ affected_devices: "nope" }))).toThrow(ApiError);
    expect(() =>
      parseIncident(
        validIncident({
          affected_device_count: 0,
        }),
      ),
    ).toThrow(ApiError);
    expect(() =>
      parseIncident(
        validIncident({
          affected_devices: [
            {
              network_id: "home",
              ieee_address: "0x1",
              friendly_name: "Sensor",
            },
          ],
        }),
      ),
    ).toThrow(ApiError);
  });

  it("exports closed canonical unions", () => {
    expect(isDecisionStatus("review_first")).toBe(true);
    expect(isDecisionStatus("future_status_v2")).toBe(false);
    expect(isDecisionPriority("high")).toBe(true);
    expect(isDecisionPriority("urgent")).toBe(false);
    expect(isCoverageLabelCode("availability_tracking_off")).toBe(true);
    expect(isCoverageLabelCode("future_backend_label")).toBe(false);
  });
});
