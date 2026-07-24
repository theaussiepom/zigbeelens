import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import type { DeviceStoryDto } from "@/types/devices";
import type { DataCoverageDto } from "@/types/decisions";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { NodeDrawer } from "./NodeDrawer";

const apiMocks = vi.hoisted(() => ({
  deviceCoverage: vi.fn(),
  deviceStory: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      ...apiMocks,
    },
  };
});

const story: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0xa1",
  status: "no_notable_change",
  priority: "none",
  headline_code: "no_notable_signals",
  reasons: [],
  evidence: [],
  limitations: [],
  suggested_checks: [],
  coverage: [],
  related_unresolved_incident_ids: [],
  timeline: [],
};

function coverage(areaName: string): DataCoverageDto {
  return {
    dimension: "ha_enrichment",
    state: "available",
    label_code: "ha_area_linked",
    params: { area_name: areaName },
  };
}

function drawerDevice(
  ieeeAddress = "0xa1",
  friendlyName = "Kitchen Router",
  networkId = "home",
): MeshEvidenceDevice {
  return {
    ieee_address: ieeeAddress,
    network_id: networkId,
    friendly_name: friendlyName,
    role: "router",
    power: "mains",
    availability: "online",
    in_inventory: true,
    in_latest_snapshot: true,
    health_bucket: "healthy",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "Observed in the latest topology snapshot.",
    passive_observation_summary: "",
    diagnostic_stats: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function emitRefresh(eventName = HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT) {
  act(() => {
    eventSourceTestState.emit(eventName, { type: eventName });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

function renderDrawer(device = drawerDevice()) {
  return render(
    <MemoryRouter>
      <NodeDrawer device={device} onClose={vi.fn()} />
    </MemoryRouter>,
  );
}

const staleCoverageCopy =
  "Device coverage could not be refreshed. Showing the last accepted view; it may not include the newest Core data or Home Assistant enrichment.";
const staleStoryCopy =
  "Device story could not be refreshed. Showing the last accepted view; it may not include the newest Core data or Home Assistant enrichment.";

describe("NodeDrawer device coverage refresh states", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    for (const mock of Object.values(apiMocks)) mock.mockReset();
    apiMocks.deviceStory.mockResolvedValue(story);
    liveConnection.resetForTests();
    eventSourceTestState.reset();
    liveConnection.setAccessEnabled(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows an initial loading state without claiming coverage is unavailable", () => {
    apiMocks.deviceStory.mockReturnValueOnce(new Promise(() => {}));
    apiMocks.deviceCoverage.mockReturnValue(new Promise(() => {}));
    renderDrawer();

    expect(
      screen.queryByTestId("device-coverage-section"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Retry device coverage" }),
    ).not.toBeInTheDocument();
  });

  it("shows initial failure as unavailable with a contextual retry", async () => {
    apiMocks.deviceCoverage.mockRejectedValue(
      new Error("initial coverage failure"),
    );
    renderDrawer();
    await flushAsyncWork();

    expect(
      screen.getByText("Device coverage is currently unavailable."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry device coverage" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(staleCoverageCopy)).not.toBeInTheDocument();
  });

  it("renders accepted nonempty coverage as loaded", async () => {
    apiMocks.deviceCoverage.mockResolvedValue([coverage("Kitchen")]);
    renderDrawer();
    await flushAsyncWork();

    expect(screen.getByText("HA area: Kitchen")).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
  });

  it("renders accepted empty coverage distinctly from unavailable", async () => {
    apiMocks.deviceCoverage.mockResolvedValue([]);
    renderDrawer();
    await flushAsyncWork();

    expect(
      screen.getByText("No device coverage entries were returned."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
  });

  it("retains accepted coverage while refreshing and across repeated failures, then replaces it after successful retry", async () => {
    const refresh = deferred<DataCoverageDto[]>();
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Accepted Kitchen")])
      .mockReturnValueOnce(refresh.promise)
      .mockRejectedValueOnce(new Error("repeated coverage failure"))
      .mockResolvedValueOnce([coverage("Recovered Kitchen")]);

    renderDrawer();
    await flushAsyncWork();
    await emitRefresh();

    const section = screen.getByTestId("device-coverage-section");
    expect(section).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("HA area: Accepted Kitchen")).toBeInTheDocument();
    expect(screen.queryByText(staleCoverageCopy)).not.toBeInTheDocument();

    await act(async () => {
      refresh.reject(new Error("coverage refresh failure"));
      await Promise.resolve();
    });
    expect(section).toHaveAttribute("aria-busy", "false");
    expect(screen.getByText("HA area: Accepted Kitchen")).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry device coverage" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry device coverage" }),
    );
    await flushAsyncWork();
    expect(screen.getByText("HA area: Accepted Kitchen")).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry device coverage" }),
    );
    await flushAsyncWork();
    expect(screen.getByText("HA area: Recovered Kitchen")).toBeInTheDocument();
    expect(
      screen.queryByText("HA area: Accepted Kitchen"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(staleCoverageCopy)).not.toBeInTheDocument();
  });

  it("retains accepted coverage after an ordinary Dashboard refresh failure", async () => {
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Accepted Kitchen")])
      .mockRejectedValueOnce(new Error("Dashboard coverage failure"));

    renderDrawer();
    await flushAsyncWork();
    await emitRefresh("dashboard_updated");

    expect(apiMocks.deviceCoverage).toHaveBeenCalledTimes(2);
    expect(screen.getByText("HA area: Accepted Kitchen")).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
  });

  it("keeps accepted empty coverage accepted-empty after a refresh error", async () => {
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("empty coverage refresh failure"));

    renderDrawer();
    await flushAsyncWork();
    await emitRefresh();

    expect(
      screen.getByText("No device coverage entries were returned."),
    ).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Retry device coverage" }),
    ).toHaveLength(1);
  });

  it("retains an accepted story and accepted-empty coverage when both refreshes fail", async () => {
    apiMocks.deviceStory
      .mockReset()
      .mockResolvedValueOnce(story)
      .mockRejectedValueOnce(new Error("story refresh failure"));
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("coverage refresh failure"));

    renderDrawer();
    await flushAsyncWork();
    await emitRefresh();

    expect(screen.getByText("No notable signals")).toBeInTheDocument();
    expect(
      screen.getByText("No device coverage entries were returned."),
    ).toBeInTheDocument();
    expect(screen.getByText(staleStoryCopy)).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();
    expect(
      screen.queryByText(/unavailable right now/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
  });

  it("retains accepted coverage when an SSE reconnect reconciliation fails", async () => {
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Accepted Kitchen")])
      .mockRejectedValueOnce(new Error("reconnect coverage failure"));

    renderDrawer();
    await flushAsyncWork();
    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeDefined();

    act(() => {
      source?.onerror?.();
      source?.onopen?.();
    });
    await flushAsyncWork();

    expect(apiMocks.deviceCoverage).toHaveBeenCalledTimes(2);
    expect(screen.getByText("HA area: Accepted Kitchen")).toBeInTheDocument();
    expect(screen.getByText(staleCoverageCopy)).toBeInTheDocument();
    expect(
      screen.queryByText("Device coverage is currently unavailable."),
    ).not.toBeInTheDocument();
  });

  it("masks accepted coverage immediately on device identity change and ignores the obsolete in-flight result", async () => {
    const oldRefresh = deferred<DataCoverageDto[]>();
    const newIdentity = deferred<DataCoverageDto[]>();
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Old Kitchen")])
      .mockReturnValueOnce(oldRefresh.promise)
      .mockReturnValueOnce(newIdentity.promise);

    const firstDevice = drawerDevice();
    const nextDevice = drawerDevice("0xb2", "Hall Router");
    const { rerender } = renderDrawer(firstDevice);
    await flushAsyncWork();
    await emitRefresh();
    expect(screen.getByText("HA area: Old Kitchen")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <NodeDrawer device={nextDevice} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Hall Router")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Open full device details/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("device-coverage-section"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("HA area: Old Kitchen")).not.toBeInTheDocument();
    expect(screen.queryByText(staleCoverageCopy)).not.toBeInTheDocument();

    await act(async () => {
      oldRefresh.resolve([coverage("Obsolete Kitchen")]);
      await Promise.resolve();
    });
    expect(
      screen.queryByText("HA area: Obsolete Kitchen"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("device-coverage-section"),
    ).not.toBeInTheDocument();

    await act(async () => {
      newIdentity.resolve([coverage("Hall")]);
      await Promise.resolve();
    });
    expect(screen.getByText("HA area: Hall")).toBeInTheDocument();
    expect(screen.queryByText("HA area: Old Kitchen")).not.toBeInTheDocument();
  });
});
