/**
 * Behavioral unknown-not-zero: constructed unknowns through production boundaries.
 */
import { describe, expect, it } from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import { parseDeviceSummary, validateReportDetailV3 } from "@/lib/decisionContract";
import { parseDeviceSnapshotHistoryDetail } from "@/lib/deviceSnapshotHistoryContract";
import {
  coverageLabel,
  deviceCoverageHelperText,
  deviceCoverageLabel,
} from "@/viewModels/decisionCopy";
import { buildDeviceRowViewModel } from "@/viewModels/devices/deviceRowViewModel";
import { buildReportDecisionViewModel } from "@/viewModels/reports/reportDecisionViewModel";
import { buildSnapshotHistoryViewModel } from "@/viewModels/topology/snapshotHistoryViewModel";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import type { DeviceStoryDto } from "@/types/devices";
import { oracleScenario } from "@/test/contracts/oracleFixture";

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
    home_assistant_name: null,
    home_assistant_area_name: null,
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
        dimension: "availability",
        state: "building",
        label_code: "availability_history_building",
        params: {},
      },
    ],
    related_unresolved_incident_ids: [],
    timeline: [],
    ...overrides,
  };
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
      home_assistant_name: null,
      home_assistant_area_name: null,
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

  it("oracle ReportDetailV3 with unknown coverage reaches ViewModel via validator", () => {
    const raw = structuredClone(oracleScenario("unknown_insufficient_data").report);
    expect(raw).toBeTruthy();
    // Preserve valid nullable telemetry; force last_seen unknown on a device fact.
    const devices = raw.domain_details.devices;
    expect(devices.length).toBeGreaterThan(0);
    let nullTelemetry = 0;
    for (const device of devices) {
      if (device.battery === null) nullTelemetry += 1;
      if (device.linkquality === null) nullTelemetry += 1;
      device.last_seen = null;
      nullTelemetry += 1;
    }
    expect(nullTelemetry).toBeGreaterThan(0);

    // Ensure at least one story carries unknown/off/building coverage labels.
    expect(raw.device_stories.length).toBeGreaterThan(0);
    raw.device_stories[0] = {
      ...raw.device_stories[0],
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
          dimension: "availability",
          state: "building",
          label_code: "availability_history_building",
          params: {},
        },
      ],
    };

    const validated = validateReportDetailV3(raw);
    const reportVm = buildReportDecisionViewModel(validated);
    expect(reportVm.deviceStories.length).toBeGreaterThan(0);
    let coverageChecked = 0;
    for (const item of reportVm.deviceStories) {
      for (const coverage of item.story.coverageItems) {
        coverageChecked += 1;
        expect(looksLikeFalseZero(coverage.label)).toBe(false);
      }
    }
    expect(coverageChecked).toBeGreaterThan(0);
    expect(looksLikeFalseZero(reportVm.deviceStories[0]!.story.headline)).toBe(false);
  });

  it("coverage unknown/off/building labels stay non-measured in Device Story ViewModel", () => {
    const storyVm = buildDeviceStoryViewModel(makeStory());
    expect(storyVm.coverageItems.length).toBeGreaterThanOrEqual(3);
    for (const item of storyVm.coverageItems) {
      expect(looksLikeFalseZero(item.label)).toBe(false);
      expect(item.label.toLowerCase()).not.toMatch(/^(0|0%|healthy|complete|no issue)$/);
    }
    expect(looksLikeFalseZero(storyVm.headline)).toBe(false);
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
      "topology_history_unavailable",
    ] as const;
    expect(codes.length).toBeGreaterThan(0);
    for (const code of codes) {
      const label = coverageLabel(
        code,
        code === "topology_history_sparse"
          ? { observed: 0, window: 3 }
          : code === "topology_history_unavailable"
            ? {
                observed_snapshot_count: 0,
                complete_snapshot_count: 2,
                available_layout_snapshot_count: 0,
                limited_layout_snapshot_count: 2,
                snapshot_window_count: 2,
              }
            : {},
      );
      expect(label.trim().length).toBeGreaterThan(0);
      expect(looksLikeFalseZero(label)).toBe(false);
    }
  });

  it("keeps limited topology captures unknown while exposing their count", () => {
    const allLimited = {
      observed_snapshot_count: 0,
      complete_snapshot_count: 2,
      available_layout_snapshot_count: 0,
      limited_layout_snapshot_count: 2,
      snapshot_window_count: 2,
    };
    const label = deviceCoverageLabel(
      "topology_history_unavailable",
      allLimited,
    );
    const helper = deviceCoverageHelperText(
      "topology_history_unavailable",
      allLimited,
    );
    expect(label).toBe("Topology history: 2 captures have no usable layouts");
    expect(helper).toMatch(/device presence cannot be inferred/i);
    expect(`${label} ${helper}`).not.toMatch(/\b0\b|not observed|absent|no links/i);

    const mixed = {
      observed_snapshot_count: 1,
      complete_snapshot_count: 2,
      available_layout_snapshot_count: 1,
      limited_layout_snapshot_count: 1,
      snapshot_window_count: 2,
    };
    expect(deviceCoverageLabel("topology_history_sparse", mixed)).toMatch(
      /1 additional capture had no usable layout/i,
    );
  });

  it("keeps layout-limited snapshot history unavailable through parser and ViewModel", () => {
    const parsed = parseDeviceSnapshotHistoryDetail({
      network_id: "home",
      device_ieee: "0xa1",
      friendly_name: "Kitchen Plug",
      has_current_issue: false,
      availability_tracking: {
        enabled: true,
        earliest_observation_at: null,
      },
      latest_snapshot: {
        snapshot_id: "snap-limited",
        captured_at: "2026-07-13T02:00:00Z",
        is_latest: true,
        layout_state: "limited",
        is_usable: false,
        device_present_in_snapshot: null,
        links_for_device_count: null,
        route_hints_for_device_count: null,
        availability_coverage_status: "tracked",
        availability_state_near_snapshot: null,
        comparison_to_latest: null,
      },
      snapshots: [],
      topology_facts: {
        stale_threshold_hours: null,
        device_facts: [],
        comparison_facts_by_snapshot_id: {},
      },
    });
    const viewModel = buildSnapshotHistoryViewModel(parsed, null);
    expect(viewModel.latest?.summaryText).toBe("Topology layout unavailable");
    expect(viewModel.latest?.summaryText ?? "").not.toMatch(
      /\b0\b|no links|no route hints|device not observed/i,
    );
  });
});
