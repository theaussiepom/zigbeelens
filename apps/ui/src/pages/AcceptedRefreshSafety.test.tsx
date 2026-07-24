import { act, fireEvent, render, screen } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DashboardPayload,
  DeviceDetail,
  DeviceSummary,
  NetworkSummary,
} from "@zigbeelens/shared";
import {
  makeDashboardPayload,
  makeDecisionBadge,
  makeNetworkSummary,
} from "@/test/decisionFixtures";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { DeviceDetailPage, DevicesPage } from "@/pages/DevicesPage";
import { NetworkDetailPage, NetworksPage } from "@/pages/NetworksPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { InvestigateLandingPage } from "@/pages/InvestigateLandingPage";

const apiMocks = vi.hoisted(() => ({
  dashboard: vi.fn(),
  devices: vi.fn(),
  device: vi.fn(),
  incidents: vi.fn(),
  network: vi.fn(),
  networks: vi.fn(),
  timeline: vi.fn(),
}));

const scenarioState = vi.hoisted(() => ({
  scenario: "",
  status: {
    topology: { enabled: false },
  },
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
    scenario: scenarioState.scenario,
    status: scenarioState.status,
  }),
}));

vi.mock("@/components/reports/ContextualReportDialog", () => ({
  ContextualReportDialog: () => null,
}));

vi.mock("@/components/meshGraph/DeviceStorySection", () => ({
  DeviceStorySection: () => <div>Device story fixture</div>,
}));

vi.mock("@/components/meshGraph/DeviceSnapshotHistory", () => ({
  DeviceSnapshotHistory: () => <div>Snapshot history fixture</div>,
}));

function deviceSummary(
  name: string,
  overrides: Partial<DeviceSummary> = {},
): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "z2m_kitchen_lamp",
    home_assistant_name: name,
    home_assistant_area_name: `${name} Area`,
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-23T01:00:00Z",
    decision: makeDecisionBadge(),
    ...overrides,
  };
}

function deviceDetail(
  name: string,
  overrides: Partial<DeviceDetail> = {},
): DeviceDetail {
  return {
    ...deviceSummary(name),
    last_payload_at: "2026-07-23T01:05:00Z",
    definition: null,
    supported: true,
    recent_availability_changes: [],
    recent_events: [],
    recent_bridge_logs: [],
    diagnostic: {
      classification: "healthy",
      severity: "healthy",
      scope: "device",
      confidence: "high",
      summary: "No current issue.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    trends: [],
    ...overrides,
  };
}

function network(name: string): NetworkSummary {
  return makeNetworkSummary({
    id: "home",
    name,
    base_topic: `zigbee2mqtt/${name.toLowerCase().replaceAll(" ", "-")}`,
    device_count: 1,
    decision: makeDecisionBadge(),
  });
}

function dashboard(name: string): DashboardPayload {
  return makeDashboardPayload({
    generated_at: "2026-07-23T02:00:00+00:00",
    networks: [network(name)],
  });
}

function devicesElement() {
  return (
    <MemoryRouter>
      <DevicesPage />
    </MemoryRouter>
  );
}

function deviceDetailElement() {
  return (
    <MemoryRouter initialEntries={["/devices/home/0xa1"]}>
      <Routes>
        <Route
          path="/devices/:networkId/:ieeeAddress"
          element={<DeviceDetailPage />}
        />
      </Routes>
    </MemoryRouter>
  );
}

function overviewElement() {
  return (
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>
  );
}

function networksElement() {
  return (
    <MemoryRouter>
      <NetworksPage />
    </MemoryRouter>
  );
}

function investigateElement() {
  return (
    <MemoryRouter>
      <InvestigateLandingPage />
    </MemoryRouter>
  );
}

function networkDetailElement() {
  return (
    <MemoryRouter initialEntries={["/networks/home"]}>
      <Routes>
        <Route path="/networks/:networkId" element={<NetworkDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

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

function staleCopy(resourceLabel: string): string {
  return `${resourceLabel} could not be refreshed. Showing the last accepted view; it may not include the newest Home Assistant enrichment.`;
}

function defaultApiResponses() {
  apiMocks.dashboard.mockResolvedValue(dashboard("Accepted Overview Network"));
  apiMocks.devices.mockResolvedValue({
    items: [deviceSummary("Accepted Device")],
    total: 1,
  });
  apiMocks.device.mockResolvedValue(deviceDetail("Accepted Device Detail"));
  apiMocks.incidents.mockResolvedValue({ items: [], total: 0 });
  apiMocks.network.mockResolvedValue(network("Accepted Network Detail"));
  apiMocks.networks.mockResolvedValue({
    items: [network("Accepted Network Summary")],
    total: 1,
  });
  apiMocks.timeline.mockResolvedValue({ items: [], total: 0 });
}

beforeEach(() => {
  vi.useFakeTimers();
  for (const mock of Object.values(apiMocks)) mock.mockReset();
  scenarioState.scenario = "";
  defaultApiResponses();
  liveConnection.resetForTests();
  eventSourceTestState.reset();
  liveConnection.setAccessEnabled(true);
});

afterEach(() => {
  vi.useRealTimers();
});

type SurfaceCase = {
  name: string;
  element: () => ReactElement;
  configureInitialFailure: () => void;
  configureRefreshSequence: () => void;
  initialAcceptedText: string;
  refreshedText: string;
  resourceLabel: string;
  retryLabel: string;
};

const surfaces: SurfaceCase[] = [
  {
    name: "Devices",
    element: devicesElement,
    configureInitialFailure: () => {
      apiMocks.devices.mockReset().mockRejectedValue(new Error("Devices initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.devices
        .mockReset()
        .mockResolvedValueOnce({ items: [deviceSummary("Accepted Devices Name")], total: 1 })
        .mockRejectedValueOnce(new Error("Devices refresh failure"))
        .mockResolvedValueOnce({ items: [deviceSummary("Refreshed Devices Name")], total: 1 });
    },
    initialAcceptedText: "Accepted Devices Name",
    refreshedText: "Refreshed Devices Name",
    resourceLabel: "Device inventory",
    retryLabel: "Retry device inventory",
  },
  {
    name: "Device Detail",
    element: deviceDetailElement,
    configureInitialFailure: () => {
      apiMocks.device.mockReset().mockRejectedValue(new Error("Device Detail initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.device
        .mockReset()
        .mockResolvedValueOnce(deviceDetail("Accepted Detail Name"))
        .mockRejectedValueOnce(new Error("Device Detail refresh failure"))
        .mockResolvedValueOnce(deviceDetail("Refreshed Detail Name"));
    },
    initialAcceptedText: "Accepted Detail Name",
    refreshedText: "Refreshed Detail Name",
    resourceLabel: "Device details",
    retryLabel: "Retry device details",
  },
  {
    name: "Overview",
    element: overviewElement,
    configureInitialFailure: () => {
      apiMocks.dashboard.mockReset().mockRejectedValue(new Error("Overview initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.dashboard
        .mockReset()
        .mockResolvedValueOnce(dashboard("Accepted Overview Name"))
        .mockRejectedValueOnce(new Error("Overview refresh failure"))
        .mockResolvedValueOnce(dashboard("Refreshed Overview Name"));
    },
    initialAcceptedText: "Accepted Overview Name",
    refreshedText: "Refreshed Overview Name",
    resourceLabel: "Overview",
    retryLabel: "Retry Overview",
  },
  {
    name: "Networks",
    element: networksElement,
    configureInitialFailure: () => {
      apiMocks.networks.mockReset().mockRejectedValue(new Error("Networks initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.networks
        .mockReset()
        .mockResolvedValueOnce({ items: [network("Accepted Networks Name")], total: 1 })
        .mockRejectedValueOnce(new Error("Networks refresh failure"))
        .mockResolvedValueOnce({ items: [network("Refreshed Networks Name")], total: 1 });
    },
    initialAcceptedText: "Accepted Networks Name",
    refreshedText: "Refreshed Networks Name",
    resourceLabel: "Network summaries",
    retryLabel: "Retry network summaries",
  },
  {
    name: "Network Detail",
    element: networkDetailElement,
    configureInitialFailure: () => {
      apiMocks.network.mockReset().mockRejectedValue(new Error("Network Detail initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.network
        .mockReset()
        .mockResolvedValueOnce(network("Accepted Network Detail Name"))
        .mockRejectedValueOnce(new Error("Network Detail refresh failure"))
        .mockResolvedValueOnce(network("Refreshed Network Detail Name"));
    },
    initialAcceptedText: "Accepted Network Detail Name",
    refreshedText: "Refreshed Network Detail Name",
    resourceLabel: "Network details",
    retryLabel: "Retry network details",
  },
  {
    name: "Investigate",
    element: investigateElement,
    configureInitialFailure: () => {
      apiMocks.networks
        .mockReset()
        .mockRejectedValue(new Error("Investigate initial failure"));
    },
    configureRefreshSequence: () => {
      apiMocks.networks
        .mockReset()
        .mockResolvedValueOnce({
          items: [network("Accepted Investigate Name")],
          total: 1,
        })
        .mockRejectedValueOnce(new Error("Investigate refresh failure"))
        .mockResolvedValueOnce({
          items: [network("Refreshed Investigate Name")],
          total: 1,
        });
    },
    initialAcceptedText: "Accepted Investigate Name",
    refreshedText: "Refreshed Investigate Name",
    resourceLabel: "Investigation networks",
    retryLabel: "Retry investigation networks",
  },
];

describe("accepted page data refresh safety", () => {
  it.each(surfaces)(
    "$name uses a full error only when no data has been accepted",
    async ({ element, configureInitialFailure, initialAcceptedText, retryLabel }) => {
      configureInitialFailure();
      render(element());
      await flushAsyncWork();

      expect(screen.getByText(/initial failure/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: retryLabel })).toBeInTheDocument();
      expect(screen.queryAllByText(initialAcceptedText)).toHaveLength(0);
      expect(screen.queryByText(/showing the last accepted view/i)).not.toBeInTheDocument();
    },
  );

  it.each(surfaces)(
    "$name retains accepted data after refresh failure and replaces it after Retry",
    async ({
      element,
      configureRefreshSequence,
      initialAcceptedText,
      refreshedText,
      resourceLabel,
      retryLabel,
    }) => {
      configureRefreshSequence();
      render(element());
      await flushAsyncWork();
      expect(screen.getAllByText(initialAcceptedText).length).toBeGreaterThan(0);

      await emitEnrichmentUpdate();

      expect(screen.getAllByText(initialAcceptedText).length).toBeGreaterThan(0);
      expect(screen.queryAllByText(refreshedText)).toHaveLength(0);
      expect(screen.getByText(staleCopy(resourceLabel))).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: retryLabel }));
      await flushAsyncWork();

      expect(screen.getAllByText(refreshedText).length).toBeGreaterThan(0);
      expect(screen.queryAllByText(initialAcceptedText)).toHaveLength(0);
      expect(screen.queryByText(staleCopy(resourceLabel))).not.toBeInTheDocument();
    },
  );

  it("Network Detail qualifies retained device cards when its inventory refresh fails", async () => {
    const reviewDecision = makeDecisionBadge({
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
    });
    apiMocks.devices
      .mockReset()
      .mockResolvedValueOnce({
        items: [
          deviceSummary("Accepted Network Device", {
            decision: reviewDecision,
            friendly_name: "accepted_network_device",
          }),
        ],
        total: 1,
      })
      .mockRejectedValueOnce(new Error("Network inventory refresh failure"))
      .mockResolvedValueOnce({
        items: [
          deviceSummary("Refreshed Network Device", {
            decision: reviewDecision,
            friendly_name: "refreshed_network_device",
          }),
        ],
        total: 1,
      });

    render(networkDetailElement());
    await flushAsyncWork();
    expect(screen.getByText("accepted_network_device")).toBeInTheDocument();

    await emitEnrichmentUpdate();

    expect(screen.getByText("accepted_network_device")).toBeInTheDocument();
    expect(
      screen.getByText(staleCopy("Network device inventory")),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry network device inventory" }),
    );
    await flushAsyncWork();

    expect(screen.getByText("refreshed_network_device")).toBeInTheDocument();
    expect(screen.queryByText("accepted_network_device")).not.toBeInTheDocument();
    expect(
      screen.queryByText(staleCopy("Network device inventory")),
    ).not.toBeInTheDocument();
  });
});

type BoundaryCase = {
  name: string;
  element: () => ReactElement;
  configure: (
    setResolveNext: (resolve: (value: unknown) => void) => void,
  ) => void;
  acceptedText: string;
  nextText: string;
  nextValue: unknown;
};

const boundaries: BoundaryCase[] = [
  {
    name: "Devices scenario",
    element: devicesElement,
    configure: (setResolveNext) => {
      apiMocks.devices.mockReset().mockImplementation((scenario?: string) => {
        if (scenario === "scenario-b") {
          return new Promise((resolve) => setResolveNext(resolve));
        }
        return Promise.resolve({ items: [deviceSummary("Scenario A Device")], total: 1 });
      });
    },
    acceptedText: "Scenario A Device",
    nextText: "Scenario B Device",
    nextValue: { items: [deviceSummary("Scenario B Device")], total: 1 },
  },
  {
    name: "Device Detail scenario",
    element: deviceDetailElement,
    configure: (setResolveNext) => {
      apiMocks.device.mockReset().mockImplementation(
        (_networkId: string, _ieee: string, scenario?: string) => {
          if (scenario === "scenario-b") {
            return new Promise((resolve) => setResolveNext(resolve));
          }
          return Promise.resolve(deviceDetail("Scenario A Detail"));
        },
      );
    },
    acceptedText: "Scenario A Detail",
    nextText: "Scenario B Detail",
    nextValue: deviceDetail("Scenario B Detail"),
  },
  {
    name: "Overview scenario",
    element: overviewElement,
    configure: (setResolveNext) => {
      apiMocks.dashboard.mockReset().mockImplementation((scenario?: string) => {
        if (scenario === "scenario-b") {
          return new Promise((resolve) => setResolveNext(resolve));
        }
        return Promise.resolve(dashboard("Scenario A Overview"));
      });
    },
    acceptedText: "Scenario A Overview",
    nextText: "Scenario B Overview",
    nextValue: dashboard("Scenario B Overview"),
  },
  {
    name: "Networks scenario",
    element: networksElement,
    configure: (setResolveNext) => {
      apiMocks.networks.mockReset().mockImplementation((scenario?: string) => {
        if (scenario === "scenario-b") {
          return new Promise((resolve) => setResolveNext(resolve));
        }
        return Promise.resolve({ items: [network("Scenario A Network")], total: 1 });
      });
    },
    acceptedText: "Scenario A Network",
    nextText: "Scenario B Network",
    nextValue: { items: [network("Scenario B Network")], total: 1 },
  },
  {
    name: "Network Detail scenario",
    element: networkDetailElement,
    configure: (setResolveNext) => {
      apiMocks.network.mockReset().mockImplementation(
        (_networkId: string, scenario?: string) => {
          if (scenario === "scenario-b") {
            return new Promise((resolve) => setResolveNext(resolve));
          }
          return Promise.resolve(network("Scenario A Network Detail"));
        },
      );
    },
    acceptedText: "Scenario A Network Detail",
    nextText: "Scenario B Network Detail",
    nextValue: network("Scenario B Network Detail"),
  },
  {
    name: "Investigate scenario",
    element: investigateElement,
    configure: (setResolveNext) => {
      apiMocks.networks.mockReset().mockImplementation((scenario?: string) => {
        if (scenario === "scenario-b") {
          return new Promise((resolve) => setResolveNext(resolve));
        }
        return Promise.resolve({
          items: [network("Scenario A Investigate")],
          total: 1,
        });
      });
    },
    acceptedText: "Scenario A Investigate",
    nextText: "Scenario B Investigate",
    nextValue: {
      items: [network("Scenario B Investigate")],
      total: 1,
    },
  },
];

describe("page identity boundaries", () => {
  it.each(boundaries)(
    "$name does not render accepted data from the previous scope",
    async ({ element, configure, acceptedText, nextText, nextValue }) => {
      let resolveNext: ((value: unknown) => void) | undefined;
      configure((resolve) => {
        resolveNext = resolve;
      });
      const view = render(element());
      await flushAsyncWork();
      expect(screen.getAllByText(acceptedText).length).toBeGreaterThan(0);

      scenarioState.scenario = "scenario-b";
      view.rerender(element());

      expect(screen.queryAllByText(acceptedText)).toHaveLength(0);
      expect(screen.queryAllByText(nextText)).toHaveLength(0);
      expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

      await act(async () => {
        resolveNext?.(nextValue);
        await Promise.resolve();
      });
      expect(screen.getAllByText(nextText).length).toBeGreaterThan(0);
      expect(screen.queryAllByText(acceptedText)).toHaveLength(0);
    },
  );

  it("Device Detail does not carry accepted facts across a device route change", async () => {
    let resolveNext: ((value: DeviceDetail) => void) | undefined;
    apiMocks.device.mockReset().mockImplementation(
      (networkId: string, ieeeAddress: string) => {
        if (networkId === "other" && ieeeAddress === "0xb2") {
          return new Promise((resolve) => {
            resolveNext = resolve;
          });
        }
        return Promise.resolve(deviceDetail("Route A Device"));
      },
    );

    render(
      <MemoryRouter initialEntries={["/devices/home/0xa1"]}>
        <Link to="/devices/other/0xb2">Change device route</Link>
        <Routes>
          <Route
            path="/devices/:networkId/:ieeeAddress"
            element={<DeviceDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getAllByText("Route A Device").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("link", { name: "Change device route" }));
    expect(screen.queryAllByText("Route A Device")).toHaveLength(0);
    expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

    await act(async () => {
      resolveNext?.(
        deviceDetail("Route B Device", {
          network_id: "other",
          ieee_address: "0xb2",
        }),
      );
      await Promise.resolve();
    });
    expect(screen.getAllByText("Route B Device").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Route A Device")).toHaveLength(0);
  });
});
