/**
 * Behavioral unknown-not-zero: constructed unknowns through production boundaries.
 */
import { describe, expect, it } from "vitest";
import type { DeviceSummary, ReportDetailV3, ReportDeviceStory } from "@zigbeelens/shared";
import { parseDeviceSummary } from "@/lib/decisionContract";
import { coverageLabel } from "@/viewModels/decisionCopy";
import { buildDeviceRowViewModel } from "@/viewModels/devices/deviceRowViewModel";
import { buildReportDecisionViewModel } from "@/viewModels/reports/reportDecisionViewModel";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import type { DeviceStoryDto } from "@/types/devices";

const FALSE_MEASURED = [/^0$/, /^0%$/, /\bhealthy\b/i, /\bcomplete\b/i, /\bno issue\b/i, /\bno links\b/i];

function looksLikeFalseZero(text: string): boolean {
  return FALSE_MEASURED.some((pattern) => pattern.test(text.trim()));
}

function makeDevice(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    device_type: "EndDevice",
    power_source: "Battery",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    manufacturer: null,
    model: null,
    battery: null,
    linkquality: null,
    last_seen: null,
    ha_area: null,
    decision: {
      status: "data_unavailable",
      priority: "none",
      headline_code: "device_data_unavailable",
      coverage_label_codes: ["last_seen_unknown", "availability_tracking_off"],
    },
    ...overrides,
  };
}

function makeStory(overrides: Partial<DeviceStoryDto> = {}): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: "0xa1",
    status: "data_unavailable",
    priority: "none",
    headline_code: "device_data_unavailable",
    reasons: [],
    evidence: [],
    limitations: [],
    suggested_checks: [],
    coverage: [
      {
        dimension: "last_seen",
        state: "unknown",
        label_code: "last_seen_unknown",
        params: {},
      },
      {
        dimension: "availability",
        state: "off",
        label_code: "availability_tracking_off",
        params: {},
      },
      {
        dimension: "last_payload",
        state: "unknown",
        label_code: "last_payload_unknown",
        params: {},
      },
      {
        dimension: "historical_snapshots",
        state: "sparse",
        label_code: "topology_history_sparse",
        params: { observed: 0, window: 3 },
      },
    ],
    related_unresolved_incident_ids: [],
    timeline: [],
    ...overrides,
  };
}

function makeReportStory(overrides: Partial<ReportDeviceStory> = {}): ReportDeviceStory {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    subject_type: "device",
    subject_id: "0xa1",
    status: "data_unavailable",
    priority: "none",
    headline_code: "device_data_unavailable",
    reasons: [],
    evidence: [],
    limitations: [],
    suggested_checks: [],
    coverage: [
      {
        dimension: "last_seen",
        state: "unknown",
        label_code: "last_seen_unknown",
        params: {},
      },
      {
        dimension: "route_hints",
        state: "unavailable",
        label_code: "route_hints_unavailable",
        params: {},
      },
    ],
    related_unresolved_incident_ids: [],
    timeline: [],
    ...overrides,
  };
}

function makeReport(overrides: Partial<ReportDetailV3> = {}): ReportDetailV3 {
  return {
    id: "report-unknown",
    product: "ZigbeeLens",
    report_version: 3,
    generated_at: "2026-06-14T15:30:00+00:00",
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
    decision_summary: {
      subject_count: 1,
      overall_status: "data_unavailable",
      highest_priority: "none",
      status_counts: { data_unavailable: 1 },
      priority_counts: { none: 1 },
      coverage_warning_count: 1,
    },
    config_summary: { mode: "mock" },
    collector_status: {},
    investigation_priorities: [],
    device_stories: [makeReportStory()],
    data_coverage_warnings: [
      {
        network_id: "home",
        dimension: "route_hints",
        state: "unavailable",
        label_code: "route_hints_unavailable",
        params: {},
      },
    ],
    domain_details: {
      networks: [{ id: "home", name: "Home", base_topic: "zigbee2mqtt/home" }],
      devices: [
        {
          network_id: "home",
          ieee_address: "0xa1",
          friendly_name: "Kitchen Plug",
          battery: null,
          linkquality: null,
          last_seen: null,
        },
      ],
      device_details: [],
      router_risks: [],
      topology_snapshot_count: 0,
    },
    incidents: [],
    events_or_timeline: [],
    limitations: [],
    raw_counts: {
      events_included: 0,
      devices_included: 1,
      incidents_included: 0,
    },
    markdown_summary: "# ZigbeeLens Evidence Report",
    ...overrides,
  } as ReportDetailV3;
}

describe("unknown never becomes zero/healthy (UI behavioral)", () => {
  it("null battery/LQI/last-seen survive parser and project to em-dash forms", () => {
    const wire = {
      network_id: "home",
      ieee_address: "0xa1",
      friendly_name: "Kitchen Plug",
      device_type: "EndDevice",
      power_source: "Battery",
      availability: "online",
      interview_state: "successful",
      incident_affected: false,
      battery: null,
      linkquality: null,
      last_seen: null,
      ha_area: null,
      decision: {
        status: "data_unavailable",
        priority: "none",
        headline_code: "device_data_unavailable",
        coverage_label_codes: [],
      },
    };
    const parsed = parseDeviceSummary(wire);
    expect(parsed.battery).toBeNull();
    expect(parsed.linkquality).toBeNull();
    expect(parsed.last_seen).toBeNull();

    const row = buildDeviceRowViewModel(makeDevice());
    expect(row.batterySummary).toBe("Battery —");
    expect(row.lqiSummary).toBe("LQI —");
    expect(row.lastSeenLabel).toBe("—");
    for (const text of [row.batterySummary, row.lqiSummary, row.lastSeenLabel]) {
      expect(looksLikeFalseZero(text)).toBe(false);
    }
  });

  it("coverage unknown/off/sparse labels stay non-measured in story and report ViewModels", () => {
    const storyVm = buildDeviceStoryViewModel(makeStory());
    expect(storyVm.coverageItems.length).toBeGreaterThanOrEqual(3);
    for (const item of storyVm.coverageItems) {
      expect(looksLikeFalseZero(item.label)).toBe(false);
      expect(item.label.toLowerCase()).not.toMatch(/^(0|0%|healthy|complete|no issue)$/);
    }
    expect(looksLikeFalseZero(storyVm.headline)).toBe(false);

    const reportVm = buildReportDecisionViewModel(makeReport());
    expect(reportVm.deviceStories).toHaveLength(1);
    expect(reportVm.networkCoverage).toHaveLength(1);
    for (const item of reportVm.deviceStories[0]!.story.coverageItems) {
      expect(looksLikeFalseZero(item.label)).toBe(false);
    }
    expect(looksLikeFalseZero(reportVm.networkCoverage[0]!.title)).toBe(false);
  });

  it("coverage label presenter maps unknown/off/building codes without inventing zero", () => {
    const codes = [
      "last_seen_unknown",
      "last_payload_unknown",
      "availability_status_unknown",
      "availability_tracking_off",
      "availability_history_building",
      "route_hints_unavailable",
      "topology_history_not_observed",
      "topology_history_sparse",
    ] as const;
    expect(codes.length).toBeGreaterThan(0);
    for (const code of codes) {
      const label = coverageLabel(code, code === "topology_history_sparse" ? { observed: 0, window: 3 } : {});
      expect(label.trim().length).toBeGreaterThan(0);
      expect(looksLikeFalseZero(label)).toBe(false);
    }
  });
});
