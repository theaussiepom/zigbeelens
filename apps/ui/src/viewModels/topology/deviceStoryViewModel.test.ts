import { describe, expect, it } from "vitest";
import type { DeviceStoryDto } from "@/types/devices";
import {
  DEVICE_SECTION_STORY,
  DEVICE_STORY_CHECKS_TITLE,
  DEVICE_STORY_LIMITATIONS_TITLE,
  DEVICE_STORY_WHY_TITLE,
} from "@/lib/meshGraphCopy";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";

const topologyGapStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0x03",
  status: "watch",
  priority: "low",
  headline_code: "topology_evidence_gap",
  reasons: [
    { code: "latest_snapshot_no_links", params: {} },
    { code: "selected_snapshot_had_links", params: { selected_snapshot_link_count: 1 } },
  ],
  evidence: [
    {
      source: "topology_snapshot",
      id: "snap-latest",
      captured_at: "2026-07-13T02:00:00Z",
      label: null,
    },
  ],
  limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
  suggested_checks: [{ code: "compare_earlier_snapshot", params: {} }],
  coverage: [
    {
      dimension: "route_hints",
      state: "not_observed",
      label_code: "route_hints_unavailable",
      params: {},
    },
  ],
  timeline: [],
};

describe("deviceStoryViewModel", () => {
  it("maps topology-gap story codes to approved user-facing copy", () => {
    const vm = buildDeviceStoryViewModel(topologyGapStory);
    expect(vm.sectionTitle).toBe(DEVICE_SECTION_STORY);
    expect(vm.statusPill?.label).toBe("Watch");
    expect(vm.statusPill?.tone).toBe("watch");
    expect(vm.headline).toBe("Topology evidence gap");
    expect(vm.headlineLead).toMatch(/does not prove the device failed/i);
    expect(vm.whyTitle).toBe(DEVICE_STORY_WHY_TITLE);
    expect(vm.reasons).toEqual([
      "Latest snapshot shows no links for this device.",
      "Selected snapshot showed 1 link for this device.",
    ]);
    expect(vm.limitationsTitle).toBe(DEVICE_STORY_LIMITATIONS_TITLE);
    expect(vm.limitations[0]).toMatch(/does not prove the device failed/i);
    expect(vm.checksTitle).toBe(DEVICE_STORY_CHECKS_TITLE);
    expect(vm.suggestedChecks).toEqual([
      "Compare an earlier topology snapshot for this device.",
    ]);
    expect(vm.coverageItems.map((item) => item.label)).toEqual(["Route hints unavailable"]);
    expect(vm.evidenceLines[0]).toContain("Latest stored topology snapshot");
    expect(vm.timeline).toEqual([]);
  });

  it("maps current issue story to review-first status copy", () => {
    const vm = buildDeviceStoryViewModel({
      ...topologyGapStory,
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      reasons: [{ code: "current_issue_present", params: {} }],
      limitations: [],
      suggested_checks: [
        { code: "confirm_powered", params: {} },
        { code: "confirm_reporting_in_z2m", params: {} },
      ],
      coverage: [],
      evidence: [],
    });
    expect(vm.statusPill?.label).toBe("Review first");
    expect(vm.headline).toBe("Current issue needs attention");
    expect(vm.suggestedChecks).toEqual([
      "Confirm the device is powered.",
      "Confirm the device is reporting in Zigbee2MQTT.",
    ]);
  });

  it("falls back safely for unknown headline codes", () => {
    const vm = buildDeviceStoryViewModel({
      ...topologyGapStory,
      headline_code: "future_headline",
      reasons: [{ code: "future_reason", params: {} }],
      limitations: [{ code: "future_limitation", params: {} }],
      suggested_checks: [{ code: "future_check", params: {} }],
    });
    expect(vm.headline).toBe("Device story summary unavailable.");
    expect(vm.reasons).toEqual(["Details unavailable."]);
    expect(vm.limitations[0]).toMatch(/interpretation is limited/i);
    expect(vm.suggestedChecks[0]).toMatch(/review stored evidence/i);
  });
});
