import { describe, expect, it } from "vitest";
import type { DataCoverageDto } from "@/types/decisions";
import {
  buildDeviceCoverageStripViewModel,
  buildEvidenceCoverageStripViewModel,
  DEVICE_DRAWER_COVERAGE_LABEL_CODES,
} from "./coverageStripViewModel";

function coverage(label_code: DataCoverageDto["label_code"]): DataCoverageDto {
  return {
    dimension: "availability",
    state: "off",
    label_code,
    params: {},
  };
}

describe("coverageStripViewModel", () => {
  it("orders required Phase 3E labels deterministically", () => {
    const vm = buildEvidenceCoverageStripViewModel([
      coverage("ha_areas_not_linked"),
      coverage("snapshot_stale"),
      coverage("availability_tracking_off"),
      coverage("route_hints_unavailable"),
      coverage("availability_history_building"),
      coverage("availability_status_unknown"),
    ]);
    expect(vm.items.map((item) => item.label)).toEqual([
      "Availability tracking off",
      "Availability history building",
      "Availability status unknown",
      "Snapshot stale",
      "Route hints unavailable",
      "HA areas not linked",
    ]);
  });

  it("provides helper text for each required Phase 3E label", () => {
    const codes = [
      "availability_tracking_off",
      "availability_history_building",
      "availability_status_unknown",
      "route_hints_unavailable",
      "ha_areas_not_linked",
      "snapshot_stale",
    ] as const;
    for (const code of codes) {
      const vm = buildEvidenceCoverageStripViewModel([coverage(code)]);
      expect(vm.items[0]?.helper.length).toBeGreaterThan(20);
    }
  });

  it("uses network-neutral HA helper copy", () => {
    const vm = buildEvidenceCoverageStripViewModel([coverage("ha_areas_not_linked")]);
    expect(vm.items[0]?.helper).toMatch(/not a zigbee network fault/i);
    expect(vm.items[0]?.helper.toLowerCase()).not.toContain("for this device");
  });

  it("falls back safely for unknown label codes", () => {
    const vm = buildEvidenceCoverageStripViewModel([
      {
        dimension: "reports",
        state: "unknown",
        label_code: "future_backend_label" as DataCoverageDto["label_code"],
      },
    ]);
    expect(vm.items[0]?.label).toBe("Coverage status unknown");
    expect(vm.items[0]?.helper).toMatch(/interpret other evidence conservatively/i);
  });

  it("preserves route-hints helper semantics", () => {
    const vm = buildEvidenceCoverageStripViewModel([coverage("route_hints_unavailable")]);
    expect(vm.items[0]?.helper).toMatch(/does not mean routes are absent/i);
    expect(vm.items[0]?.helper).not.toMatch(/no routes/i);
  });

  it("preserves HA helper semantics", () => {
    const vm = buildEvidenceCoverageStripViewModel([coverage("ha_areas_not_linked")]);
    expect(vm.items[0]?.helper).toMatch(/home assistant area enrichment/i);
    expect(vm.items[0]?.helper).toMatch(/not a zigbee network fault/i);
    expect(vm.items[0]?.helper).not.toMatch(/re-pair|router|channel/i);
  });

  it("preserves stale helper semantics", () => {
    const vm = buildEvidenceCoverageStripViewModel([coverage("snapshot_stale")]);
    expect(vm.items[0]?.helper).toMatch(/older than the configured capture cadence/i);
    expect(vm.items[0]?.helper).not.toMatch(/capture now|trigger capture|automatic capture/i);
  });

  it("filters device-drawer coverage to relevant network constraints", () => {
    const vm = buildEvidenceCoverageStripViewModel(
      [
        coverage("availability_tracking_off"),
        coverage("availability_history_building"),
        coverage("snapshot_stale"),
        coverage("route_hints_unavailable"),
      ],
      { filterLabelCodes: DEVICE_DRAWER_COVERAGE_LABEL_CODES },
    );
    expect(vm.items.map((item) => item.label)).toEqual([
      "Availability tracking off",
      "Snapshot stale",
      "Route hints unavailable",
    ]);
  });

  it("orders per-device coverage by dimension", () => {
    const vm = buildEvidenceCoverageStripViewModel(
      [
        {
          dimension: "ha_enrichment",
          state: "not_configured",
          label_code: "ha_areas_not_linked",
        },
        {
          dimension: "availability",
          state: "available",
          label_code: "availability_available",
        },
        {
          dimension: "last_seen",
          state: "available",
          label_code: "last_seen_available",
        },
      ],
      { presentation: "device" },
    );
    expect(vm.items.map((item) => item.label)).toEqual([
      "Availability: available",
      "Last seen: available",
      "HA area: missing",
    ]);
  });

  it("uses device availability helper copy", () => {
    const vm = buildDeviceCoverageStripViewModel([
      {
        dimension: "availability",
        state: "building",
        label_code: "availability_history_building",
      },
    ]);
    expect(vm.items[0]?.label).toBe("Availability: building");
    expect(vm.items[0]?.helper).toMatch(/this device/i);
    expect(vm.items[0]?.helper.toLowerCase()).not.toContain("turned on");
  });

  it("uses device topology helper copy for zero snapshot window", () => {
    const vm = buildDeviceCoverageStripViewModel([
      {
        dimension: "historical_snapshots",
        state: "not_observed",
        label_code: "topology_history_not_observed",
        params: { observed_snapshot_count: 0, snapshot_window_count: 0 },
      },
    ]);
    expect(vm.items[0]?.label).toBe("Topology history: 0 of 0 snapshots");
    expect(vm.items[0]?.helper).toBe(
      "No complete stored topology snapshots are available to assess this device yet.",
    );
    expect(vm.items[0]?.helper).not.toMatch(/not observed in any considered/i);
  });

  it("uses device topology helper copy for zero of N", () => {
    const vm = buildDeviceCoverageStripViewModel([
      {
        dimension: "historical_snapshots",
        state: "not_observed",
        label_code: "topology_history_not_observed",
        params: { observed_snapshot_count: 0, snapshot_window_count: 10 },
      },
    ]);
    expect(vm.items[0]?.helper).toMatch(
      /not observed in the considered stored topology snapshots/i,
    );
  });

  it("returns an empty strip when coverage is empty", () => {
    expect(buildEvidenceCoverageStripViewModel([]).items).toEqual([]);
  });
});
