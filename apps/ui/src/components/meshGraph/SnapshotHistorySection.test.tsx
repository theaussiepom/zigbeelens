import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceSnapshotHistoryDetail, DeviceSnapshotHistoryRow } from "@/types/devices";

const eventListeners = new Set<(eventName: string) => void>();
const stateListeners = new Set<(state: string) => void>();
const emit = (eventName: string) => {
  for (const listener of eventListeners) listener(eventName);
};
const emitState = (state: string) => {
  for (const listener of stateListeners) listener(state);
};

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: (listener: (e: string) => void) => {
      eventListeners.add(listener);
      return () => {
        eventListeners.delete(listener);
      };
    },
    subscribeState: (listener: (state: string) => void) => {
      stateListeners.add(listener);
      listener("open");
      return () => {
        stateListeners.delete(listener);
      };
    },
    getState: () => "open",
    isAccessEnabled: () => true,
  },
}));

const topologyDeviceSnapshotHistory = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    topologyDeviceSnapshotHistory: (...args: unknown[]) =>
      topologyDeviceSnapshotHistory(...args),
  },
  ApiError: class ApiError extends Error {},
}));

import { SnapshotHistorySection } from "./SnapshotHistorySection";

function makeRow(overrides: Partial<DeviceSnapshotHistoryRow>): DeviceSnapshotHistoryRow {
  return {
    snapshot_id: "snap-prev",
    captured_at: "2026-07-05T19:10:00+00:00",
    is_latest: false,
    is_usable: true,
    links_for_device_count: 6,
    route_hints_for_device_count: 2,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: {
      status: "changed",
      reasons: ["Selected snapshot differs."],
      suggested_checks: [],
      link_counts: {
        latest_count: 0,
        selected_count: 6,
        latest_only_count: 0,
        selected_only_count: 6,
        changed_count: 0,
      },
      route_hint_counts: {
        latest_count: 0,
        selected_count: 2,
        latest_only_count: 0,
        selected_only_count: 2,
        changed_count: 0,
      },
    },
    ...overrides,
  };
}

function historyPayload(snapshotIds: string[]): DeviceSnapshotHistoryDetail {
  const latestId = snapshotIds[0] ?? "snap-live";
  const earlier = snapshotIds.slice(1);
  return {
    network_id: "home",
    device_ieee: "0xabc",
    friendly_name: "Sensor",
    has_current_issue: false,
    availability_tracking: {
      enabled: true,
      earliest_observation_at: "2026-07-01T00:00:00+00:00",
    },
    latest_snapshot: makeRow({
      snapshot_id: latestId,
      captured_at: "2026-07-06T00:30:00+00:00",
      is_latest: true,
      comparison_to_latest: null,
    }),
    snapshots: earlier.map((id, index) =>
      makeRow({
        snapshot_id: id,
        captured_at: `2026-07-0${5 - index}T00:00:00+00:00`,
      }),
    ),
    topology_facts: {
      stale_threshold_hours: null,
      device_facts: [],
      comparison_facts_by_snapshot_id: {},
    },
  };
}

describe("SnapshotHistorySection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    eventListeners.clear();
    stateListeners.clear();
    topologyDeviceSnapshotHistory.mockReset();
    topologyDeviceSnapshotHistory.mockResolvedValue(
      historyPayload(["snap-live", "snap-prev", "snap-older"]),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads, refetches on topology_updated, preserves/falls back selection", async () => {
    render(<SnapshotHistorySection networkId="home" deviceIeee="0xabc" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("snapshot-history-list")).toBeInTheDocument();

    const older = screen
      .getAllByRole("button")
      .find((button) => button.getAttribute("aria-pressed") === "false");
    expect(older).toBeTruthy();
    await act(async () => {
      older!.click();
    });

    topologyDeviceSnapshotHistory.mockResolvedValue(
      historyPayload(["snap-live", "snap-prev", "snap-older"]),
    );
    act(() => emit("topology_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { pressed: true })).toBeInTheDocument();

    topologyDeviceSnapshotHistory.mockResolvedValue(
      historyPayload(["snap-live", "snap-prev"]),
    );
    act(() => emit("topology_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(3);
    expect(screen.getByTestId("snapshot-history-list").querySelectorAll("li")).toHaveLength(1);

    act(() => emit("collector_status"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(3);
  });

  it("rejects stale responses after device change and polls while disconnected", async () => {
    const { rerender, unmount } = render(
      <SnapshotHistorySection networkId="home" deviceIeee="0xabc" />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(1);

    let resolveStale: (value: unknown) => void = () => {};
    topologyDeviceSnapshotHistory.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveStale = resolve;
        }),
    );
    topologyDeviceSnapshotHistory.mockResolvedValue(historyPayload(["snap-def"]));
    rerender(<SnapshotHistorySection networkId="home" deviceIeee="0xdef" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveStale(historyPayload(["snap-stale"]));
      await Promise.resolve();
    });
    expect(screen.queryByText(/snap-stale/i)).toBeNull();

    act(() => emitState("disconnected"));
    act(() => vi.advanceTimersByTime(30_000));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyDeviceSnapshotHistory.mock.calls.length).toBeGreaterThanOrEqual(3);

    unmount();
    const callsAfterUnmount = topologyDeviceSnapshotHistory.mock.calls.length;
    act(() => vi.advanceTimersByTime(30_000));
    expect(topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(callsAfterUnmount);
  });
});
