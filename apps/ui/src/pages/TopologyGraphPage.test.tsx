import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";
import { meshEvidenceGraphFixture } from "@/fixtures/meshEvidenceGraph";
import type { TopologyNetworkDetail } from "@/lib/api";
import { EVIDENCE_CLASSES, evidenceClassLabel, GRAPH_SAFETY_COPY } from "@/lib/meshEvidence";
import { mockReactFlow } from "@/test/mockReactFlow";

beforeAll(() => {
  mockReactFlow();
});

function makeDevice(overrides: Partial<DeviceSummary>): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0x0000000000000000",
    friendly_name: "Device",
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    last_seen: "2026-07-06T01:00:00+00:00",
    interview_state: "successful",
    health: {
      primary: "healthy",
      severity: "healthy",
      confidence: "high",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    incident_affected: false,
    sort_priority: 0,
    lens_bucket: "healthy",
    lens_bucket_label: "Healthy",
    lens_bucket_reason: "Reporting normally on its expected cadence.",
    lens_reasons: [],
    ...overrides,
  };
}

const liveDevices: DeviceSummary[] = [
  makeDevice({
    ieee_address: "0xc0",
    friendly_name: "Live Coordinator",
    device_type: "Coordinator",
  }),
  makeDevice({
    ieee_address: "0xr1",
    friendly_name: "Live Hall Router",
    device_type: "Router",
    last_seen: "2026-07-06T01:30:00+00:00",
  }),
  makeDevice({
    ieee_address: "0xe1",
    friendly_name: "Live Lamp",
    device_type: "EndDevice",
  }),
  makeDevice({
    ieee_address: "0xe2",
    friendly_name: "Live Sleepy Sensor",
    device_type: "EndDevice",
    power_source: "Battery",
  }),
];

const liveDetailHome: TopologyNetworkDetail = {
  network_id: "home",
  network_name: "Home",
  latest_snapshot: {
    snapshot_id: "snap-live",
    network_id: "home",
    captured_at: "2026-07-06T00:30:00+00:00",
    requested_by: "startup_scan",
    status: "complete",
    router_count: 1,
    end_device_count: 1,
    link_count: 3,
  },
  nodes: [
    { ieee_address: "0xc0", friendly_name: "Live Coordinator", node_type: "Coordinator" },
    { ieee_address: "0xr1", friendly_name: "Live Hall Router", node_type: "Router", lqi: 150 },
    { ieee_address: "0xe1", friendly_name: "Live Lamp", node_type: "EndDevice", lqi: 90 },
  ],
  links: [
    {
      source_ieee: "0xr1",
      target_ieee: "0xc0",
      linkquality: 140,
      relationship: "Parent",
      route_count: 2,
    },
    // Reverse direction of the same pair: must merge into one neighbour edge.
    {
      source_ieee: "0xc0",
      target_ieee: "0xr1",
      linkquality: 150,
      relationship: "Child",
      route_count: null,
    },
    // Routes genuinely observed as empty: neighbour evidence only, no route edge.
    {
      source_ieee: "0xr1",
      target_ieee: "0xe1",
      linkquality: 90,
      relationship: "Child",
      route_count: 0,
    },
  ],
  inventory: { device_count: 4, router_count: 1, end_device_count: 2 },
  layout_available: true,
};

const liveDetailLimited: TopologyNetworkDetail = {
  network_id: "home2",
  network_name: "Home 2",
  latest_snapshot: {
    snapshot_id: "snap-limited",
    network_id: "home2",
    captured_at: "2026-07-06T00:15:00+00:00",
    requested_by: "startup_scan",
    status: "complete",
    router_count: 0,
    end_device_count: 0,
    link_count: 0,
  },
  nodes: [],
  links: [],
  inventory: { device_count: 102, router_count: 14, end_device_count: 88 },
  layout_available: false,
};

// Same snapshot, but the link table references an endpoint that appears in
// neither the node list nor the inventory (seen on real networks).
const liveDetailWithGhostEndpoint: TopologyNetworkDetail = {
  ...liveDetailHome,
  links: [
    ...liveDetailHome.links!,
    {
      source_ieee: "0xr1",
      target_ieee: "0xghost",
      linkquality: 60,
      relationship: "Sibling",
      route_count: null,
    },
  ],
};

let mockDetail: TopologyNetworkDetail | null = liveDetailHome;
let mockDevices: DeviceSummary[] = liveDevices;
let mockLayoutFailure: Error | null = null;

vi.mock("@/lib/meshGraphLayout", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/meshGraphLayout")>();
  return {
    ...actual,
    layoutMeshGraph: (...args: Parameters<typeof actual.layoutMeshGraph>) =>
      mockLayoutFailure
        ? Promise.reject(mockLayoutFailure)
        : actual.layoutMeshGraph(...args),
  };
});

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: { version: "0.1.13", topology: { enabled: true } },
  }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (
    _fetcher: () => Promise<unknown>,
    deps: unknown[],
    options?: { enabled?: boolean },
  ) => {
    if (options?.enabled === false) {
      return { data: null, loading: false, error: null, refetch: vi.fn() };
    }
    if (deps.length === 2) {
      return { data: { items: mockDevices, total: mockDevices.length }, loading: false, error: null, refetch: vi.fn() };
    }
    return { data: mockDetail, loading: false, error: null, refetch: vi.fn() };
  },
}));

beforeEach(() => {
  mockDetail = liveDetailHome;
  mockDevices = liveDevices;
  mockLayoutFailure = null;
});

function renderGraphPage(networkId = "home") {
  return render(
    <MemoryRouter initialEntries={[`/topology/${networkId}/graph`]}>
      <Routes>
        <Route path="/topology/:networkId/graph" element={<TopologyGraphPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function renderLiveAndWaitForLayout(networkId = "home") {
  const result = renderGraphPage(networkId);
  await screen.findByText("Live Hall Router");
  return result;
}

async function switchToSample(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByRole("combobox", { name: /data source/i }), "sample");
  await screen.findByText("Living room plug");
}

describe("TopologyGraphPage live mode", () => {
  it("defaults to live snapshot data and labels it as live", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByTestId("graph-mode-badge")).toHaveTextContent("Live topology snapshot");
    expect(screen.queryByText("Prototype — sample data")).not.toBeInTheDocument();
    expect(screen.getByText("Snapshot status")).toBeInTheDocument();
    expect(screen.getByText("Captured")).toBeInTheDocument();
  });

  it("renders live devices and never fixture devices in live mode", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByText("Live Coordinator")).toBeInTheDocument();
    expect(screen.getByText("Live Lamp")).toBeInTheDocument();
    expect(screen.getByText("Live Sleepy Sensor")).toBeInTheDocument();
    // Scope to node title elements: role labels like "Coordinator" legitimately
    // appear on live nodes and would collide with fixture device names.
    for (const fixtureDevice of meshEvidenceGraphFixture.devices) {
      expect(
        screen.queryByText(fixtureDevice.friendly_name, { selector: ".truncate" }),
      ).not.toBeInTheDocument();
    }
  });

  it("maps neighbour links to latest_snapshot_neighbor edges, merging directions", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(2);
    });
  });

  it("creates route edges only where real route-table evidence exists", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    await waitFor(() => {
      // Only 0xr1 → 0xc0 carried route-table entries; 0xr1 → 0xe1 observed
      // zero routes and the reverse direction reported none.
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);
    });
  });

  it("never generates historical, passive or stale edges from live data", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length).toBeGreaterThan(0);
    });
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(0);
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(0);
    expect(container.querySelectorAll(".mesh-edge--stale_low_confidence")).toHaveLength(0);
  });

  it("disables non-live evidence filters in live mode", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByRole("checkbox", { name: /historical evidence/i })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /stale \/ low-confidence/i })).toBeDisabled();
    expect(
      screen.getByText(/are not produced from live snapshot data yet/i),
    ).toBeInTheDocument();
  });

  it("opens the neighbour edge drawer with snapshot facts and safe wording", async () => {
    await renderLiveAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Latest snapshot neighbour evidence between Live Hall Router and Live Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Latest snapshot neighbour evidence")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText(
        /this link was reported in the latest topology snapshot/i,
      ),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("Captured at")).toBeInTheDocument();
    expect(within(drawer).getByText("Observed relationship")).toBeInTheDocument();
    expect(within(drawer).getByText("Parent")).toBeInTheDocument();
    expect(within(drawer).getByText("LQI latest")).toBeInTheDocument();
    expect(within(drawer).getByText("140")).toBeInTheDocument();
  });

  it("qualifies route-table evidence in the route edge drawer", async () => {
    await renderLiveAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Latest route-table / next-hop evidence from Live Hall Router to Live Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(
      within(drawer).getByText(/route evidence at capture time, not a guaranteed current path/i),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("Route observed count").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(within(drawer).getByText("Captured at")).toBeInTheDocument();
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/routes via/i)).not.toBeInTheDocument();
  });

  it("renders live inventory fields in the node drawer", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Live Hall Router")).toBeInTheDocument();
    expect(within(drawer).getByText("0xr1")).toBeInTheDocument();
    expect(within(drawer).getByText("Online")).toBeInTheDocument();
    expect(within(drawer).getByText("In Zigbee2MQTT device inventory")).toBeInTheDocument();
    expect(within(drawer).getByText("Healthy")).toBeInTheDocument();
    expect(
      within(drawer).getByText(/observed in the latest topology snapshot/i),
    ).toBeInTheDocument();
  });

  it("uses the not-an-incident copy for a sleepy battery device with no topology link", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe2"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText(
        /this can be normal for sleepy battery devices and is not an incident by itself/i,
      ),
    ).toBeInTheDocument();
    expect(within(drawer).queryByText(/incident detected/i)).not.toBeInTheDocument();
  });

  it("shows an honest limited state without fake zeroes or sample fallback", async () => {
    mockDetail = liveDetailLimited;
    const { container } = renderGraphPage("home2");
    expect(
      await screen.findByText(/did not provide usable node\/link layout data/i),
    ).toBeInTheDocument();
    const observedNodes = screen.getByText("Observed topology nodes");
    expect(observedNodes.nextElementSibling).toHaveTextContent("—");
    const observedLinks = screen.getByText("Observed topology links");
    expect(observedLinks.nextElementSibling).toHaveTextContent("—");
    expect(screen.getByText("102")).toBeInTheDocument();
    expect(screen.getByText(/missing topology data is not an incident by itself/i)).toBeInTheDocument();
    // No graph, no fixture fallback.
    expect(container.querySelectorAll(".mesh-edge")).toHaveLength(0);
    expect(screen.queryByTestId("mesh-evidence-graph")).not.toBeInTheDocument();
    expect(screen.queryByText("Living room plug")).not.toBeInTheDocument();
    expect(screen.queryByText("Prototype — sample data")).not.toBeInTheDocument();
  });

  it("shows a waiting state when no snapshot exists instead of falling back to sample", async () => {
    mockDetail = {
      network_id: "home2",
      network_name: "Home 2",
      latest_snapshot: null,
      nodes: [],
      links: [],
      inventory: { device_count: 5, router_count: 1, end_device_count: 3 },
      layout_available: false,
    };
    renderGraphPage("home2");
    expect(await screen.findByText("Waiting for a topology snapshot")).toBeInTheDocument();
    expect(
      screen.getByText(/missing topology data is not an incident by itself/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Living room plug")).not.toBeInTheDocument();
  });

  it("creates a clearly labelled placeholder node for a link endpoint unknown to inventory and node list", async () => {
    mockDetail = liveDetailWithGhostEndpoint;
    await renderLiveAndWaitForLayout();
    const ghost = screen.getByTestId("mesh-node-0xghost");
    expect(ghost).toBeInTheDocument();
    expect(within(ghost).getByText("Unknown role")).toBeInTheDocument();

    fireEvent.click(ghost);
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText("Referenced by topology links only — unknown to inventory and node list"),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(
        /the latest topology snapshot referenced this endpoint in a link, but zigbeelens does not currently have matching inventory or device details/i,
      ),
    ).toBeInTheDocument();
    expect(within(drawer).queryByText("In Zigbee2MQTT device inventory")).not.toBeInTheDocument();
  });

  it("exposes the chosen layout strategy as debug metadata", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const wrapper = container.querySelector("[data-layout-strategy]");
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("data-layout-strategy", "layered");
    expect(wrapper).toHaveAttribute("data-layout-structural-edges", "2");
  });

  it("shows an error state instead of an infinite spinner when the layout fails", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockLayoutFailure = new Error("Referenced shape does not exist: 0xdead");
    renderGraphPage();
    const errorPanel = await screen.findByTestId("graph-layout-error");
    expect(errorPanel).toHaveTextContent(
      "The graph layout could not be computed for this snapshot. The topology data is still available in list/detail views.",
    );
    expect(screen.queryByText(/computing layout/i)).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("never silently swaps to sample data when the layout fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockLayoutFailure = new Error("layout timed out");
    renderGraphPage();
    await screen.findByTestId("graph-layout-error");
    expect(screen.getByTestId("graph-mode-badge")).toHaveTextContent("Live topology snapshot");
    expect(screen.queryByText("Living room plug")).not.toBeInTheDocument();
    expect(screen.queryByText("Prototype — sample data")).not.toBeInTheDocument();
  });
});

describe("TopologyGraphPage sample mode", () => {
  it("is explicitly labelled and never presented as live data", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await switchToSample(user);
    expect(screen.getByTestId("graph-mode-badge")).toHaveTextContent("Prototype — sample data");
    expect(screen.getByTestId("graph-mode-badge")).not.toHaveTextContent(
      "Live topology snapshot",
    );
    expect(
      screen.getByText(/sample evidence data for design validation — not data from your network/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/it does not represent network/i)).toBeInTheDocument();
  });

  it("renders the full fixture evidence grammar in sample mode", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await switchToSample(user);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(5);
    });
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(2);
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(2);
  });

  it("still frames passive-derived sample edges as investigation hints, never routes", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await switchToSample(user);
    const edge = await screen.findByLabelText(
      "Passive-derived association between Hallway repeater and Kitchen motion",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Investigation hint")).toBeInTheDocument();
    expect(within(drawer).getAllByText(/is not a route/i).length).toBeGreaterThan(0);
    expect(within(drawer).queryByText(/routes via/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
  });

  it("does not claim a current route for historical sample evidence", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await switchToSample(user);
    const edge = await screen.findByLabelText(
      "Historically observed link between Hallway repeater and Bedroom temp sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
  });

  it("re-enables historical/passive/stale filters in sample mode", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await switchToSample(user);
    const staleToggle = screen.getByRole("checkbox", { name: /stale \/ low-confidence/i });
    expect(staleToggle).toBeEnabled();
    await user.click(staleToggle);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--stale_low_confidence")).toHaveLength(1);
    });
  });
});

describe("TopologyGraphPage shared chrome", () => {
  it("renders the legend with every evidence class", async () => {
    await renderLiveAndWaitForLayout();
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    for (const cls of EVIDENCE_CLASSES) {
      expect(within(legend).getByText(evidenceClassLabel(cls))).toBeInTheDocument();
    }
  });

  it("renders the safety banner in both modes", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const note = screen.getByRole("note", { name: /evidence safety note/i });
    expect(note).toHaveTextContent(GRAPH_SAFETY_COPY);
    await switchToSample(user);
    expect(screen.getByRole("note", { name: /evidence safety note/i })).toHaveTextContent(
      GRAPH_SAFETY_COPY,
    );
  });
});
