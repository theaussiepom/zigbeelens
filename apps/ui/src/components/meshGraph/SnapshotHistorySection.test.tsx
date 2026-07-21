import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { DeviceSnapshotHistoryDetail, DeviceSnapshotHistoryRow } from "@/types/devices";
import type { DeviceSnapshotCompareStatus } from "@/types/devices";

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

import { DeviceSnapshotHistory, SnapshotHistorySection } from "./SnapshotHistorySection";

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

  it("shows comparison status, reasons, and collapsed evidence details", async () => {
    topologyDeviceSnapshotHistory.mockResolvedValue({
      network_id: "home",
      device_ieee: "0xabc",
      friendly_name: "Lamp",
      has_current_issue: true,
      availability_tracking: {
        enabled: true,
        earliest_observation_at: "2026-07-01T00:00:00+00:00",
      },
      latest_snapshot: makeRow({
        snapshot_id: "snap-live",
        is_latest: true,
        links_for_device_count: 0,
        route_hints_for_device_count: 0,
        availability_state_near_snapshot: "offline",
        comparison_to_latest: null,
      }),
      snapshots: [
        makeRow({
          snapshot_id: "snap-prev",
          comparison_to_latest: {
            status: "worth_reviewing" as DeviceSnapshotCompareStatus,
            reasons: [
              "Latest snapshot shows no links for this device.",
              "The selected snapshot showed 6 links.",
            ],
            suggested_checks: [
              "Confirm the device is powered.",
              "Check whether it is reporting in Zigbee2MQTT.",
            ],
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
        }),
      ],
      topology_facts: {
        stale_threshold_hours: null,
        device_facts: [],
        comparison_facts_by_snapshot_id: {},
      },
    });

    render(<SnapshotHistorySection networkId="home" deviceIeee="0xabc" />);
    await act(async () => {
      await Promise.resolve();
    });

    const section = screen.getByTestId("snapshot-history-section");
    const card = within(section).getByTestId("snapshot-comparison-card");
    expect(within(card).getByText("Worth reviewing")).toBeInTheDocument();
    expect(
      within(card).getByText("Latest snapshot shows no links for this device."),
    ).toBeInTheDocument();
    expect(within(card).getByText("Confirm the device is powered.")).toBeInTheDocument();
    expect(
      within(section).queryByTestId("snapshot-evidence-details"),
    ).not.toBeInTheDocument();

    await act(async () => {
      within(section).getByRole("button", { name: "Evidence details" }).click();
    });
    const details = within(section).getByTestId("snapshot-evidence-details");
    expect(details).toHaveTextContent("0 links shown in latest snapshot");
    expect(details).toHaveTextContent(
      "Route hints are route-table hints captured during topology collection",
    );
  });

  it("renders page chrome with Raw snapshot support link", async () => {
    render(
      <MemoryRouter>
        <DeviceSnapshotHistory
          networkId="Home Office"
          deviceIeee="0xabc"
          showHeading
          showRawSnapshotLink
        />
      </MemoryRouter>,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("device-snapshot-history")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /snapshot history/i })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /raw snapshot/i });
    expect(link).toHaveAttribute("href", "/topology/Home%20Office");
  });

  it("keeps snapshot-history errors section-local", async () => {
    topologyDeviceSnapshotHistory.mockRejectedValueOnce(new Error("boom"));
    render(<SnapshotHistorySection networkId="home" deviceIeee="0xabc" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText(/snapshot history is unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/loading snapshot history/i)).not.toBeInTheDocument();
  });

  it("keeps loaded history and selection when a background refresh fails", async () => {
    render(<SnapshotHistorySection networkId="home" deviceIeee="0xabc" />);
    await act(async () => {
      await Promise.resolve();
    });

    const earlier = screen
      .getAllByRole("button")
      .find((button) => button.getAttribute("aria-pressed") === "false");
    expect(earlier).toBeTruthy();
    await act(async () => {
      earlier!.click();
    });
    expect(screen.getByRole("button", { pressed: true })).toBe(earlier);

    let rejectRefresh: (reason?: unknown) => void = () => {};
    topologyDeviceSnapshotHistory.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectRefresh = reject;
        }),
    );

    act(() => emit("topology_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("snapshot-history-list")).toBeInTheDocument();
    expect(screen.getByRole("button", { pressed: true })).toBe(earlier);
    expect(screen.queryByTestId("snapshot-history-refresh-warning")).not.toBeInTheDocument();

    await act(async () => {
      rejectRefresh(new Error("refresh failed"));
      await Promise.resolve();
    });

    expect(screen.getByTestId("snapshot-history-refresh-warning")).toBeInTheDocument();
    expect(
      screen.getByText(/could not be refreshed\. showing the last loaded data/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { pressed: true })).toBe(earlier);
    expect(screen.getByTestId("snapshot-comparison-card")).toBeInTheDocument();

    topologyDeviceSnapshotHistory.mockResolvedValue(
      historyPayload(["snap-live", "snap-prev", "snap-older"]),
    );
    await act(async () => {
      screen.getByRole("button", { name: /^retry$/i }).click();
      await Promise.resolve();
    });

    expect(screen.queryByTestId("snapshot-history-refresh-warning")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { pressed: true })).toBeInTheDocument();
    expect(screen.getByTestId("snapshot-history-list")).toBeInTheDocument();
  });
});
