import { describe, expect, it } from "vitest";
import {
  resolveTopologyDisplayCounts,
  snapshotSummaryLooksLimited,
  TOPOLOGY_LIMITED_VALUE,
} from "@/lib/topologyStats";

describe("resolveTopologyDisplayCounts", () => {
  it("shows limited markers when parsed layout data is empty", () => {
    const counts = resolveTopologyDisplayCounts(
      {
        snapshot_id: "snap-1",
        network_id: "home",
        status: "complete",
        router_count: 0,
        end_device_count: 0,
        link_count: 0,
      },
      [],
      [],
    );
    expect(counts.layoutAvailable).toBe(false);
    expect(counts.routers).toBe(TOPOLOGY_LIMITED_VALUE);
    expect(counts.endDevices).toBe(TOPOLOGY_LIMITED_VALUE);
    expect(counts.links).toBe(TOPOLOGY_LIMITED_VALUE);
  });

  it("shows parsed topology counts when layout data exists", () => {
    const counts = resolveTopologyDisplayCounts(
      {
        snapshot_id: "snap-1",
        network_id: "home",
        status: "complete",
        router_count: 2,
        end_device_count: 8,
        link_count: 4,
      },
      [{ ieee_address: "0x1", node_type: "Router" }],
      [{ source_ieee: "0x1", target_ieee: "0x2" }],
    );
    expect(counts.layoutAvailable).toBe(true);
    expect(counts.routers).toBe(2);
    expect(counts.endDevices).toBe(8);
    expect(counts.links).toBe(4);
  });
});

describe("snapshotSummaryLooksLimited", () => {
  it("detects complete snapshots with zero topology counts", () => {
    expect(
      snapshotSummaryLooksLimited({
        status: "complete",
        router_count: 0,
        end_device_count: 0,
        link_count: 0,
      }),
    ).toBe(true);
    expect(
      snapshotSummaryLooksLimited({
        status: "complete",
        router_count: 1,
        end_device_count: 0,
        link_count: 0,
      }),
    ).toBe(false);
  });
});
