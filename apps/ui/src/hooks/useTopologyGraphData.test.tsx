import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeTopologyEvidenceGraphDetail } from "@/test/topologyEvidenceGraphFixture";

const listeners = new Set<(eventName: string) => void>();
const emit = (eventName: string) => {
  for (const listener of listeners) listener(eventName);
};

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: (listener: (e: string) => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    subscribeState: () => () => {},
    getState: () => "open",
    isAccessEnabled: () => true,
  },
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT:
    "home_assistant_enrichment_updated",
  LIVE_EVENTS: [
    "topology_updated",
    "dashboard_updated",
    "incidents_updated",
    "home_assistant_enrichment_updated",
  ],
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: { topology: { enabled: true } },
    scenario: "",
  }),
}));

const topologyEvidenceGraph = vi.fn();
const devices = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    topologyEvidenceGraph: (...args: unknown[]) => topologyEvidenceGraph(...args),
    devices: (...args: unknown[]) => devices(...args),
  },
  ApiError: class ApiError extends Error {},
}));

import { useTopologyGraphData } from "./useTopologyGraphData";

describe("useTopologyGraphData", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    listeners.clear();
    topologyEvidenceGraph.mockReset();
    devices.mockReset();
    topologyEvidenceGraph.mockResolvedValue(
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: {
          snapshot_id: "snap-1",
          captured_at: "2026-01-01T00:00:00+00:00",
        },
        nodes: [],
        links: [],
        layout_available: false,
      }),
    );
    devices.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("separates topology and device-inventory invalidations", async () => {
    renderHook(() => useTopologyGraphData("home"));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(1);
    expect(devices).toHaveBeenCalledTimes(1);

    act(() => emit("topology_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(2);
    expect(devices).toHaveBeenCalledTimes(1);

    act(() => emit("home_assistant_enrichment_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(3);
    expect(devices).toHaveBeenCalledTimes(2);

    act(() => emit("dashboard_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(3);
    expect(devices).toHaveBeenCalledTimes(3);

    act(() => emit("incidents_updated"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(3);
    expect(devices).toHaveBeenCalledTimes(4);

    act(() => emit("collector_status"));
    act(() => vi.advanceTimersByTime(350));
    await act(async () => {
      await Promise.resolve();
    });
    expect(topologyEvidenceGraph).toHaveBeenCalledTimes(3);
    expect(devices).toHaveBeenCalledTimes(4);
  });
});
