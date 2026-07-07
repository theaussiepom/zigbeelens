import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";
import { meshEvidenceGraphFixture } from "@/fixtures/meshEvidenceGraph";
import type {
  HistoricalEdgeAggregate,
  TopologyEvidenceGraphDetail,
  TopologyNetworkDetail,
} from "@/lib/api";
import {
  EVIDENCE_CLASSES,
  evidenceClassLabel,
  GRAPH_SAFETY_COPY,
  GRAPH_SAFETY_COPY_LIVE,
} from "@/lib/meshEvidence";
import { positionStorageKey } from "@/lib/meshGraphSmartLayout";
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

const HISTORICAL_NEIGHBOR_LIMITATIONS = [
  "This neighbour link was observed in a recent previous topology snapshot but is not shown in the latest usable snapshot. This does not prove current live routing.",
  "Not observed in the latest snapshot. This alone does not prove the link is gone or that a device has failed.",
];

const HISTORICAL_ROUTE_LIMITATIONS = [
  "Route-table evidence was observed in a recent previous topology snapshot. This does not prove current live routing.",
  "Not observed in the latest snapshot. This alone does not prove the link is gone or that a device has failed.",
];

function makeHistoricalAggregate(
  overrides: Partial<HistoricalEdgeAggregate>,
): HistoricalEdgeAggregate {
  return {
    source_ieee: "0xe1",
    target_ieee: "0xe2",
    evidence_class: "historical_neighbor",
    directional: false,
    first_seen_at: "2026-07-01T10:00:00+00:00",
    last_seen_at: "2026-07-04T10:00:00+00:00",
    observed_count: 5,
    snapshot_count: 3,
    lqi_latest: 80,
    lqi_min: 60,
    lqi_median: 75,
    lqi_max: 90,
    route_observed_count: null,
    last_route_count: null,
    last_relationship: "Sibling",
    last_snapshot_id: "snap-old",
    last_captured_at: "2026-07-04T10:00:00+00:00",
    not_seen_in_latest_snapshot: true,
    latest_layout_limited: false,
    confidence: "medium",
    limitations: HISTORICAL_NEIGHBOR_LIMITATIONS,
    ...overrides,
  };
}

/** The home network plus backend-aggregated recent-missing evidence. */
const liveDetailWithHistory: TopologyEvidenceGraphDetail = {
  ...liveDetailHome,
  data_source: "latest_snapshot_plus_history",
  latest_layout_limited: false,
  history_window: {
    days: 7,
    max_snapshots: 3,
    snapshots_considered: 3,
    earliest_captured_at: "2026-07-01T10:00:00+00:00",
    latest_captured_at: "2026-07-04T10:00:00+00:00",
  },
  historical_neighbors: [makeHistoricalAggregate({})],
  historical_routes: [
    makeHistoricalAggregate({
      source_ieee: "0xr1",
      target_ieee: "0xe1",
      evidence_class: "historical_route",
      directional: true,
      lqi_latest: null,
      lqi_min: null,
      lqi_median: null,
      lqi_max: null,
      observed_count: 2,
      snapshot_count: 2,
      route_observed_count: 2,
      last_route_count: 3,
      last_relationship: "Child",
      limitations: HISTORICAL_ROUTE_LIMITATIONS,
    }),
  ],
  limitations: [],
  counts: {
    latest_snapshot_neighbor_edges: 2,
    latest_snapshot_route_edges: 1,
    historical_neighbor_edges: 1,
    historical_route_edges: 1,
    recent_missing_link_count_total: 2,
    hidden_for_readability: null,
    known_inventory_devices: 4,
    observed_topology_nodes: 3,
  },
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

/**
 * A dense network shaped like the real reference deployment: a coordinator
 * plus a clique of routers, giving well over the dense-mode edge threshold,
 * with exactly one real route-table link, varied LQI values, and one router
 * (0xr7) already flagged as needing attention.
 */
function makeDenseNetwork(routerCount = 30): {
  detail: TopologyNetworkDetail;
  devices: DeviceSummary[];
} {
  const nodes = [
    { ieee_address: "0xc0", friendly_name: "Dense Coordinator", node_type: "Coordinator" },
  ];
  const devices = [
    makeDevice({
      ieee_address: "0xc0",
      friendly_name: "Dense Coordinator",
      device_type: "Coordinator",
    }),
  ];
  const links: NonNullable<TopologyNetworkDetail["links"]> = [];
  for (let i = 0; i < routerCount; i += 1) {
    const ieee = `0xr${i}`;
    nodes.push({ ieee_address: ieee, friendly_name: `Dense Router ${i}`, node_type: "Router" });
    devices.push(
      makeDevice({
        ieee_address: ieee,
        friendly_name: `Dense Router ${i}`,
        device_type: "Router",
        ...(i === 7
          ? {
              lens_bucket: "needs_attention" as const,
              lens_bucket_label: "Needs attention",
              lens_bucket_reason: "Reporting gaps observed.",
            }
          : {}),
      }),
    );
    for (let j = 0; j < i; j += 1) {
      links.push({
        source_ieee: ieee,
        target_ieee: `0xr${j}`,
        linkquality: 20 + ((i * 7 + j * 13) % 200),
        relationship: "Sibling",
        route_count: null,
      });
    }
  }
  links.push({
    source_ieee: "0xr0",
    target_ieee: "0xc0",
    linkquality: 140,
    relationship: "Parent",
    route_count: 2,
  });
  return {
    detail: {
      network_id: "home",
      network_name: "Home",
      latest_snapshot: {
        snapshot_id: "snap-dense",
        network_id: "home",
        captured_at: "2026-07-06T00:30:00+00:00",
        requested_by: "startup_scan",
        status: "complete",
        router_count: routerCount,
        end_device_count: 0,
        link_count: links.length,
      },
      nodes,
      links,
      inventory: { device_count: devices.length, router_count: routerCount, end_device_count: 0 },
      layout_available: true,
    },
    devices,
  };
}

let mockDetail: TopologyNetworkDetail | null = liveDetailHome;
let mockDevices: DeviceSummary[] = liveDevices;

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
  localStorage.clear();
});

/** Rendered canvas position of a device node (from React Flow's transform). */
function nodePosition(container: HTMLElement, ieee: string): string {
  const wrapper = container.querySelector(`.react-flow__node[data-id="${ieee}"]`);
  expect(wrapper).not.toBeNull();
  // Normalise whitespace: React Flow formats the transform inconsistently.
  return (wrapper as HTMLElement).style.transform.replace(/\s+/g, "");
}

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
    // No historical evidence in this fixture: recent missing links disabled.
    expect(screen.getByRole("checkbox", { name: /recent missing links/i })).toBeDisabled();
    expect(screen.queryByText(/previously seen/i)).not.toBeInTheDocument();
    expect(
      screen.getByText("No recent missing links in the selected history window."),
    ).toBeInTheDocument();
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

  it("exposes the active layout mode as debug metadata", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const wrapper = container.querySelector("[data-layout-mode]");
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("data-layout-mode", "smart");
  });
});

describe("TopologyGraphPage layout modes", () => {
  it("renders the five human-named layout modes with short hints, Smart layout as default", async () => {
    await renderLiveAndWaitForLayout();
    const selector = screen.getByRole("combobox", { name: /layout/i });
    const labels = within(selector)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(labels).toEqual([
      "Smart layout — Best overall view",
      "Router backbone — Infrastructure first",
      "Router clusters — Group by router evidence",
      "Health focus — Find problem devices",
      "Manual layout — Use saved positions",
    ]);
    expect(selector).toHaveValue("smart");
    expect(screen.getByTestId("layout-mode-description")).toHaveTextContent(
      /best overall view.*coordinator, router backbone, end devices/i,
    );
  });

  it("smart layout anchors the coordinator above the routers on first render", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const yOf = (ieee: string) => {
      const match = /translate\(\s*[-\d.]+px\s*,\s*([-\d.]+)px\s*\)/.exec(
        nodePosition(container, ieee),
      );
      expect(match).not.toBeNull();
      return Number(match![1]);
    };
    expect(yOf("0xc0")).toBeLessThan(yOf("0xr1"));
    expect(yOf("0xr1")).toBeLessThan(yOf("0xe1"));
  });

  it("changing layout mode keeps the evidence controls and updates the description", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await user.selectOptions(screen.getByRole("combobox", { name: /layout/i }), "clusters");
    expect(container.querySelector("[data-layout-mode]")).toHaveAttribute(
      "data-layout-mode",
      "clusters",
    );
    expect(screen.getByTestId("layout-mode-description")).toHaveTextContent(
      /does not prove current live routing/i,
    );
    expect(screen.getByRole("group", { name: /evidence filters/i })).toBeInTheDocument();
  });

  it("manual layout mode explains browser-local saved positions", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.selectOptions(screen.getByRole("combobox", { name: /layout/i }), "manual");
    expect(screen.getByTestId("layout-mode-description")).toHaveTextContent(
      /uses your saved positions.*in this browser/i,
    );
  });

  it("shows an updated explanation for every layout mode", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const selector = screen.getByRole("combobox", { name: /layout/i });
    const expected: Array<[string, RegExp]> = [
      ["backbone", /mesh infrastructure first.*routers forming the main structure/i],
      ["clusters", /observed router neighbourhoods.*does not prove current live routing/i],
      ["health", /devices needing attention easier to find/i],
      ["manual", /uses your saved positions/i],
      ["smart", /best overall view/i],
    ];
    for (const [mode, pattern] of expected) {
      await user.selectOptions(selector, mode);
      expect(screen.getByTestId("layout-mode-description")).toHaveTextContent(pattern);
    }
  });

  it("applies saved manual positions from localStorage over the generated layout", async () => {
    localStorage.setItem(
      positionStorageKey("home", "smart"),
      JSON.stringify({ "0xr1": { x: 4321, y: 1234 } }),
    );
    const { container } = await renderLiveAndWaitForLayout();
    expect(nodePosition(container, "0xr1")).toContain("translate(4321px,1234px)");
  });

  it("keeps saved positions applied across filter toggles and drawer open/close", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      positionStorageKey("home", "smart"),
      JSON.stringify({ "0xr1": { x: 4321, y: 1234 } }),
    );
    const { container } = await renderLiveAndWaitForLayout();

    await user.click(screen.getByRole("checkbox", { name: /route evidence/i }));
    expect(nodePosition(container, "0xr1")).toContain("translate(4321px,1234px)");

    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });
    expect(nodePosition(container, "0xr1")).toContain("translate(4321px,1234px)");
  });

  it("reset layout clears saved positions and recomputes the generated layout", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      positionStorageKey("home", "smart"),
      JSON.stringify({ "0xr1": { x: 4321, y: 1234 } }),
    );
    const { container } = await renderLiveAndWaitForLayout();
    expect(nodePosition(container, "0xr1")).toContain("translate(4321px,1234px)");

    await user.click(screen.getByRole("button", { name: /reset layout/i }));
    await waitFor(() => {
      expect(nodePosition(container, "0xr1")).not.toContain("translate(4321px,1234px)");
    });
    expect(localStorage.getItem(positionStorageKey("home", "smart"))).toBeNull();
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
      "Recent missing neighbour link between Hallway repeater and Bedroom temp sensor",
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

describe("TopologyGraphPage layout stability", () => {
  it("does not move nodes or remount the graph on a routine refetch with unchanged data", async () => {
    const view = renderGraphPage();
    await screen.findByText("Live Hall Router");
    const flowEl = view.container.querySelector(".react-flow");
    expect(flowEl).not.toBeNull();
    const before = nodePosition(view.container, "0xr1");

    // Simulate a routine API refetch: identical content, fresh object identity.
    mockDetail = JSON.parse(JSON.stringify(liveDetailHome)) as TopologyNetworkDetail;
    view.rerender(
      <MemoryRouter initialEntries={["/topology/home/graph"]}>
        <Routes>
          <Route path="/topology/:networkId/graph" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("Live Hall Router");
    expect(nodePosition(view.container, "0xr1")).toBe(before);
    // Same React Flow DOM node — no remount, so fitView cannot have re-fired.
    expect(view.container.querySelector(".react-flow")).toBe(flowEl);
  });

  it("does not move nodes when filters change or a drawer opens", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByText("Live Hall Router");
    const flowEl = container.querySelector(".react-flow");
    const before = nodePosition(container, "0xr1");

    await user.click(screen.getByRole("checkbox", { name: /route evidence/i }));
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });

    expect(nodePosition(container, "0xr1")).toBe(before);
    // No remount either: fitView cannot have re-fired.
    expect(container.querySelector(".react-flow")).toBe(flowEl);
  });
});

describe("TopologyGraphPage dense graph mode", () => {
  beforeEach(() => {
    const dense = makeDenseNetwork();
    mockDetail = dense.detail;
    mockDevices = dense.devices;
  });

  function connectionsPanel() {
    return within(screen.getByRole("group", { name: /connections to show/i }));
  }

  it("renders human-readable connection controls with the spec defaults", async () => {
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionsPanel();

    expect(panel.getByRole("checkbox", { name: /route hints/i })).toBeChecked();
    expect(panel.getByRole("checkbox", { name: /best neighbour links/i })).toBeChecked();
    // "Devices with issues" is off by default and framed as highlighting.
    expect(panel.getByRole("checkbox", { name: /devices with issues/i })).not.toBeChecked();
    expect(
      panel.getByText(/highlight devices already marked by zigbeelens as needing attention/i),
    ).toBeInTheDocument();
    expect(panel.getByRole("checkbox", { name: /all neighbour links/i })).not.toBeChecked();
    expect(panel.getByRole("checkbox", { name: /old or uncertain links/i })).not.toBeChecked();

    // Helper copy explains what each type draws.
    expect(
      panel.getByText(/a focused set of observed neighbour links/i),
    ).toBeInTheDocument();
    expect(
      panel.getByText(/draw every observed neighbour link from the latest snapshot/i),
    ).toBeInTheDocument();

    // No route-hint copy may claim live routing.
    expect(panel.getByText(/not guaranteed live routing/i)).toBeInTheDocument();
  });

  it("disables old/uncertain and recent missing links when the data has none", async () => {
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionsPanel();

    expect(panel.getByRole("checkbox", { name: /old or uncertain links/i })).toBeDisabled();
    expect(
      panel.getByText("No old or uncertain links in this snapshot."),
    ).toBeInTheDocument();

    // No historical evidence in this fixture: disabled with honest copy.
    expect(panel.getByRole("checkbox", { name: /recent missing links/i })).toBeDisabled();
    expect(panel.queryByText(/previously seen/i)).not.toBeInTheDocument();
    expect(
      panel.getByText("No recent missing links in the selected history window."),
    ).toBeInTheDocument();
    expect(panel.queryByRole("checkbox", { name: /selected device links/i })).not.toBeInTheDocument();
    expect(panel.queryByRole("checkbox", { name: /suggested investigation links/i })).not.toBeInTheDocument();
  });

  it("draws a focused subset by default — not empty, not the full hairball", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");

    expect(screen.queryByTestId("dense-graph-banner")).not.toBeInTheDocument();
    expect(screen.queryByText("Focused view")).not.toBeInTheDocument();
    expect(screen.queryByText(/drawn in this view/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);
    });
    const neighbourCount = container.querySelectorAll(
      ".mesh-edge--latest_snapshot_neighbor",
    ).length;
    // Best neighbour links: some but never all 436.
    expect(neighbourCount).toBeGreaterThan(0);
    expect(neighbourCount).toBeLessThan(436);
  });

  it("Devices with issues highlights issue nodes without flooding the graph with links", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionsPanel();

    const before = container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length;
    const beforePos = nodePosition(container, "0xr7");

    await user.click(panel.getByRole("checkbox", { name: /devices with issues/i }));

    // Node highlighting only: the flagged device 0xr7 gets the highlight
    // class, no extra neighbour edges appear, and nothing moves.
    await waitFor(() => {
      expect(
        container.querySelector('.react-flow__node[data-id="0xr7"]'),
      ).toHaveClass("mesh-node--issue-highlight");
    });
    expect(container.querySelectorAll(".mesh-node--issue-highlight")).toHaveLength(1);
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(
      before,
    );
    expect(nodePosition(container, "0xr7")).toBe(beforePos);

    // Selecting the issue node still reveals its full evidence neighbourhood.
    fireEvent.click(screen.getByTestId("mesh-node-0xr7"));
    await screen.findByRole("dialog", { name: /device details/i });
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length,
      ).toBeGreaterThan(before);
    });
  });

  it("selecting a node reveals its full evidence neighbourhood without moving nodes", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const beforePos = nodePosition(container, "0xr5");
    const beforeCount = container.querySelectorAll(
      ".mesh-edge--latest_snapshot_neighbor",
    ).length;

    fireEvent.click(screen.getByTestId("mesh-node-0xr5"));
    await screen.findByRole("dialog", { name: /device details/i });
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length,
      ).toBeGreaterThan(beforeCount);
    });
    // A weak link of 0xr5 that is in nobody's best-N is now reachable.
    expect(
      screen.getByLabelText(
        "Latest snapshot neighbour evidence between Dense Router 5 and Dense Router 4",
      ),
    ).toBeInTheDocument();
    expect(nodePosition(container, "0xr5")).toBe(beforePos);
  });

  it("All neighbour links renders the full snapshot evidence with a warning, and off restores the subset", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const subsetCount = container.querySelectorAll(
      ".mesh-edge--latest_snapshot_neighbor",
    ).length;
    const beforePos = nodePosition(container, "0xr5");

    const allLinks = connectionsPanel().getByRole("checkbox", { name: /all neighbour links/i });
    await user.click(allLinks);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(436);
    });
    expect(connectionsPanel().getByTestId("all-neighbour-links-warning")).toHaveTextContent(
      "All neighbour links is on. Dense networks may become hard to read.",
    );
    // Route hints stay visible alongside.
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);

    await user.click(allLinks);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(
        subsetCount,
      );
    });
    // The warning disappears once All neighbour links is off again.
    expect(screen.queryByTestId("all-neighbour-links-warning")).not.toBeInTheDocument();
    // Connection toggles never move nodes.
    expect(nodePosition(container, "0xr5")).toBe(beforePos);
  });

  it("edge drawer keeps full metadata for visible edges in dense mode", async () => {
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const edge = await screen.findByLabelText(
      "Latest route-table / next-hop evidence from Dense Router 0 to Dense Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Route observed count").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
  });

  it("stays off for small graphs, which keep the evidence filter panel", async () => {
    mockDetail = liveDetailHome;
    mockDevices = liveDevices;
    renderGraphPage();
    await screen.findByText("Live Hall Router");
    expect(screen.queryByTestId("dense-graph-banner")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("group", { name: /connections to show/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /evidence filters/i })).toBeInTheDocument();
  });
});

describe("TopologyGraphPage historical evidence (live)", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithHistory;
    mockDevices = liveDevices;
  });

  it("enables Recent missing links when historical evidence exists, default off", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const checkbox = screen.getByRole("checkbox", { name: /recent missing links/i });
    expect(checkbox).toBeEnabled();
    expect(checkbox).not.toBeChecked();
    // The old label is gone everywhere.
    expect(screen.queryByText(/previously seen/i)).not.toBeInTheDocument();
    // Off by default: no historical edges rendered.
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(0);
    // No passive-derived edges are ever created from live data.
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(0);
  });

  it("renders dotted historical edges when Recent missing links is enabled", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await user.click(screen.getByRole("checkbox", { name: /recent missing links/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(1);
    // Latest edges are never duplicated as historical.
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(2);
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);
  });

  it("shows the recent missing links count pill from API counts", async () => {
    await renderLiveAndWaitForLayout();
    const pill = screen.getByText("Recent missing links", { selector: ".uppercase" });
    expect(pill.nextElementSibling).toHaveTextContent("2");
  });

  it("metric chips carry plain-language accessible descriptions", async () => {
    await renderLiveAndWaitForLayout();
    expect(
      screen.getByTitle("Devices present in the latest parsed topology snapshot."),
    ).toBeInTheDocument();
    expect(
      screen.getByTitle("Links reported in the latest topology snapshot."),
    ).toBeInTheDocument();
    expect(
      screen.getByTitle(
        "Links seen in recent previous topology snapshots but not present in the latest usable snapshot.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByTitle("Devices ZigbeeLens knows from Zigbee2MQTT inventory."),
    ).toBeInTheDocument();
  });

  it("frames the historical neighbour drawer as previous-snapshot evidence, never live routing", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.click(screen.getByRole("checkbox", { name: /recent missing links/i }));
    const edge = await screen.findByLabelText(
      "Recent missing neighbour link between Live Lamp and Live Sleepy Sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Recent missing link")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/observed in a recent previous topology snapshot/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText(/not observed in the latest topology snapshot/i),
    ).toBeInTheDocument();
    // Historical aggregate facts.
    expect(within(drawer).getByText("First observed")).toBeInTheDocument();
    expect(within(drawer).getByText("Last observed")).toBeInTheDocument();
    expect(within(drawer).getByText("Observed count").nextElementSibling).toHaveTextContent("5");
    expect(within(drawer).getByText("Snapshot count").nextElementSibling).toHaveTextContent("3");
    expect(within(drawer).getByText("LQI min").nextElementSibling).toHaveTextContent("60");
    expect(within(drawer).getByText("LQI median").nextElementSibling).toHaveTextContent("75");
    expect(within(drawer).getByText("LQI max").nextElementSibling).toHaveTextContent("90");
    // Unknown route evidence stays "Not recorded", never zero.
    expect(
      within(drawer).getByText("Route observed count").nextElementSibling,
    ).toHaveTextContent("Not recorded");
    // No live-routing claims.
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/lost connection/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/broken link/i)).not.toBeInTheDocument();
  });

  it("frames the historical route drawer with previous route-table evidence and counts", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.click(screen.getByRole("checkbox", { name: /recent missing links/i }));
    const edge = await screen.findByLabelText(
      "Recent missing route hint from Live Hall Router to Live Lamp",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(within(drawer).getByText("Recent missing route")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(
        /route-table evidence was observed in a recent previous topology snapshot/i,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText("Route observed count").nextElementSibling,
    ).toHaveTextContent("2");
    expect(within(drawer).getByText("Last route count").nextElementSibling).toHaveTextContent(
      "3",
    );
    expect(within(drawer).queryByText(/current route/i)).not.toBeInTheDocument();
  });

  it("adds a recent missing topology section to the node drawer", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Recent missing topology evidence")).toBeInTheDocument();
    // 0xe1 touches the historical neighbour and the historical route.
    expect(
      within(drawer).getByText(/2 recent missing links in the selected history window/i),
    ).toBeInTheDocument();
    expect(within(drawer).getByText(/last seen in topology evidence/i)).toBeInTheDocument();
  });

  it("says so plainly when a device has no recent missing links", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xc0"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText(
        "No recent missing topology links in the selected history window.",
      ),
    ).toBeInTheDocument();
  });

  it("qualifies rather than overclaims when the latest layout is limited", async () => {
    const limitedNeighborCopy =
      "This neighbour link was observed in a recent previous topology snapshot. The latest snapshot layout is limited, so absence from the latest graph is not meaningful by itself.";
    mockDetail = {
      ...liveDetailWithHistory,
      latest_layout_limited: true,
      historical_neighbors: [
        makeHistoricalAggregate({
          latest_layout_limited: true,
          not_seen_in_latest_snapshot: true,
          limitations: [limitedNeighborCopy],
        }),
      ],
      historical_routes: [],
    };
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.click(screen.getByRole("checkbox", { name: /recent missing links/i }));
    const edge = await screen.findByLabelText(
      "Recent missing neighbour link between Live Lamp and Live Sleepy Sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link evidence/i });
    expect(
      within(drawer).getAllByText(/absence from the latest graph is not meaningful by itself/i)
        .length,
    ).toBeGreaterThan(0);
    // No unqualified "missing from latest" claim.
    expect(
      within(drawer).queryByText(/not observed in the latest topology snapshot\./i),
    ).not.toBeInTheDocument();

    // Node drawer carries the same qualification.
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const nodeDrawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(nodeDrawer).getByText(
        /the latest snapshot layout is limited, so absence from the latest graph is not meaningful by itself/i,
      ),
    ).toBeInTheDocument();
  });
});

describe("TopologyGraphPage historical evidence in dense mode", () => {
  function makeDenseWithHistory(historicalNeighbors?: HistoricalEdgeAggregate[]) {
    const dense = makeDenseNetwork();
    const neighbors = historicalNeighbors ?? [
      makeHistoricalAggregate({ source_ieee: "0xr1", target_ieee: "0xr20" }),
      makeHistoricalAggregate({ source_ieee: "0xr2", target_ieee: "0xr21" }),
    ];
    const detail: TopologyEvidenceGraphDetail = {
      ...dense.detail,
      data_source: "latest_snapshot_plus_history",
      latest_layout_limited: false,
      history_window: {
        days: 7,
        max_snapshots: 3,
        snapshots_considered: 2,
        earliest_captured_at: "2026-07-01T10:00:00+00:00",
        latest_captured_at: "2026-07-04T10:00:00+00:00",
      },
      historical_neighbors: neighbors,
      historical_routes: [],
      limitations: [],
      counts: {
        latest_snapshot_neighbor_edges: 435,
        latest_snapshot_route_edges: 1,
        historical_neighbor_edges: neighbors.length,
        historical_route_edges: 0,
        recent_missing_link_count_total: neighbors.length,
        hidden_for_readability: null,
        known_inventory_devices: dense.devices.length,
        observed_topology_nodes: 31,
      },
    };
    return { detail, devices: dense.devices };
  }

  beforeEach(() => {
    const dense = makeDenseWithHistory();
    mockDetail = dense.detail;
    mockDevices = dense.devices;
  });

  it("keeps historical edges out of the default focused view", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    expect(screen.queryByTestId("dense-graph-banner")).not.toBeInTheDocument();
  });

  it("shows historical edges in dense mode only when Recent missing links is enabled", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = within(screen.getByRole("group", { name: /connections to show/i }));

    const checkbox = panel.getByRole("checkbox", { name: /recent missing links/i });
    expect(checkbox).toBeEnabled();
    expect(checkbox).not.toBeChecked();
    expect(panel.queryByText(/previously seen/i)).not.toBeInTheDocument();
    expect(
      panel.getByText(
        "Draw recent links observed in previous topology snapshots but not present in the latest usable snapshot.",
      ),
    ).toBeInTheDocument();

    await user.click(checkbox);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(2);
    });

    await user.click(checkbox);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    });
  });

  it("caps recent missing links per node in dense mode", async () => {
    // Six historical links all touching 0xr1: the per-node cap (3) applies.
    const dense = makeDenseWithHistory(
      [20, 21, 22, 23, 24, 25].map((i) =>
        makeHistoricalAggregate({ source_ieee: "0xr1", target_ieee: `0xr${i}` }),
      ),
    );
    mockDetail = dense.detail;
    mockDevices = dense.devices;

    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = within(screen.getByRole("group", { name: /connections to show/i }));
    await user.click(panel.getByRole("checkbox", { name: /recent missing links/i }));

    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(3);
    });
  });

  it("renders no concealment or live-routing phrasing anywhere on the page", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = within(screen.getByRole("group", { name: /connections to show/i }));
    await user.click(panel.getByRole("checkbox", { name: /recent missing links/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(2);
    });

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/hidden for readability/i);
    expect(text).not.toMatch(/\bignored\b/i);
    expect(text).not.toMatch(/\bdiscarded\b/i);
    expect(text).not.toMatch(/\birrelevant\b/i);
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/currently routed/i);
    expect(text).not.toMatch(/current route\b/i);
  });

  it("selecting a device reveals its recent missing links without moving the layout", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const beforePos = nodePosition(container, "0xr20");
    // Control off: the historical edge is hidden.
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);

    fireEvent.click(screen.getByTestId("mesh-node-0xr20"));
    await screen.findByRole("dialog", { name: /device details/i });
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    // Only 0xr20's historical neighbourhood is revealed, not 0xr2–0xr21.
    expect(
      screen.getByLabelText(
        "Recent missing neighbour link between Dense Router 1 and Dense Router 20",
      ),
    ).toBeInTheDocument();
    expect(nodePosition(container, "0xr20")).toBe(beforePos);
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

  it("renders mode-specific safety banners: live copy never claims passive links are active", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const note = screen.getByRole("note", { name: /evidence safety note/i });
    expect(note).toHaveTextContent(GRAPH_SAFETY_COPY_LIVE);
    // Live mode has no passive-derived edges, so the banner must not imply them.
    expect(note).not.toHaveTextContent(/passive/i);
    expect(note).toHaveTextContent(/should not be treated as proof of current live routing/i);
    await switchToSample(user);
    // Sample mode still demonstrates passive-derived fixture evidence.
    expect(screen.getByRole("note", { name: /evidence safety note/i })).toHaveTextContent(
      GRAPH_SAFETY_COPY,
    );
  });
});
