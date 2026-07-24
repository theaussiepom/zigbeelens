import { act, fireEvent, render, screen } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import type { DeviceStoryDto } from "@/types/devices";
import type { DataCoverageDto } from "@/types/decisions";
import { makeDecisionBadge } from "@/test/decisionFixtures";
import { makeTopologyEvidenceGraphDetail } from "@/test/topologyEvidenceGraphFixture";
import { mockReactFlow } from "@/test/mockReactFlow";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { NodeDrawer } from "@/components/meshGraph/NodeDrawer";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";

const apiMocks = vi.hoisted(() => ({
  topologyEvidenceGraph: vi.fn(),
  devices: vi.fn(),
  deviceCoverage: vi.fn(),
  deviceStory: vi.fn(),
  topology: vi.fn(),
  topologyNetwork: vi.fn(),
  topologyDeviceSnapshotHistory: vi.fn(),
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

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: {
      version: "0.1.14",
      topology: { enabled: true },
    },
  }),
}));

beforeAll(() => {
  mockReactFlow();
});

function summary(
  homeAssistantName: string | null,
): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "z2m_kitchen_router",
    home_assistant_name: homeAssistantName,
    device_type: "Router",
    power_source: "Mains",
    availability: "online",
    last_seen: "2026-07-23T01:00:00+00:00",
    interview_state: "successful",
    incident_affected: false,
    decision: makeDecisionBadge(),
  };
}

function graphDetail(hasAreaCoverageWarning: boolean) {
  return makeTopologyEvidenceGraphDetail({
    network_id: "home",
    network_name: "Home",
    latest_snapshot: {
      snapshot_id: "snapshot-1",
      network_id: "home",
      captured_at: "2026-07-23T01:00:00+00:00",
      requested_by: "startup_scan",
      status: "complete",
      router_count: 1,
      end_device_count: 0,
      link_count: 0,
    },
    nodes: [
      {
        ieee_address: "0xa1",
        friendly_name: "z2m_kitchen_router",
        node_type: "Router",
      },
    ],
    links: [],
    inventory: {
      device_count: 1,
      router_count: 1,
      end_device_count: 0,
    },
    layout_available: true,
    topology_facts: {
      stale_threshold_hours: null,
      network_facts: [],
      coverage: hasAreaCoverageWarning
        ? [
            {
              dimension: "ha_enrichment",
              state: "not_configured",
              label_code: "ha_areas_not_linked",
              params: {},
            },
          ]
        : [],
    },
  });
}

function graphDetailForNetwork(
  networkId: string,
  networkName: string,
  deviceName: string,
) {
  const detail = graphDetail(false);
  return {
    ...detail,
    network_id: networkId,
    network_name: networkName,
    latest_snapshot: {
      ...detail.latest_snapshot,
      network_id: networkId,
      snapshot_id: `snapshot-${networkId}`,
    },
    nodes: [
      {
        ...detail.nodes[0],
        friendly_name: deviceName,
      },
    ],
  };
}

function story(areaName: string | null): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: "0xa1",
    status: "no_notable_change",
    priority: "none",
    headline_code: "no_notable_signals",
    reasons: [],
    evidence: [],
    limitations: [],
    suggested_checks: [],
    coverage: [coverage(areaName)],
    related_unresolved_incident_ids: [],
    timeline: [],
  };
}

function coverage(areaName: string | null): DataCoverageDto {
  return areaName
    ? {
        dimension: "ha_enrichment",
        state: "available",
        label_code: "ha_area_linked",
        params: { area_name: areaName },
      }
    : {
        dimension: "ha_enrichment",
        state: "not_configured",
        label_code: "ha_areas_not_linked",
        params: {},
      };
}

const drawerDevice: MeshEvidenceDevice = {
  ieee_address: "0xa1",
  network_id: "home",
  friendly_name: "Kitchen Router",
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

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function emitEnrichmentUpdate() {
  act(() => {
    eventSourceTestState.emit(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT, {
      type: HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    });
    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

async function emitOrdinaryDashboardUpdate() {
  act(() => {
    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

beforeEach(() => {
  vi.useFakeTimers();
  for (const mock of Object.values(apiMocks)) mock.mockReset();
  localStorage.clear();
  liveConnection.resetForTests();
  eventSourceTestState.reset();
  liveConnection.setAccessEnabled(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Mesh Home Assistant enrichment live refresh", () => {
  it("uses a full error only when no evidence graph has been accepted", async () => {
    apiMocks.topologyEvidenceGraph.mockRejectedValue(
      new Error("Mesh evidence initial failure"),
    );
    apiMocks.devices.mockResolvedValue({ items: [summary("Accepted Mesh Device")] });

    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={<TopologyGraphPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();

    expect(screen.getByText(/Mesh evidence initial failure/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry Mesh evidence graph" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Accepted Mesh Device")).not.toBeInTheDocument();
    expect(screen.queryByText(/showing the last accepted view/i)).not.toBeInTheDocument();
  });

  it("keeps the accepted graph after a failed refresh and updates it after Retry", async () => {
    apiMocks.topologyEvidenceGraph
      .mockResolvedValueOnce(graphDetail(true))
      .mockRejectedValueOnce(new Error("Mesh evidence refresh failure"))
      .mockResolvedValueOnce(graphDetail(false));
    apiMocks.devices.mockResolvedValue({
      items: [summary("Accepted Mesh Device")],
    });

    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={<TopologyGraphPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Accepted Mesh Device")).toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();

    await emitEnrichmentUpdate();

    expect(screen.getByText("Accepted Mesh Device")).toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Mesh evidence graph could not be refreshed. Showing the last accepted view; it may not include newer topology evidence, Core data, or Home Assistant enrichment.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry Mesh evidence graph" }),
    );
    await flushAsyncWork();

    expect(screen.getByText("Accepted Mesh Device")).toBeInTheDocument();
    expect(screen.queryByText("HA areas not linked")).not.toBeInTheDocument();
    expect(screen.queryByText(/Mesh evidence graph could not be refreshed/i)).not.toBeInTheDocument();
  });

  it("does not carry an accepted graph across a network route boundary", async () => {
    let resolveNext:
      | ((value: ReturnType<typeof graphDetailForNetwork>) => void)
      | undefined;
    apiMocks.topologyEvidenceGraph.mockImplementation((networkId: string) => {
      if (networkId === "other") {
        return new Promise((resolve) => {
          resolveNext = resolve;
        });
      }
      return Promise.resolve(
        graphDetailForNetwork("home", "Home", "Home Network Device"),
      );
    });
    apiMocks.devices.mockResolvedValue({ items: [] });

    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Link to="/investigate/other">Change Mesh network</Link>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={<TopologyGraphPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Home Network Device")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Change Mesh network" }));
    expect(screen.queryByText("Home Network Device")).not.toBeInTheDocument();
    expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

    await act(async () => {
      resolveNext?.(
        graphDetailForNetwork("other", "Other", "Other Network Device"),
      );
      await Promise.resolve();
    });
    expect(screen.getByText("Other Network Device")).toBeInTheDocument();
    expect(screen.queryByText("Home Network Device")).not.toBeInTheDocument();
  });

  it("refreshes evidence and inventory names in place, including removal fallback", async () => {
    apiMocks.topologyEvidenceGraph
      .mockResolvedValueOnce(graphDetail(true))
      .mockResolvedValueOnce(graphDetail(false))
      .mockResolvedValueOnce(graphDetail(true));
    apiMocks.devices
      .mockResolvedValueOnce({ items: [summary("Old Kitchen Router")] })
      .mockResolvedValueOnce({ items: [summary("Kitchen Router")] })
      .mockResolvedValueOnce({ items: [summary(null)] });

    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={<TopologyGraphPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Old Kitchen Router")).toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("Kitchen Router")).toBeInTheDocument();
    expect(screen.queryByText("HA areas not linked")).not.toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("z2m_kitchen_router")).toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();
    expect(apiMocks.topologyEvidenceGraph).toHaveBeenCalledTimes(3);
    expect(apiMocks.devices).toHaveBeenCalledTimes(3);
    expect(apiMocks.topology).not.toHaveBeenCalled();
    expect(apiMocks.topologyNetwork).not.toHaveBeenCalled();
    expect(apiMocks.topologyDeviceSnapshotHistory).not.toHaveBeenCalled();
  });

  it("refreshes Mesh evidence and inventory for an ordinary unattributed Dashboard fallback", async () => {
    apiMocks.topologyEvidenceGraph
      .mockResolvedValueOnce(graphDetail(false))
      .mockResolvedValueOnce(graphDetail(true));
    apiMocks.devices
      .mockResolvedValueOnce({ items: [summary("Accepted Mesh Device")] })
      .mockResolvedValueOnce({ items: [summary("Ordinary Mesh Device Update")] });

    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route
            path="/investigate/:networkId"
            element={<TopologyGraphPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Accepted Mesh Device")).toBeInTheDocument();

    await emitOrdinaryDashboardUpdate();

    expect(screen.getByText("Ordinary Mesh Device Update")).toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();
    expect(apiMocks.devices).toHaveBeenCalledTimes(2);
    expect(apiMocks.topologyEvidenceGraph).toHaveBeenCalledTimes(2);
    expect(apiMocks.topology).not.toHaveBeenCalled();
    expect(apiMocks.topologyNetwork).not.toHaveBeenCalled();
    expect(apiMocks.topologyDeviceSnapshotHistory).not.toHaveBeenCalled();
  });

  it("refreshes an open Mesh drawer's Device Story and device coverage", async () => {
    apiMocks.deviceStory
      .mockResolvedValueOnce(story("Old Kitchen"))
      .mockResolvedValueOnce(story("Kitchen"))
      .mockResolvedValueOnce(story(null));
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Old Kitchen")])
      .mockResolvedValueOnce([coverage("Kitchen")])
      .mockResolvedValueOnce([coverage(null)]);

    render(
      <MemoryRouter>
        <NodeDrawer device={drawerDevice} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("HA area: linked")).toBeInTheDocument();
    expect(screen.getByText("HA area: Old Kitchen")).toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("HA area: linked")).toBeInTheDocument();
    expect(screen.getByText("HA area: Kitchen")).toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();
    expect(screen.getByText("HA area: missing")).toBeInTheDocument();
    expect(apiMocks.deviceStory).toHaveBeenCalledTimes(3);
    expect(apiMocks.deviceCoverage).toHaveBeenCalledTimes(3);
    expect(apiMocks.topologyDeviceSnapshotHistory).not.toHaveBeenCalled();
  });

  it("refreshes an open Mesh drawer from an unattributed Dashboard fallback", async () => {
    apiMocks.deviceStory
      .mockResolvedValueOnce(story("Old Kitchen"))
      .mockResolvedValueOnce(story("Fallback Kitchen"));
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Old Kitchen")])
      .mockResolvedValueOnce([coverage("Fallback Kitchen")]);

    render(
      <MemoryRouter>
        <NodeDrawer device={drawerDevice} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("HA area: Old Kitchen")).toBeInTheDocument();

    await emitOrdinaryDashboardUpdate();

    expect(screen.getByText("HA area: Fallback Kitchen")).toBeInTheDocument();
    expect(apiMocks.deviceStory).toHaveBeenCalledTimes(2);
    expect(apiMocks.deviceCoverage).toHaveBeenCalledTimes(2);
    expect(apiMocks.topologyDeviceSnapshotHistory).not.toHaveBeenCalled();
  });

  it("does not present retained HA coverage as current when the live refetch fails", async () => {
    apiMocks.deviceStory
      .mockResolvedValueOnce(story("Old Kitchen"))
      .mockRejectedValueOnce(new Error("injected story refresh failure"))
      .mockResolvedValueOnce(story("Recovered Kitchen"));
    apiMocks.deviceCoverage
      .mockResolvedValueOnce([coverage("Old Kitchen")])
      .mockRejectedValueOnce(new Error("injected coverage refresh failure"))
      .mockResolvedValueOnce([coverage("Recovered Kitchen")]);

    render(
      <MemoryRouter>
        <NodeDrawer device={drawerDevice} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("HA area: Old Kitchen")).toBeInTheDocument();

    await emitEnrichmentUpdate();

    expect(
      screen.getByText(
        "Device story is unavailable right now. Other device details still reflect stored evidence.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Device coverage is currently unavailable."),
    ).toBeInTheDocument();
    expect(screen.queryByText("HA area: Old Kitchen")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry device story" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry device coverage" }));
    await flushAsyncWork();

    expect(screen.getByText("HA area: Recovered Kitchen")).toBeInTheDocument();
    expect(apiMocks.deviceStory).toHaveBeenCalledTimes(3);
    expect(apiMocks.deviceCoverage).toHaveBeenCalledTimes(3);
  });
});
