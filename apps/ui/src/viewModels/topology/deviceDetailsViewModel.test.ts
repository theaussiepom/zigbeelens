import { describe, expect, it } from "vitest";
import type { DataCoverageDto } from "@/types/decisions";
import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import { meshHealthBucketLabel, meshNodeFlagLabel } from "@/lib/meshEvidence";
import {
  DEVICE_SECTION_DATA_COVERAGE,
  DEVICE_SECTION_OPEN_ISSUE,
  DEVICE_SECTION_PASSIVE_HINTS,
  DEVICE_SECTION_RECENT_MISSING,
  DEVICE_SECTION_STATS,
} from "@/lib/meshGraphCopy";
import { buildDeviceDetailsViewModel } from "@/viewModels/topology/deviceDetailsViewModel";

function makeDevice(overrides: Partial<MeshEvidenceDevice> = {}): MeshEvidenceDevice {
  return {
    ieee_address: "0xr1",
    network_id: "home",
    friendly_name: "Live Hall Router",
    role: "router",
    power: "mains",
    availability: "online",
    health_bucket: "healthy",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "Observed in the latest topology snapshot.",
    passive_observation_summary: "",
    diagnostic_stats: [],
    ...overrides,
  };
}

function sectionIds(vm: ReturnType<typeof buildDeviceDetailsViewModel>): string[] {
  return vm.sections.map((section) => section.id);
}

describe("deviceDetailsViewModel", () => {
  it("orders core sections and omits empty optional sections", () => {
    const vm = buildDeviceDetailsViewModel(makeDevice());
    expect(sectionIds(vm)).toEqual([
      "summary",
      "currentStatus",
      "topologyEvidence",
      "snapshotHistory",
    ]);
  });

  it("maps current status labels from device evidence", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({ health_bucket: "needs_attention", availability: "offline" }),
    );
    const status = vm.sections.find((section) => section.id === "currentStatus");
    expect(status?.id).toBe("currentStatus");
    if (status?.id !== "currentStatus") return;
    expect(status.facts[0].value).toBe(meshHealthBucketLabel("needs_attention"));
    expect(status.facts[1].value).toBe("Offline");
  });

  it("includes diagnostic stats when recorded values exist", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        diagnostic_stats: [
          { label: "Last seen", value: "2h ago", detail: "2026-07-06T00:00:00+00:00" },
          { label: "Battery level", value: "12%" },
        ],
      }),
    );
    const stats = vm.sections.find((section) => section.id === "diagnosticStats");
    expect(stats?.title).toBe(DEVICE_SECTION_STATS);
    if (stats?.id !== "diagnosticStats") return;
    expect(stats.stats).toHaveLength(2);
    expect(stats.stats[0].detail).toBe("2026-07-06T00:00:00+00:00");
  });

  it("includes recent missing evidence when a summary exists", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        historical_topology_summary:
          "Previously observed links for this device are not shown in the latest snapshot.",
      }),
    );
    const section = vm.sections.find((section) => section.id === "recentMissing");
    expect(section?.title).toBe(DEVICE_SECTION_RECENT_MISSING);
    if (section?.id !== "recentMissing") return;
    expect(section.body).toContain("Previously observed links");
  });

  it("includes passive hints when a summary exists", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        passive_hint_summary: "Suggested investigation links touch this device.",
      }),
    );
    const section = vm.sections.find((section) => section.id === "passiveHints");
    expect(section?.title).toBe(DEVICE_SECTION_PASSIVE_HINTS);
    if (section?.id !== "passiveHints") return;
    expect(section.body).toContain("Suggested investigation links");
  });

  it("includes open issue section when an issue exists", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        open_issue: {
          title: "Device offline",
          summary: "Recorded as offline in Zigbee2MQTT.",
        },
      }),
    );
    const section = vm.sections.find((section) => section.id === "openIssue");
    expect(section?.title).toBe(DEVICE_SECTION_OPEN_ISSUE);
    if (section?.id !== "openIssue") return;
    expect(section.issueTitle).toBe("Device offline");
    expect(section.issueSummary).toContain("Recorded as offline");
  });

  it("maps header flags through mesh node flag labels", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({ flags: ["needs_attention", "battery_sleepy"] }),
    );
    expect(vm.header.flagLabels).toEqual([
      meshNodeFlagLabel("needs_attention"),
      meshNodeFlagLabel("battery_sleepy"),
    ]);
  });

  it("places snapshot history after topology and recent missing sections", () => {
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        historical_topology_summary: "Recent missing links were observed.",
        passive_hint_summary: "Passive hints available.",
        open_issue: { title: "Issue", summary: "Summary" },
      }),
    );
    expect(sectionIds(vm)).toEqual([
      "summary",
      "currentStatus",
      "topologyEvidence",
      "recentMissing",
      "snapshotHistory",
      "passiveHints",
      "openIssue",
    ]);
    const snapshotHistory = vm.sections.find((section) => section.id === "snapshotHistory");
    if (snapshotHistory?.id !== "snapshotHistory") return;
    expect(snapshotHistory.networkId).toBe("home");
    expect(snapshotHistory.deviceIeee).toBe("0xr1");
  });

  it("omits dataCoverage when network coverage is empty", () => {
    const vm = buildDeviceDetailsViewModel(makeDevice(), []);
    expect(vm.sections.some((section) => section.id === "dataCoverage")).toBe(false);
  });

  it("includes filtered network coverage after snapshot history", () => {
    const coverage: DataCoverageDto[] = [
      {
        dimension: "availability",
        state: "off",
        label_code: "availability_tracking_off",
      },
      {
        dimension: "availability",
        state: "building",
        label_code: "availability_history_building",
      },
      {
        dimension: "topology_snapshot",
        state: "stale",
        label_code: "snapshot_stale",
      },
    ];
    const vm = buildDeviceDetailsViewModel(
      makeDevice({
        passive_hint_summary: "Passive hints available.",
      }),
      coverage,
    );
    const ids = sectionIds(vm);
    const section = vm.sections.find((item) => item.id === "dataCoverage");
    expect(section?.title).toBe(DEVICE_SECTION_DATA_COVERAGE);
    if (section?.id !== "dataCoverage") return;
    expect(section.items.map((item) => item.label)).toEqual([
      "Availability tracking off",
      "Snapshot stale",
    ]);
    expect(ids.indexOf("dataCoverage")).toBeGreaterThan(ids.indexOf("snapshotHistory"));
    expect(ids.indexOf("dataCoverage")).toBeLessThan(ids.indexOf("passiveHints"));
  });
});
