import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { parseDeviceSnapshotHistoryDetail } from "@/lib/deviceSnapshotHistoryContract";

function comparison() {
  return {
    status: "no_notable_change",
    reasons: ["Similar number of links shown."],
    suggested_checks: [],
    link_counts: {
      latest_count: 0,
      selected_count: 0,
      latest_only_count: 0,
      selected_only_count: 0,
      changed_count: 0,
    },
    route_hint_counts: {
      latest_count: 0,
      selected_count: 0,
      latest_only_count: 0,
      selected_only_count: 0,
      changed_count: 0,
    },
  };
}

function availableRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    snapshot_id: "snap-latest",
    captured_at: "2026-07-13T02:00:00Z",
    is_latest: true,
    layout_state: "available",
    is_usable: true,
    device_present_in_snapshot: true,
    links_for_device_count: 0,
    route_hints_for_device_count: 0,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: null,
    ...overrides,
  };
}

function limitedRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    snapshot_id: "snap-limited",
    captured_at: "2026-07-12T02:00:00Z",
    is_latest: false,
    layout_state: "limited",
    is_usable: false,
    device_present_in_snapshot: null,
    links_for_device_count: null,
    route_hints_for_device_count: null,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: null,
    comparison_to_latest: null,
    ...overrides,
  };
}

function detail(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    network_id: "home",
    device_ieee: "0xabc",
    friendly_name: "Sensor",
    has_current_issue: false,
    availability_tracking: {
      enabled: true,
      earliest_observation_at: "2026-07-01T00:00:00Z",
    },
    latest_snapshot: availableRow(),
    snapshots: [limitedRow()],
    topology_facts: {
      stale_threshold_hours: 24,
      device_facts: [],
      comparison_facts_by_snapshot_id: {},
    },
    ...overrides,
  };
}

function expectProtocolFailure(value: unknown): void {
  try {
    parseDeviceSnapshotHistoryDetail(value);
    throw new Error("expected parser to reject malformed value");
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "protocol", detail: "malformed" });
  }
}

describe("device snapshot-history runtime contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("preserves factual available zero and null limited evidence", () => {
    const parsed = parseDeviceSnapshotHistoryDetail(detail());
    expect(parsed.latest_snapshot).toMatchObject({
      layout_state: "available",
      is_usable: true,
      device_present_in_snapshot: true,
      links_for_device_count: 0,
      route_hints_for_device_count: 0,
    });
    expect(parsed.snapshots[0]).toEqual(
      expect.objectContaining({
        layout_state: "limited",
        is_usable: false,
        device_present_in_snapshot: null,
        links_for_device_count: null,
        route_hints_for_device_count: null,
        comparison_to_latest: null,
      }),
    );
  });

  it.each([
    ["is_usable", true],
    ["device_present_in_snapshot", false],
    ["links_for_device_count", 0],
    ["route_hints_for_device_count", 0],
    ["comparison_to_latest", comparison()],
  ])("rejects limited layout with legacy or inferred %s=%j", (field, value) => {
    expectProtocolFailure(
      detail({
        snapshots: [limitedRow({ [field]: value })],
      }),
    );
  });

  it.each([
    ["is_usable", false],
    ["device_present_in_snapshot", null],
    ["links_for_device_count", null],
    ["route_hints_for_device_count", null],
    ["links_for_device_count", -1],
    ["route_hints_for_device_count", 1.5],
  ])("rejects malformed available %s=%j", (field, value) => {
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({ [field]: value }),
      }),
    );
  });

  it("rejects positive counts when an available row says the device was absent", () => {
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({
          device_present_in_snapshot: false,
          links_for_device_count: 1,
        }),
      }),
    );
  });

  it("requires comparison exactly when both latest and earlier layouts are available", () => {
    expectProtocolFailure(
      detail({
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: null,
          }),
        ],
      }),
    );

    const parsed = parseDeviceSnapshotHistoryDetail(
      detail({
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: comparison(),
          }),
        ],
      }),
    );
    expect(parsed.snapshots[0]?.comparison_to_latest?.status).toBe(
      "no_notable_change",
    );
  });

  it("accepts a limited latest layout only without earlier comparisons", () => {
    const parsed = parseDeviceSnapshotHistoryDetail(
      detail({
        latest_snapshot: limitedRow({
          snapshot_id: "snap-latest",
          is_latest: true,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: null,
          }),
        ],
      }),
    );
    expect(parsed.latest_snapshot?.layout_state).toBe("limited");
    expect(parsed.snapshots[0]?.comparison_to_latest).toBeNull();

    expectProtocolFailure(
      detail({
        latest_snapshot: limitedRow({
          snapshot_id: "snap-latest",
          is_latest: true,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: comparison(),
          }),
        ],
      }),
    );
  });

  it("wires the strict parser into the API client and fails closed", async () => {
    const malformed = detail({
      snapshots: [limitedRow({ links_for_device_count: 0 })],
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(malformed), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api.topologyDeviceSnapshotHistory("home", "0xabc"),
    ).rejects.toMatchObject({
      kind: "protocol",
      detail: "malformed",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
