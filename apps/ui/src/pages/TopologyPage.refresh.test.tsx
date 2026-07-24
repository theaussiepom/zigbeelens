import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { TopologyNetworkDetail, TopologyOverview } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import {
  LIMITED_LAYOUT_COPY,
  TopologyPage,
} from "@/pages/TopologyPage";
import {
  RAW_DETAIL_ERROR_GENERIC_COPY,
  RAW_DETAIL_PENDING_COPY,
  RAW_DETAIL_UNKNOWN_COPY,
} from "@/viewModels/topology/topologyRawDetailSnapshotViewModel";

const eventListeners = new Set<(eventName: string) => void>();
const emit = (eventName: string) => {
  for (const listener of eventListeners) listener(eventName);
};

vi.mock("@/lib/events", () => ({
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT:
    "home_assistant_enrichment_updated",
  liveConnection: {
    subscribeEvents: (listener: (e: string) => void) => {
      eventListeners.add(listener);
      return () => {
        eventListeners.delete(listener);
      };
    },
    subscribeState: () => () => {},
    getState: () => "open",
    isAccessEnabled: () => true,
  },
  LIVE_EVENTS: [],
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.1.13",
      topology: { enabled: true },
    },
  }),
}));

const overview: TopologyOverview = {
  enabled: true,
  manual_capture_enabled: false,
  automatic_capture_enabled: false,
  capture_in_progress: false,
  last_capture_error: null,
  networks: [
    {
      network_id: "home",
      network_name: "Home",
      latest_snapshot: {
        snapshot_id: "snap-home",
        status: "complete",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 2,
        link_count: 4,
        end_device_count: 8,
      },
    },
  ],
};

const detailComplete: TopologyNetworkDetail = {
  network_id: "home",
  network_name: "Home",
  latest_snapshot: {
    snapshot_id: "snap-home",
    captured_at: "2026-06-16T02:17:53.509572+00:00",
    requested_by: "startup_scan",
    status: "complete",
    router_count: 2,
    link_count: 4,
    end_device_count: 8,
  },
  nodes: [
    {
      ieee_address: "0xabc",
      friendly_name: "Router hall",
      node_type: "Router",
      lqi: 120,
    },
  ],
  links: [
    {
      source_ieee: "0xabc",
      target_ieee: "0xdef",
      relationship: "Child",
      linkquality: 100,
    },
  ],
  inventory: {
    device_count: 12,
    router_count: 2,
    end_device_count: 8,
  },
  layout_available: true,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/topology/home"]}>
      <Routes>
        <Route path="/topology/:networkId" element={<TopologyPage />} />
        <Route path="/topology" element={<TopologyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TopologyPage raw detail refresh resilience", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    eventListeners.clear();
    vi.spyOn(api, "topology").mockResolvedValue(structuredClone(overview));
    vi.spyOn(api, "topologyNetwork").mockResolvedValue(structuredClone(detailComplete));
    vi.spyOn(api, "captureTopology").mockResolvedValue({
      snapshot_id: "x",
      status: "pending",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("keeps accepted detail when a background refresh fails and retries successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderDetail();

    await waitFor(() => {
      expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Raw snapshot contents"));
    expect(screen.getByText("Router hall")).toBeVisible();

    const refresh = deferred<TopologyNetworkDetail>();
    vi.mocked(api.topologyNetwork).mockReturnValueOnce(refresh.promise);

    act(() => emit("topology_updated"));
    await act(async () => {
      vi.advanceTimersByTime(350);
      await Promise.resolve();
    });

    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Router hall")).toBeVisible();
    expect(screen.queryByTestId("raw-snapshot-refresh-warning")).not.toBeInTheDocument();

    await act(async () => {
      refresh.reject(new ApiError("refresh failed", 503));
      await Promise.resolve();
    });

    expect(screen.getByTestId("raw-snapshot-refresh-warning")).toBeInTheDocument();
    expect(
      screen.getByText(/raw snapshot could not be refreshed\. showing the last loaded data/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Router hall")).toBeVisible();

    vi.mocked(api.topologyNetwork).mockResolvedValueOnce({
      ...structuredClone(detailComplete),
      latest_snapshot: {
        ...detailComplete.latest_snapshot!,
        snapshot_id: "snap-refreshed",
      },
    });

    await user.click(screen.getByRole("button", { name: /^retry$/i }));
    await waitFor(() => {
      expect(screen.queryByTestId("raw-snapshot-refresh-warning")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Router hall")).toBeVisible();
  });

  it("does not refetch raw topology for an enrichment-only invalidation", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    });
    expect(api.topology).toHaveBeenCalledTimes(1);
    expect(api.topologyNetwork).toHaveBeenCalledTimes(1);

    act(() => {
      emit("home_assistant_enrichment_updated");
      emit("dashboard_updated");
    });
    await act(async () => {
      vi.advanceTimersByTime(350);
      await Promise.resolve();
    });

    expect(api.topology).toHaveBeenCalledTimes(1);
    expect(api.topologyNetwork).toHaveBeenCalledTimes(1);
  });
});

describe("TopologyPage raw detail status matrix", () => {
  beforeEach(() => {
    eventListeners.clear();
    vi.spyOn(api, "topology").mockResolvedValue(structuredClone(overview));
    vi.spyOn(api, "captureTopology").mockResolvedValue({
      snapshot_id: "x",
      status: "pending",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    {
      name: "no snapshot",
      detail: {
        ...detailComplete,
        latest_snapshot: null,
        nodes: [],
        links: [],
      },
      label: "diagnostics limited",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: /no topology snapshot is stored/i,
    },
    {
      name: "complete with layout",
      detail: detailComplete,
      label: "Complete",
      expectDisclosure: true,
      expectLimited: false,
      expectTopologyCounts: true,
      copy: /point-in-time snapshot evidence/i,
    },
    {
      name: "complete limited",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          router_count: 0,
          link_count: 0,
          end_device_count: 0,
        },
        nodes: [],
        links: [],
      },
      label: "Complete · layout limited",
      expectDisclosure: false,
      expectLimited: true,
      expectTopologyCounts: true,
      copy: null,
    },
    {
      name: "pending",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          status: "pending",
        },
      },
      label: "Pending",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: RAW_DETAIL_PENDING_COPY,
    },
    {
      name: "error with stored text",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          status: "error",
          error: "bridge timed out",
        },
      },
      label: "Error",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: /bridge timed out/i,
    },
    {
      name: "error without stored text",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          status: "error",
          error: null,
        },
      },
      label: "Error",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: RAW_DETAIL_ERROR_GENERIC_COPY,
    },
    {
      name: "null status",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          status: null,
        },
      },
      label: "Status unknown",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: RAW_DETAIL_UNKNOWN_COPY,
    },
    {
      name: "unknown future status",
      detail: {
        ...detailComplete,
        latest_snapshot: {
          ...detailComplete.latest_snapshot!,
          status: "future_status_v2",
        },
      },
      label: "Status unknown",
      expectDisclosure: false,
      expectLimited: false,
      expectTopologyCounts: false,
      copy: RAW_DETAIL_UNKNOWN_COPY,
    },
  ])(
    "renders $name",
    async ({ detail, label, expectDisclosure, expectLimited, expectTopologyCounts, copy }) => {
      vi.spyOn(api, "topologyNetwork").mockResolvedValue(structuredClone(detail));
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText(label, { exact: true })).toBeInTheDocument();
      });

      if (expectDisclosure) {
        expect(screen.getByText("Raw snapshot contents")).toBeInTheDocument();
      } else {
        expect(screen.queryByText("Raw snapshot contents")).not.toBeInTheDocument();
      }

      if (expectLimited) {
        expect(screen.getByText(LIMITED_LAYOUT_COPY)).toBeInTheDocument();
        expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
      } else {
        expect(screen.queryByText(LIMITED_LAYOUT_COPY)).not.toBeInTheDocument();
      }

      if (expectTopologyCounts) {
        expect(screen.getByText("Topology routers")).toBeInTheDocument();
      } else if (label !== "diagnostics limited") {
        expect(screen.queryByText("Topology routers")).not.toBeInTheDocument();
      }

      // Inventory remains factual when a snapshot row exists.
      if (detail.latest_snapshot && detail.inventory) {
        expect(screen.getByText("Known devices")).toBeInTheDocument();
        expect(screen.getByText(String(detail.inventory.device_count))).toBeInTheDocument();
      }

      if (copy) {
        expect(screen.getByText(copy)).toBeInTheDocument();
      }

      if (label === "Error") {
        const badge = screen.getByText("Error", { exact: true });
        expect(badge.className).toMatch(/critical/i);
      }
      if (label === "Status unknown") {
        expect(screen.queryByText("Complete", { exact: true })).not.toBeInTheDocument();
      }
    },
  );
});

describe("TopologyPage capture action gate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hides capture when topology is disabled even if manual_capture_enabled is true", async () => {
    vi.spyOn(api, "topology").mockResolvedValue({
      ...structuredClone(overview),
      enabled: false,
      manual_capture_enabled: true,
    });
    vi.spyOn(api, "topologyNetwork").mockResolvedValue(structuredClone(detailComplete));

    render(
      <MemoryRouter initialEntries={["/topology"]}>
        <Routes>
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/topology/:networkId" element={<TopologyPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Configured networks")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /capture snapshot/i })).not.toBeInTheDocument();

    const link = screen.getByRole("link", { name: /view snapshot details/i });
    expect(within(link).getByText("Home")).toBeInTheDocument();
  });
});
