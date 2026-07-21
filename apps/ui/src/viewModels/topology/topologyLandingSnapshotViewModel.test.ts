import { describe, expect, it } from "vitest";
import type { TopologySnapshotSummary } from "@/types/topology";
import { buildTopologyLandingSnapshotViewModel } from "./topologyLandingSnapshotViewModel";

function snap(overrides: Partial<TopologySnapshotSummary> = {}): TopologySnapshotSummary {
  return {
    snapshot_id: "snap-1",
    captured_at: "2026-06-16T02:17:53.509572+00:00",
    status: "complete",
    router_count: 2,
    link_count: 4,
    end_device_count: 8,
    ...overrides,
  };
}

describe("buildTopologyLandingSnapshotViewModel", () => {
  it("presents no snapshot calmly", () => {
    const vm = buildTopologyLandingSnapshotViewModel(null);
    expect(vm.label).toBe("No snapshot");
    expect(vm.severity).toBe("watch");
    expect(vm.summaryText).toMatch(/no topology snapshot/i);
    expect(vm.summaryText).not.toMatch(/\b0\b/);
  });

  it("presents complete usable counts", () => {
    const vm = buildTopologyLandingSnapshotViewModel(snap());
    expect(vm.label).toBe("Complete");
    expect(vm.severity).toBe("healthy");
    expect(vm.summaryText).toMatch(/2 topology routers/);
    expect(vm.summaryText).toMatch(/4 topology links/);
  });

  it("presents complete layout-limited without measured zeros", () => {
    const vm = buildTopologyLandingSnapshotViewModel(
      snap({ router_count: 0, link_count: 0, end_device_count: 0 }),
    );
    expect(vm.label).toBe("Complete · layout limited");
    expect(vm.severity).toBe("watch");
    expect(vm.summaryText).toMatch(/layout limited/i);
    expect(vm.summaryText).not.toMatch(/0 topology routers/);
  });

  it("presents pending without completed counts", () => {
    const vm = buildTopologyLandingSnapshotViewModel(snap({ status: "pending" }));
    expect(vm.label).toBe("Pending");
    expect(vm.severity).toBe("watch");
    expect(vm.summaryText).toMatch(/pending/i);
    expect(vm.summaryText).not.toMatch(/topology routers/);
  });

  it("presents error without a healthy snapshot badge", () => {
    const vm = buildTopologyLandingSnapshotViewModel(snap({ status: "error" }));
    expect(vm.label).toBe("Error");
    expect(vm.severity).toBe("critical");
    expect(vm.summaryText).toMatch(/error/i);
    expect(vm.summaryText).not.toMatch(/topology routers/);
  });

  it("never assumes complete for missing/unknown status", () => {
    expect(buildTopologyLandingSnapshotViewModel(snap({ status: null })).label).toBe(
      "Status unknown",
    );
    expect(buildTopologyLandingSnapshotViewModel(snap({ status: undefined })).label).toBe(
      "Status unknown",
    );
    expect(buildTopologyLandingSnapshotViewModel(snap({ status: "" })).label).toBe(
      "Status unknown",
    );
    expect(buildTopologyLandingSnapshotViewModel(snap({ status: "weird" })).label).toBe(
      "Status unknown",
    );
    for (const status of [null, undefined, "", "weird"] as const) {
      const vm = buildTopologyLandingSnapshotViewModel(snap({ status }));
      expect(vm.severity).toBe("watch");
      expect(vm.label).not.toBe("Complete");
    }
  });
});
