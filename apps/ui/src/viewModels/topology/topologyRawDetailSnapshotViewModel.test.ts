import { describe, expect, it } from "vitest";
import type { TopologyLinkRow, TopologyNodeRow, TopologySnapshotSummary } from "@/types/topology";
import {
  RAW_DETAIL_ERROR_GENERIC_COPY,
  RAW_DETAIL_PENDING_COPY,
  RAW_DETAIL_UNKNOWN_COPY,
  buildTopologyRawDetailSnapshotViewModel,
} from "./topologyRawDetailSnapshotViewModel";

const node: TopologyNodeRow = {
  ieee_address: "0xabc",
  friendly_name: "Router",
  node_type: "Router",
  lqi: 100,
};

const link: TopologyLinkRow = {
  source_ieee: "0xabc",
  target_ieee: "0xdef",
  relationship: "Child",
  linkquality: 90,
};

function snap(overrides: Partial<TopologySnapshotSummary> = {}): TopologySnapshotSummary {
  return {
    snapshot_id: "snap-1",
    status: "complete",
    captured_at: "2026-06-16T02:17:53.509572+00:00",
    requested_by: "startup_scan",
    router_count: 2,
    link_count: 4,
    end_device_count: 8,
    ...overrides,
  };
}

describe("buildTopologyRawDetailSnapshotViewModel", () => {
  it("presents no snapshot", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(null, [], []);
    expect(vm.kind).toBe("no_snapshot");
    expect(vm.severity).toBe("watch");
    expect(vm.showRawContents).toBe(false);
    expect(vm.showTopologyCounts).toBe(false);
  });

  it("presents complete with usable layout", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(snap(), [node], [link]);
    expect(vm.kind).toBe("complete");
    expect(vm.label).toBe("Complete");
    expect(vm.severity).toBe("healthy");
    expect(vm.showTopologyCounts).toBe(true);
    expect(vm.showRawContents).toBe(true);
    expect(vm.showLimitedLayoutCopy).toBe(false);
    expect(vm.showPointInTimeLimitation).toBe(true);
    expect(vm.counts.routers).toBe(2);
  });

  it("presents complete with layout limited", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(
      snap({ router_count: 0, link_count: 0, end_device_count: 0 }),
      [],
      [],
    );
    expect(vm.kind).toBe("complete_limited");
    expect(vm.label).toBe("Complete · layout limited");
    expect(vm.severity).toBe("watch");
    expect(vm.showTopologyCounts).toBe(true);
    expect(vm.counts.routers).toBe("—");
    expect(vm.showLimitedLayoutCopy).toBe(true);
    expect(vm.showRawContents).toBe(false);
  });

  it("presents pending without completed topology evidence", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(
      snap({ status: "pending" }),
      [node],
      [link],
    );
    expect(vm.kind).toBe("pending");
    expect(vm.label).toBe("Pending");
    expect(vm.severity).toBe("watch");
    expect(vm.statusCopy).toBe(RAW_DETAIL_PENDING_COPY);
    expect(vm.showTopologyCounts).toBe(false);
    expect(vm.showLimitedLayoutCopy).toBe(false);
    expect(vm.showRawContents).toBe(false);
  });

  it("presents error with stored error text", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(
      snap({ status: "error", error: "bridge timed out" }),
      [],
      [],
    );
    expect(vm.kind).toBe("error");
    expect(vm.label).toBe("Error");
    expect(vm.severity).toBe("critical");
    expect(vm.statusCopy).toBe("bridge timed out");
    expect(vm.showTopologyCounts).toBe(false);
    expect(vm.showRawContents).toBe(false);
    expect(vm.showLimitedLayoutCopy).toBe(false);
  });

  it("presents error with generic copy when no stored error", () => {
    const vm = buildTopologyRawDetailSnapshotViewModel(snap({ status: "error", error: null }), [], []);
    expect(vm.statusCopy).toBe(RAW_DETAIL_ERROR_GENERIC_COPY);
    expect(vm.severity).toBe("critical");
  });

  it("never treats null or future status as complete", () => {
    for (const status of [null, undefined, "", "future_status_v2"] as const) {
      const vm = buildTopologyRawDetailSnapshotViewModel(snap({ status }), [node], [link]);
      expect(vm.kind).toBe("unknown");
      expect(vm.label).toBe("Status unknown");
      expect(vm.severity).toBe("watch");
      expect(vm.statusCopy).toBe(RAW_DETAIL_UNKNOWN_COPY);
      expect(vm.showTopologyCounts).toBe(false);
      expect(vm.showRawContents).toBe(false);
      expect(vm.showLimitedLayoutCopy).toBe(false);
    }
  });
});
