import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import { TopologyGraphPage } from "@/pages/TopologyGraphPage";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
  DeviceStoryDto,
  HistoricalEdgeAggregate,
  InvestigationCard,
  LastKnownLinkAggregate,
  PassiveHintAggregate,
  TopologyEvidenceGraphDetail,
} from "@/lib/api";
import { api } from "@/lib/api";
import type { DataCoverageDto } from "@/types/decisions";
import {
  LIVE_EVIDENCE_CLASSES,
  evidenceClassLabel,
  GRAPH_SAFETY_COPY_LIVE,
} from "@/lib/meshEvidence";
import { connectionControlsStorageKey } from "@/lib/meshGraphDense";
import { findForbiddenUserFacingPhrases, GRAPH_VIEW_DRAW_MORE_LINKS } from "@/lib/meshGraphCopy";
import { viewPresetStorageKey } from "@/lib/meshGraphPresets";
import { positionStorageKey } from "@/lib/meshGraphSmartLayout";
import { mockReactFlow } from "@/test/mockReactFlow";
import { makeTopologyEvidenceGraphDetail } from "@/test/topologyEvidenceGraphFixture";

beforeAll(() => {
  mockReactFlow();
});

async function openDrawMoreLinks(user?: ReturnType<typeof userEvent.setup>) {
  const button = screen.getByRole("button", { name: new RegExp(GRAPH_VIEW_DRAW_MORE_LINKS, "i") });
  if (button.getAttribute("aria-expanded") !== "true") {
    if (user) await user.click(button);
    else fireEvent.click(button);
  }
}

function connectionControlsPanel() {
  openDrawMoreLinks();
  return within(screen.getByRole("group", { name: /connections to show/i }));
}

function connectionCheckbox(name: RegExp | string) {
  return connectionControlsPanel().getByRole("checkbox", { name });
}

async function clickConnectionCheckbox(
  user: ReturnType<typeof userEvent.setup>,
  name: RegExp | string,
) {
  await openDrawMoreLinks(user);
  await user.click(screen.getByRole("checkbox", { name }));
}

async function selectGraphViewPreset(
  user: ReturnType<typeof userEvent.setup>,
  presetId: string,
) {
  await user.selectOptions(
    screen.getByRole("combobox", { name: /graph view preset/i }),
    presetId,
  );
}

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
    decision: { status: "no_notable_change", priority: "none", headline_code: "device_no_notable_change", coverage_label_codes: [] },
    incident_affected: false,
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

const liveDetailHome = makeTopologyEvidenceGraphDetail({
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
});

const liveDetailLimited = makeTopologyEvidenceGraphDetail({
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
});

const HISTORICAL_NEIGHBOR_LIMITATIONS = [
  "This link was seen recently but is not in the latest usable snapshot. That can happen if the device is sleepy, recently moved, powered off, or simply absent from the latest map. Check the device before treating this as a mesh problem.",
  "Not observed in the latest snapshot. This alone does not prove a failure.",
];

const HISTORICAL_ROUTE_LIMITATIONS = [
  "Route-table evidence was observed in a recent previous topology snapshot. This suggests possible next-hop evidence at that time. It does not prove current live routing.",
  "Not observed in the latest snapshot. This alone does not prove a failure.",
];

const emptyTopologyNetworkFacts = {
  stale_threshold_hours: null,
  network_facts: [],
  coverage: [],
};

const emptyTopologyDeviceFacts = {
  stale_threshold_hours: null,
  device_facts: [],
  comparison_facts_by_snapshot_id: {},
};

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
const liveDetailWithHistory: TopologyEvidenceGraphDetail = makeTopologyEvidenceGraphDetail({
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
  last_known_links: [],
  last_known_window: {
    snapshots_considered: 3,
    earliest_captured_at: "2026-07-01T10:00:00+00:00",
    latest_captured_at: "2026-07-04T10:00:00+00:00",
  },
  passive_hints: [],
  passive_hint_window: { days: 7, event_window_minutes: 5, min_repeated_windows: 2 },
  investigations: [],
  investigation_counts: { available: 0, returned: 0 },
  device_stats: {},
  device_stats_window: { days: 7, max_snapshots: 10, snapshots_considered: 0 },
  limitations: [],
  counts: undefined,
  topology_facts: emptyTopologyNetworkFacts,
});

const LAST_KNOWN_LIMITATIONS = [
  "This is the most recent stored link evidence for a device that reported no links in the latest snapshot. It is last known evidence, not a currently reported link, and does not prove current connectivity or live routing.",
  "Sleepy battery devices routinely age out of router neighbour tables; a missing link in the latest snapshot is not, by itself, evidence of a fault.",
];

function makeLastKnownLink(overrides: Partial<LastKnownLinkAggregate>): LastKnownLinkAggregate {
  return {
    source_ieee: "0xr1",
    target_ieee: "0xsleepy",
    evidence_class: "last_known_link",
    directional: false,
    last_reported_at: "2026-07-04T10:00:00+00:00",
    last_snapshot_id: "snap-old",
    lqi_latest: 88,
    last_relationship: "Child",
    not_seen_in_latest_snapshot: true,
    confidence: "low",
    limitations: LAST_KNOWN_LIMITATIONS,
    ...overrides,
  };
}

/** The home network plus one last known link for a linkless sleepy device. */
const liveDetailWithLastKnown: TopologyEvidenceGraphDetail = makeTopologyEvidenceGraphDetail({
  ...liveDetailWithHistory,
  last_known_links: [makeLastKnownLink({})],
  counts: undefined,
});

const PASSIVE_HINT_LIMITATIONS = [
  "This suggestion comes from passive observations, not topology evidence. It is useful for deciding which devices to inspect together, but it should not be treated as a connection between them.",
  "This does not prove current live routing.",
];

function makePassiveHint(overrides: Partial<PassiveHintAggregate>): PassiveHintAggregate {
  return {
    source_ieee: "0xe1",
    target_ieee: "0xe2",
    evidence_class: "passive_derived_association",
    directional: false,
    confidence: "medium",
    first_seen_at: "2026-07-03T10:00:00+00:00",
    last_seen_at: "2026-07-05T22:00:00+00:00",
    observed_count: 3,
    issue_related: false,
    rules_matched: ["shared_instability_window", "topology_neighbourhood_corroboration"],
    supporting_observations: [
      "3 related instability windows in the last 7 days.",
      "Recent topology evidence also involved a related router neighbourhood.",
    ],
    limitations: PASSIVE_HINT_LIMITATIONS,
    suggested_investigation: [
      "Review both devices' recent availability history around the correlated windows.",
    ],
    ...overrides,
  };
}

/** The home network plus one passive-derived investigation hint. */
const liveDetailWithPassiveHints: TopologyEvidenceGraphDetail = makeTopologyEvidenceGraphDetail({
  ...liveDetailWithHistory,
  passive_hints: [makePassiveHint({})],
  counts: undefined,
});

const INVESTIGATION_GENERIC_LIMITATION =
  "This is a place to look first based on available ZigbeeLens evidence. It is not a root-cause claim and does not prove live routing or current connectivity.";

function makeInvestigationCard(overrides: Partial<InvestigationCard>): InvestigationCard {
  return {
    id: "recent-missing-0xe1",
    type: "recent_missing_cluster",
    priority: "Worth checking",
    score: 8,
    title: "Several recent missing links involve Live Lamp",
    summary:
      "Live Lamp has 3 links that were seen recently but are not present in the latest usable snapshot.",
    why_it_matters:
      "This does not prove a failure, but it may be worth checking if the device has moved, lost power, or has weak mesh conditions.",
    supporting_evidence: ["3 recent missing links involve Live Lamp."],
    limitations: [INVESTIGATION_GENERIC_LIMITATION],
    suggested_next_steps: [
      "Check device power.",
      "Select the device to inspect its evidence details.",
    ],
    device_ieees: ["0xe1", "0xe2"],
    edge_ids: ["hist-neighbor-0xe1|0xe2"],
    primary_device_ieee: "0xe1",
    primary_neighbourhood_ieee: null,
    created_from_evidence_classes: ["historical_neighbor"],
    latest_supporting_evidence_at: "2026-07-04T10:00:00+00:00",
    action_group: "check_power_reporting",
    ...overrides,
  };
}

/** The home network plus one ranked problem-first investigation card. */
const liveDetailWithInvestigations: TopologyEvidenceGraphDetail = makeTopologyEvidenceGraphDetail({
  ...liveDetailWithHistory,
  investigations: [makeInvestigationCard({})],
  investigation_counts: { available: 1, returned: 1 },
  counts: undefined,
});

// Same snapshot, but the link table references an endpoint that appears in
// neither the node list nor the inventory (seen on real networks).
const liveDetailWithGhostEndpoint: TopologyEvidenceGraphDetail = makeTopologyEvidenceGraphDetail({
  ...liveDetailHome,
  latest_snapshot: { ...liveDetailHome.latest_snapshot, link_count: 4 },
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
  counts: undefined,
});

/**
 * A dense network shaped like the real reference deployment: a coordinator
 * plus a clique of routers, giving well over the dense-mode edge threshold,
 * with exactly one real route-table link, varied LQI values, and one router
 * (0xr7) already flagged as needing attention.
 */
function makeDenseNetwork(routerCount = 30): {
  detail: TopologyEvidenceGraphDetail;
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
  const links: TopologyEvidenceGraphDetail["links"] = [];
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
              decision: {
                status: "worth_reviewing",
                priority: "high",
                headline_code: "device_worth_reviewing",
                coverage_label_codes: [],
              },
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
    detail: makeTopologyEvidenceGraphDetail({
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
    }),
    devices,
  };
}

let mockDetail: TopologyEvidenceGraphDetail | null = liveDetailHome;
let mockDevices: DeviceSummary[] = liveDevices;
let mockInventoryAccepted = true;
let mockInventoryLoading = false;
let mockInventoryError: string | null = null;
let mockInventoryRefetch = vi.fn();

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: { version: "0.1.13", topology: { enabled: true } },
  }),
}));

vi.mock("@/hooks/useLiveResource", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useLiveResource")>();
  return {
    useLiveResource: (
      fetcher: () => Promise<unknown>,
      deps: unknown[],
      options?: { enabled?: boolean; refetchOn?: string[] },
    ) => {
      if (options?.enabled === false) {
        return { data: null, loading: false, error: null, refetch: vi.fn() };
      }
      // Device inventory: networkId + scenario with factual inventory events.
      // Snapshot history also uses two deps, so do not key only on deps.length.
      if (
        deps.length === 2 &&
        options?.refetchOn != null &&
        options.refetchOn.includes("dashboard_updated")
      ) {
        return {
          data: mockInventoryAccepted
            ? { items: mockDevices, total: mockDevices.length }
            : null,
          loading: mockInventoryLoading,
          error: mockInventoryError,
          refetch: mockInventoryRefetch,
        };
      }
      // Evidence graph: single networkId dependency.
      if (deps.length === 1) {
        return { data: mockDetail, loading: false, error: null, refetch: vi.fn() };
      }
      // Snapshot history and other live resources use the real hook + API spies.
      return actual.useLiveResource(fetcher, deps, options);
    },
  };
});

/** Minimal device snapshot history so any opened Device details panel has a
 * calm Snapshot history section by default. */
const emptyDeviceHistory: DeviceSnapshotHistoryDetail = {
  network_id: "home",
  device_ieee: "0x0000000000000000",
  friendly_name: null,
  has_current_issue: false,
  availability_tracking: { enabled: true, earliest_observation_at: "2026-07-01T00:00:00+00:00" },
  latest_snapshot: {
    snapshot_id: "snap-live",
    captured_at: "2026-07-06T00:30:00+00:00",
    is_latest: true,
    is_usable: true,
    links_for_device_count: 1,
    route_hints_for_device_count: 0,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: null,
  },
  snapshots: [],
  topology_facts: emptyTopologyDeviceFacts,
};

const emptyDeviceStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0x0000000000000000",
  status: "no_notable_change",
  priority: "none",
  headline_code: "no_notable_signals",
  reasons: [],
  evidence: [],
  limitations: [],
  suggested_checks: [],
  coverage: [],
  timeline: [],
};

beforeEach(() => {
  mockDetail = liveDetailHome;
  mockDevices = liveDevices;
  mockInventoryAccepted = true;
  mockInventoryLoading = false;
  mockInventoryError = null;
  mockInventoryRefetch = vi.fn();
  localStorage.clear();
  vi.spyOn(api, "topologyDeviceSnapshotHistory").mockImplementation(() =>
    Promise.resolve(emptyDeviceHistory),
  );
  vi.spyOn(api, "deviceStory").mockImplementation(() => Promise.resolve(emptyDeviceStory));
  vi.spyOn(api, "deviceCoverage").mockImplementation(() => Promise.resolve([]));
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
    <MemoryRouter initialEntries={[`/investigate/${networkId}`]}>
      <Routes>
        <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function ChangeNetworkButton({ networkId }: { networkId: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(`/investigate/${networkId}`)}>
      Change test network
    </button>
  );
}

async function renderLiveAndWaitForLayout(networkId = "home") {
  const result = renderGraphPage(networkId);
  await screen.findByText("Live Hall Router");
  return result;
}

describe("TopologyGraphPage live mode", () => {
  it("labels the graph as live snapshot data with no sample-data option", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByTestId("graph-mode-badge")).toHaveTextContent("Live topology snapshot");
    // Sample mode has been removed: no data source selector, no prototype copy.
    expect(screen.queryByRole("combobox", { name: /data source/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/sample data/i)).not.toBeInTheDocument();
    expect(screen.getByText("Snapshot status")).toBeInTheDocument();
    expect(screen.getByText("Captured")).toBeInTheDocument();
    expect(screen.getByText("Observed topology nodes").parentElement).toHaveTextContent("3");
    expect(screen.getByText("Recent missing links").parentElement).toHaveTextContent("—");
  });

  it("renders the live devices from the evidence API", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByText("Live Coordinator")).toBeInTheDocument();
    expect(screen.getByText("Live Lamp")).toBeInTheDocument();
    expect(screen.getByText("Live Sleepy Sensor")).toBeInTheDocument();
  });

  it("renders topology while device inventory is still loading without claiming inventory absence", async () => {
    mockInventoryAccepted = false;
    mockInventoryLoading = true;

    await renderLiveAndWaitForLayout();
    expect(
      screen.getByText(
        "Device inventory is still loading. Showing topology evidence without inventory confirmation.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText("Device inventory unavailable — inventory status unknown"),
    ).toBeInTheDocument();
    expect(drawer).not.toHaveTextContent("not in the current device inventory");
  });

  it("renders topology after an initial inventory failure with a contextual retry", async () => {
    mockInventoryAccepted = false;
    mockInventoryError = "request failed";

    await renderLiveAndWaitForLayout();
    expect(
      screen.getByText(
        "Device inventory is unavailable. Showing topology evidence without inventory confirmation.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry device inventory" }));
    expect(mockInventoryRefetch).toHaveBeenCalledTimes(1);
  });

  it("treats an accepted empty inventory as factual absence", async () => {
    mockDevices = [];

    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    expect(screen.getByRole("dialog", { name: /device details/i })).toHaveTextContent(
      "Observed in topology snapshot only — not in the current device inventory",
    );
  });

  it("includes inventory-only devices after an accepted nonempty inventory arrives", async () => {
    mockInventoryAccepted = false;
    const view = await renderLiveAndWaitForLayout();
    expect(screen.queryByText("Live Sleepy Sensor")).not.toBeInTheDocument();

    mockInventoryAccepted = true;
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Live Sleepy Sensor")).toBeInTheDocument();
  });

  it("updates an open device drawer when inventory Retry succeeds", async () => {
    mockInventoryAccepted = false;
    mockInventoryError = "request failed";
    const view = await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(drawer).toHaveTextContent("Device inventory unavailable — inventory status unknown");
    fireEvent.click(screen.getByRole("button", { name: "Retry device inventory" }));
    expect(mockInventoryRefetch).toHaveBeenCalledTimes(1);

    mockInventoryAccepted = true;
    mockInventoryError = null;
    mockDevices = liveDevices.map((device) =>
      device.ieee_address === "0xe1"
        ? {
            ...device,
            friendly_name: "Accepted Kitchen Router",
            device_type: "Router",
            decision: {
              status: "review_first",
              priority: "high",
              headline_code: "device_review_first",
              coverage_label_codes: [],
            },
          }
        : device,
    );
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await within(drawer).findByText("Accepted Kitchen Router")).toBeInTheDocument();
    expect(drawer).toHaveTextContent("Router");
    expect(drawer).toHaveTextContent("Needs attention");
    expect(drawer).toHaveTextContent("In Zigbee2MQTT device inventory");
  });

  it("closes an open device drawer when the selected identity disappears", async () => {
    const view = await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    expect(screen.getByRole("dialog", { name: /device details/i })).toBeInTheDocument();

    const links = liveDetailHome.links.filter(
      (link) => link.source_ieee !== "0xe1" && link.target_ieee !== "0xe1",
    );
    mockDevices = liveDevices.filter((device) => device.ieee_address !== "0xe1");
    mockDetail = makeTopologyEvidenceGraphDetail({
      ...liveDetailHome,
      latest_snapshot: {
        ...liveDetailHome.latest_snapshot,
        end_device_count: 0,
        link_count: links.length,
      },
      nodes: liveDetailHome.nodes.filter((node) => node.ieee_address !== "0xe1"),
      links,
      counts: undefined,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /device details/i })).not.toBeInTheDocument(),
    );
  });

  it("updates an open edge drawer and closes it if the edge disappears", async () => {
    const view = await renderLiveAndWaitForLayout();
    fireEvent.click(
      await screen.findByLabelText("Route hint from Live Hall Router to Live Coordinator"),
    );
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("Route hints observed").nextElementSibling).toHaveTextContent(
      "2",
    );

    const refreshedLinks = liveDetailHome.links.map((link) =>
      link.source_ieee === "0xr1" && link.target_ieee === "0xc0"
        ? { ...link, route_count: 7 }
        : link,
    );
    mockDetail = makeTopologyEvidenceGraphDetail({
      ...liveDetailHome,
      links: refreshedLinks,
      counts: undefined,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(within(drawer).getByText("Route hints observed").nextElementSibling).toHaveTextContent(
      "7",
    );

    mockDetail = makeTopologyEvidenceGraphDetail({
      ...liveDetailHome,
      links: refreshedLinks.map((link) => ({ ...link, route_count: 0 })),
      counts: undefined,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /link details/i })).not.toBeInTheDocument(),
    );
  });

  it("clears an open drawer when the network route changes", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <ChangeNetworkButton networkId="home2" />
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("Live Hall Router");
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    expect(screen.getByRole("dialog", { name: /device details/i })).toBeInTheDocument();

    mockDetail = liveDetailLimited;
    mockDevices = [];
    await user.click(screen.getByRole("button", { name: "Change test network" }));

    expect(
      await screen.findByText(/did not provide usable node\/link layout data/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /device details/i })).not.toBeInTheDocument();
  });

  it("retains accepted inventory evidence after a refresh failure", async () => {
    const view = await renderLiveAndWaitForLayout();
    expect(screen.getByText("Live Sleepy Sensor")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(drawer).toHaveTextContent("In Zigbee2MQTT device inventory");

    mockInventoryError = "refresh failed";
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      screen.getByText(
        "Device inventory could not be refreshed. Showing the last loaded inventory confirmation.",
      ),
    ).toBeInTheDocument();
    expect(drawer).toHaveTextContent("In Zigbee2MQTT device inventory");
    expect(drawer).toHaveTextContent("End device");
    expect(drawer).toHaveTextContent("Healthy");
    expect(screen.getByRole("button", { name: "Retry device inventory" })).toBeInTheDocument();
  });

  it("maps neighbour links to latest_snapshot_neighbor edges, merging directions", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    // One line per pair: the route-covered pair (0xr1–0xc0) draws only its
    // route edge, so a single neighbour edge (0xr1–0xe1) renders by default.
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(1);
    });
    // With route hints off, both merged neighbour edges draw.
    await clickConnectionCheckbox(user, /route hints/i);
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

  it("only offers evidence filters that live data can produce", async () => {
    await renderLiveAndWaitForLayout();
    // No historical evidence in this response: recent missing links disabled.
    expect(connectionCheckbox(/recent missing links/i)).toBeDisabled();
    expect(screen.queryByText(/previously seen/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "No previous complete snapshots are available, so recent missing links could not be evaluated.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No previous complete snapshots are available, so last known links could not be evaluated.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Live Sleepy Sensor")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/every device has link evidence/i);
    // No passive hints in this response: suggested investigation links
    // disabled with honest empty copy.
    expect(
      connectionCheckbox(/suggested investigation links/i),
    ).toBeDisabled();
    expect(
      screen.getByText("No suggested investigation links are available for this network yet."),
    ).toBeInTheDocument();
    // The stale control is gone with sample mode.
    expect(
      screen.queryByRole("checkbox", { name: /stale \/ low-confidence/i }),
    ).not.toBeInTheDocument();
  });

  it("disables route hints with capture guidance when the snapshot has no route tables", async () => {
    mockDetail = makeTopologyEvidenceGraphDetail({
      ...liveDetailHome,
      links: liveDetailHome.links!.map((link) => ({ ...link, route_count: 0 })),
      counts: undefined,
    });
    const { container } = await renderLiveAndWaitForLayout();
    expect(connectionCheckbox(/route hints/i)).toBeDisabled();
    expect(screen.getByText(/No route hints in the latest snapshot/)).toBeInTheDocument();
    // Guidance points at capturing a new snapshot, never at live-routing claims.
    expect(screen.getByText(/capture a new topology snapshot/i)).toBeInTheDocument();
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(0);
  });

  it("explains route hints vs best neighbour links behind a click", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    expect(screen.queryByTestId("connections-explainer")).not.toBeInTheDocument();

    await openDrawMoreLinks(user);
    await user.click(screen.getByTestId("connections-explainer-toggle"));
    const text = screen.getByTestId("connections-explainer").textContent ?? "";
    expect(text).toMatch(/neighbour table/i);
    expect(text).toMatch(/routing table/i);
    expect(text).toMatch(/link quality/i);
    expect(text).toMatch(/not proof of current live routing/i);
    expect(text).toMatch(/one line per pair/i);
    expect(text).toMatch(/recent missing links/i);
    expect(text).toMatch(/does not prove a failure/i);
    expect(text).toMatch(/suggested investigation links/i);
    expect(text).toMatch(/all neighbour links/i);
    // Wording guardrails hold inside the explainer too.
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/current route\b/i);
    expect(text).not.toMatch(/actual path/i);
    expect(text).not.toMatch(/connected through/i);

    await user.click(screen.getByTestId("connections-explainer-toggle"));
    expect(screen.queryByTestId("connections-explainer")).not.toBeInTheDocument();
  });

  it("enables route hints with the standard helper when route tables exist", async () => {
    await renderLiveAndWaitForLayout();
    const checkbox = connectionCheckbox(/route hints/i);
    expect(checkbox).toBeEnabled();
    expect(checkbox).toBeChecked();
    expect(screen.queryByText(/No route hints in the latest snapshot/)).not.toBeInTheDocument();
  });

  it("opens the neighbour link details panel with snapshot facts and safe wording", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    // This pair is route-covered, so its neighbour line draws once route
    // hints are off (one line per pair while both are on).
    await clickConnectionCheckbox(user, /route hints/i);
    const edge = await screen.findByLabelText(
      "Latest snapshot neighbour link between Live Hall Router and Live Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("Latest snapshot neighbour link")).toBeInTheDocument();
    expect(within(drawer).getByText("What this line means")).toBeInTheDocument();
    expect(within(drawer).getByText("Why ZigbeeLens drew it")).toBeInTheDocument();
    expect(within(drawer).getByText("Supporting evidence")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText(/latest topology snapshot reported a neighbour relationship/i),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("Captured at")).toBeInTheDocument();
    expect(within(drawer).getByText("Observed relationship")).toBeInTheDocument();
    expect(within(drawer).getByText("Parent")).toBeInTheDocument();
    expect(within(drawer).getByText("Link quality (latest)")).toBeInTheDocument();
    expect(within(drawer).getByText("140")).toBeInTheDocument();
    // Quiet neighbour links do not need a separate "What this does not prove".
    expect(within(drawer).queryByText("What this does not prove")).not.toBeInTheDocument();
  });

  it("qualifies route-table evidence in the route link details panel", async () => {
    await renderLiveAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Route hint from Live Hall Router to Live Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("What this does not prove")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/possible next-hop evidence at capture time/i).length,
    ).toBeGreaterThan(0);
    expect(within(drawer).getByText("Route hints observed").nextElementSibling).toHaveTextContent(
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

  it("shows recorded diagnostic stats in the node drawer", async () => {
    mockDevices = liveDevices.map((device) =>
      device.ieee_address === "0xe2" ? { ...device, battery: 12 } : device,
    );
    const detailWithStats: TopologyEvidenceGraphDetail = {
      ...liveDetailWithHistory,
      device_stats: {
        "0xe2": {
          snapshots_with_links: 2,
          last_router_link_at: "2026-07-06T00:00:00+00:00",
          last_router_link_partner: "0xr1",
          offline_events_24h: 1,
          offline_events_7d: 3,
          last_offline_at: "2026-07-06T02:00:00+00:00",
        },
      },
      device_stats_window: { days: 7, max_snapshots: 10, snapshots_considered: 4 },
    };
    mockDetail = detailWithStats;
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe2"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Diagnostic stats")).toBeInTheDocument();
    expect(within(drawer).getByText("Last seen")).toBeInTheDocument();
    expect(within(drawer).getByText("Battery level")).toBeInTheDocument();
    expect(within(drawer).getByText("12%")).toBeInTheDocument();
    expect(within(drawer).getByText("Snapshots with links (last 7 days)")).toBeInTheDocument();
    expect(within(drawer).getByText("2 of 4")).toBeInTheDocument();
    expect(within(drawer).getByText("Last router link observed")).toBeInTheDocument();
    expect(within(drawer).getByText(/to Live Hall Router/)).toBeInTheDocument();
    expect(within(drawer).getByText("Offline events (24 h)")).toBeInTheDocument();
    expect(within(drawer).getByText("Offline events (7 days)")).toBeInTheDocument();
    // The old prose verdict section is gone.
    expect(within(drawer).queryByText("How ZigbeeLens reads this")).not.toBeInTheDocument();
  });

  it("never invents stats: unknown values produce no rows, not zeroes", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    const text = drawer.textContent ?? "";
    // 0xe1 has no recorded battery and no backend stats entry.
    expect(text).not.toMatch(/battery level/i);
    expect(text).not.toMatch(/offline events/i);
    expect(text).not.toMatch(/last router link/i);
  });

  it("shows an honest limited state without fake zeroes", async () => {
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
    // No graph, no fabricated fallback data.
    expect(container.querySelectorAll(".mesh-edge")).toHaveLength(0);
    expect(screen.queryByTestId("mesh-evidence-graph")).not.toBeInTheDocument();
  });

  it("shows a waiting state when no snapshot exists", async () => {
    mockDetail = makeTopologyEvidenceGraphDetail({
      network_id: "home2",
      network_name: "Home 2",
      latest_snapshot: null,
      nodes: [],
      links: [],
      inventory: { device_count: 5, router_count: 1, end_device_count: 3 },
      layout_available: false,
    });
    renderGraphPage("home2");
    expect(await screen.findByText("Waiting for a topology snapshot")).toBeInTheDocument();
    expect(
      screen.getByText(/missing topology data is not an incident by itself/i),
    ).toBeInTheDocument();
  });

  it("creates a clearly labelled placeholder node for a link endpoint absent from accepted inventory and node list", async () => {
    mockDetail = liveDetailWithGhostEndpoint;
    await renderLiveAndWaitForLayout();
    const ghost = screen.getByTestId("mesh-node-0xghost");
    expect(ghost).toBeInTheDocument();
    expect(within(ghost).getByText("Unknown role")).toBeInTheDocument();

    fireEvent.click(ghost);
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(
      within(drawer).getByText(
        "Referenced by topology links only — not in the current device inventory or node list",
      ),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(
        /referenced by 1 topology link entry in the latest snapshot, but no node details were reported/i,
      ),
    ).toBeInTheDocument();
    // No inventory data means no fabricated stats rows.
    expect(within(drawer).queryByText("Last seen")).not.toBeInTheDocument();
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
    expect(screen.getByRole("group", { name: /graph view/i })).toBeInTheDocument();
    await openDrawMoreLinks();
    expect(screen.getByRole("group", { name: /connections to show/i })).toBeInTheDocument();
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

  it("keeps saved positions applied across connection toggles and drawer open/close", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      positionStorageKey("home", "smart"),
      JSON.stringify({ "0xr1": { x: 4321, y: 1234 } }),
    );
    const { container } = await renderLiveAndWaitForLayout();

    await clickConnectionCheckbox(user, /route hints/i);
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

describe("TopologyGraphPage layout stability", () => {
  it("does not move nodes or remount the graph on a routine refetch with unchanged data", async () => {
    const view = renderGraphPage();
    await screen.findByText("Live Hall Router");
    const flowEl = view.container.querySelector(".react-flow");
    expect(flowEl).not.toBeNull();
    const before = nodePosition(view.container, "0xr1");

    // Simulate a routine API refetch: identical content, fresh object identity.
    mockDetail = structuredClone(liveDetailHome);
    view.rerender(
      <MemoryRouter initialEntries={["/investigate/home"]}>
        <Routes>
          <Route path="/investigate/:networkId" element={<TopologyGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("Live Hall Router");
    expect(nodePosition(view.container, "0xr1")).toBe(before);
    // Same React Flow DOM node — no remount, so fitView cannot have re-fired.
    expect(view.container.querySelector(".react-flow")).toBe(flowEl);
  });

  it("does not move nodes when connection controls change or a drawer opens", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByText("Live Hall Router");
    const flowEl = container.querySelector(".react-flow");
    const before = nodePosition(container, "0xr1");

    await clickConnectionCheckbox(user, /route hints/i);
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });

    expect(nodePosition(container, "0xr1")).toBe(before);
    // No remount either: fitView cannot have re-fired.
    expect(container.querySelector(".react-flow")).toBe(flowEl);
  });
});

describe("TopologyGraphPage focused view on large graphs", () => {
  beforeEach(() => {
    const dense = makeDenseNetwork();
    mockDetail = dense.detail;
    mockDevices = dense.devices;
  });

  function connectionsPanel() {
    return connectionControlsPanel();
  }

  it("renders human-readable connection controls with the Troubleshooting preset defaults", async () => {
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    expect(screen.getByRole("combobox", { name: /graph view preset/i })).toHaveValue(
      "troubleshooting",
    );
    const panel = connectionsPanel();

    expect(panel.getByRole("checkbox", { name: /route hints/i })).toBeChecked();
    expect(panel.getByRole("checkbox", { name: /best neighbour links/i })).toBeChecked();
    expect(panel.getByRole("checkbox", { name: /all neighbour links/i })).not.toBeChecked();
    expect(panel.getByRole("checkbox", { name: /old or uncertain links/i })).not.toBeChecked();
    // "Devices with issues" is no longer a control: issue devices are always
    // highlighted, so the checkbox is gone.
    expect(
      panel.queryByRole("checkbox", { name: /devices with issues/i }),
    ).not.toBeInTheDocument();

    // Link-type explanations live in the explainer, not under the checkboxes.
    expect(
      panel.queryByText(/a focused set of observed neighbour links/i),
    ).not.toBeInTheDocument();
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
      panel.getByText(
        "No previous complete snapshots are available, so recent missing links could not be evaluated.",
      ),
    ).toBeInTheDocument();
    expect(panel.queryByRole("checkbox", { name: /selected device links/i })).not.toBeInTheDocument();

    // No passive hints in this fixture: disabled with honest empty copy.
    expect(
      panel.getByRole("checkbox", { name: /suggested investigation links/i }),
    ).toBeDisabled();
    expect(
      panel.getByText("No suggested investigation links are available for this network yet."),
    ).toBeInTheDocument();
  });

  it("draws a focused subset by default — not empty, not the full hairball", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");

    expect(screen.queryByTestId("dense-graph-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("focused-view-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("all-drawn-note")).not.toBeInTheDocument();

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

  it("always highlights issue devices without flooding the graph with links", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");

    // The flagged device 0xr7 is highlighted by default — no toggle needed —
    // and issue emphasis stays node-only: no extra neighbour edges appear.
    await waitFor(() => {
      expect(
        container.querySelector('.react-flow__node[data-id="0xr7"]'),
      ).toHaveClass("mesh-node--issue-highlight");
    });
    expect(container.querySelectorAll(".mesh-node--issue-highlight")).toHaveLength(1);
    const before = container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length;

    // Selecting the issue node still reveals its full evidence neighbourhood.
    fireEvent.click(screen.getByTestId("mesh-node-0xr7"));
    await screen.findByRole("dialog", { name: /device details/i });
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor").length,
      ).toBeGreaterThan(before);
    });
  });

  it("deselecting a node restores the graph", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
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

    // Clicking the selected node again deselects: drawer closes, focused
    // neighbourhood collapses back to the default subset, muting clears.
    fireEvent.click(screen.getByTestId("mesh-node-0xr5"));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /device details/i })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(
        beforeCount,
      );
    });
    expect(container.querySelectorAll(".mesh-node--muted")).toHaveLength(0);
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
        "Latest snapshot neighbour link between Dense Router 5 and Dense Router 4",
      ),
    ).toBeInTheDocument();
    expect(nodePosition(container, "0xr5")).toBe(beforePos);
  });

  it("All neighbour links renders the full snapshot evidence, and off restores the subset", async () => {
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
    // No inline warning under the checkbox — the explainer carries the copy.
    expect(screen.queryByTestId("all-neighbour-links-warning")).not.toBeInTheDocument();
    // Route hints stay visible alongside.
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);

    await user.click(allLinks);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(
        subsetCount,
      );
    });
    // Connection toggles never move nodes.
    expect(nodePosition(container, "0xr5")).toBe(beforePos);
  });

  it("edge drawer keeps full metadata for visible edges in dense mode", async () => {
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const edge = await screen.findByLabelText(
      "Route hint from Dense Router 0 to Dense Coordinator",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("Route hints observed").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
  });

  it("small graphs use the same connection panel and draw all enabled evidence", async () => {
    mockDetail = liveDetailHome;
    mockDevices = liveDevices;
    const { container } = renderGraphPage();
    await screen.findByText("Live Hall Router");
    // One control model everywhere: no separate evidence-filter panel.
    expect(screen.getByRole("group", { name: /graph view/i })).toBeInTheDocument();
    await openDrawMoreLinks();
    expect(screen.getByRole("group", { name: /connections to show/i })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /evidence filters/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("focused-view-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("all-drawn-note")).not.toBeInTheDocument();
    await waitFor(() => {
      // One line per pair: the route-covered pair draws only its route edge,
      // the remaining pair draws its neighbour edge.
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(1);
      expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);
    });
  });

  it("persists connection choices per network and restores them", async () => {
    const user = userEvent.setup();
    const first = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const allLinksToggle = () =>
      connectionControlsPanel().getByRole("checkbox", {
        name: /all neighbour links/i,
      });
    expect(allLinksToggle()).not.toBeChecked();
    await user.click(allLinksToggle());
    expect(allLinksToggle()).toBeChecked();
    first.unmount();

    // A fresh visit to the same network restores the choice.
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    expect(allLinksToggle()).toBeChecked();
  });

  it("different networks keep independent connection choices", async () => {
    localStorage.setItem(
      "zigbeelens.meshGraph.connectionControls.v1.other",
      JSON.stringify({ routeHints: false }),
    );
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionControlsPanel();
    // "home" has no saved choices: defaults apply despite "other" storage.
    expect(panel.getByRole("checkbox", { name: /route hints/i })).toBeChecked();
  });

  it("falls back to defaults when saved connection choices are corrupt", async () => {
    localStorage.setItem("zigbeelens.meshGraph.connectionControls.v1.home", "{corrupt");
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionControlsPanel();
    expect(panel.getByRole("checkbox", { name: /route hints/i })).toBeChecked();
    expect(panel.getByRole("checkbox", { name: /all neighbour links/i })).not.toBeChecked();
  });

  it("reset connection choices returns to the Troubleshooting preset", async () => {
    const user = userEvent.setup();
    renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = () => connectionControlsPanel();
    await user.click(panel().getByRole("checkbox", { name: /all neighbour links/i }));
    expect(panel().getByRole("checkbox", { name: /all neighbour links/i })).toBeChecked();

    await user.click(screen.getByRole("button", { name: /reset connection choices/i }));
    expect(panel().getByRole("checkbox", { name: /all neighbour links/i })).not.toBeChecked();
    expect(screen.getByRole("combobox", { name: /graph view preset/i })).toHaveValue(
      "troubleshooting",
    );
    expect(
      localStorage.getItem("zigbeelens.meshGraph.connectionControls.v1.home"),
    ).not.toBeNull();
    expect(localStorage.getItem(viewPresetStorageKey("home"))).toBe("troubleshooting");
  });
});

describe("TopologyGraphPage graph view presets", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithHistory;
    mockDevices = liveDevices;
  });

  it("defaults new users to the Troubleshooting preset", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.getByRole("combobox", { name: /graph view preset/i })).toHaveValue(
      "troubleshooting",
    );
    expect(connectionCheckbox(/recent missing links/i)).toBeChecked();
    expect(connectionCheckbox(/suggested investigation links/i)).toBeDisabled();
  });

  it("switches to Quiet view and hides historical edges", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await selectGraphViewPreset(user, "quiet_view");
    expect(screen.getByRole("combobox", { name: /graph view preset/i })).toHaveValue("quiet_view");
    expect(connectionCheckbox(/route hints/i)).not.toBeChecked();
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    });
    expect(localStorage.getItem(viewPresetStorageKey("home"))).toBe("quiet_view");
  });

  it("restores a saved preset on revisit", async () => {
    localStorage.setItem(viewPresetStorageKey("home"), "battery_devices");
    await renderLiveAndWaitForLayout();
    expect(screen.getByRole("combobox", { name: /graph view preset/i })).toHaveValue(
      "battery_devices",
    );
    expect(connectionCheckbox(/route hints/i)).not.toBeChecked();
    expect(connectionCheckbox(/best neighbour links/i)).toBeChecked();
    expect(connectionCheckbox(/recent missing links/i)).not.toBeChecked();
  });
});

describe("TopologyGraphPage historical evidence (live)", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithHistory;
    mockDevices = liveDevices;
  });

  it("enables Recent missing links when historical evidence exists, on with Troubleshooting preset", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const checkbox = connectionCheckbox(/recent missing links/i);
    expect(checkbox).toBeEnabled();
    expect(checkbox).toBeChecked();
    expect(
      screen.getByText("2 recent missing links are available from evaluated history."),
    ).toBeInTheDocument();
    // The old label is gone everywhere.
    expect(screen.queryByText(/previously seen/i)).not.toBeInTheDocument();
    // Troubleshooting preset: historical edges render by default.
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
      expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(1);
    });
    // No passive-derived edges are ever created from live data.
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(0);
  });

  it("renders dotted historical edges when Recent missing links is enabled", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    // Already on with Troubleshooting; toggle off then on to exercise the control.
    await clickConnectionCheckbox(user, /recent missing links/i);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    });
    await clickConnectionCheckbox(user, /recent missing links/i);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    expect(container.querySelectorAll(".mesh-edge--historical_route")).toHaveLength(1);
    // Latest edges are never duplicated as historical. (One neighbour edge:
    // the route-covered pair draws only its route edge.)
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_neighbor")).toHaveLength(1);
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
      screen.getAllByTitle("Links reported in the latest topology snapshot.").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByTitle(
        "Links seen in recent previous snapshots but not present in the latest usable snapshot.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByTitle("Devices ZigbeeLens knows from Zigbee2MQTT inventory."),
    ).toBeInTheDocument();
  });

  it("renders the evidence coverage strip near metrics when coverage exists", async () => {
    mockDetail = {
      ...liveDetailWithHistory,
      topology_facts: {
        ...emptyTopologyNetworkFacts,
        coverage: [
          {
            dimension: "route_hints",
            state: "not_observed",
            label_code: "route_hints_unavailable",
          },
          {
            dimension: "availability",
            state: "off",
            label_code: "availability_tracking_off",
          },
        ],
      },
    };
    await renderLiveAndWaitForLayout();
    const strip = screen.getByTestId("evidence-coverage-strip");
    expect(strip).toHaveTextContent("Evidence coverage");
    expect(within(strip).getByText("Availability tracking off")).toBeInTheDocument();
    expect(within(strip).getByText("Route hints unavailable")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/route_hints_unavailable/);
  });

  it("does not render an empty evidence coverage strip", async () => {
    mockDetail = {
      ...liveDetailWithHistory,
      topology_facts: emptyTopologyNetworkFacts,
    };
    await renderLiveAndWaitForLayout();
    expect(screen.queryByTestId("evidence-coverage-strip")).not.toBeInTheDocument();
  });

  it("renders Evidence coverage once in the device details drawer", async () => {
    const coverageSpy = vi.spyOn(api, "deviceCoverage").mockResolvedValue([
      {
        dimension: "availability",
        state: "off",
        label_code: "availability_tracking_off",
      },
      {
        dimension: "ha_enrichment",
        state: "not_configured",
        label_code: "ha_areas_not_linked",
      },
    ]);
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(coverageSpy).toHaveBeenCalledWith("home", "0xr1");
    expect(await within(drawer).findByText("Availability: tracking off")).toBeInTheDocument();
    expect(within(drawer).getByText("HA area: missing")).toBeInTheDocument();
    expect(within(drawer).getAllByText("Evidence coverage")).toHaveLength(1);
  });

  it("shows unavailable device coverage when the coverage API fails", async () => {
    vi.spyOn(api, "deviceCoverage").mockRejectedValue(new Error("network error"));
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(await within(drawer).findByText("Evidence coverage")).toBeInTheDocument();
    expect(
      within(drawer).getByText("Device coverage is currently unavailable."),
    ).toBeInTheDocument();
    expect(within(drawer).queryByText("network error")).not.toBeInTheDocument();
  });

  it("keeps network and device HA coverage wording distinct", async () => {
    mockDetail = {
      ...liveDetailWithHistory,
      topology_facts: {
        ...emptyTopologyNetworkFacts,
        coverage: [
          {
            dimension: "ha_enrichment",
            state: "not_configured",
            label_code: "ha_areas_not_linked",
          },
        ],
      },
    };
    vi.spyOn(api, "deviceCoverage").mockResolvedValue([
      {
        dimension: "ha_enrichment",
        state: "not_configured",
        label_code: "ha_areas_not_linked",
      },
    ]);
    await renderLiveAndWaitForLayout();
    const strip = screen.getByTestId("evidence-coverage-strip");
    expect(within(strip).getByText("HA areas not linked")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(await within(drawer).findByText("HA area: missing")).toBeInTheDocument();
  });

  it("does not let a stale device coverage response overwrite a newly selected device", async () => {
    let resolveFirst: ((value: DataCoverageDto[]) => void) | undefined;
    const firstPromise = new Promise<DataCoverageDto[]>((resolve) => {
      resolveFirst = resolve;
    });
    const coverageSpy = vi
      .spyOn(api, "deviceCoverage")
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValueOnce([
        {
          dimension: "availability",
          state: "available",
          label_code: "availability_available",
        },
      ]);

    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    fireEvent.click(screen.getByTestId("mesh-node-0xe2"));
    resolveFirst?.([
      {
        dimension: "availability",
        state: "off",
        label_code: "availability_tracking_off",
      },
    ]);
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(await within(drawer).findByText("Availability: available")).toBeInTheDocument();
    expect(within(drawer).queryByText("Availability: tracking off")).not.toBeInTheDocument();
    expect(coverageSpy).toHaveBeenCalledWith("home", "0xe2");
  });

  it("frames the historical neighbour details panel as previous-snapshot evidence, never live routing", async () => {
    await renderLiveAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Recent missing link between Live Lamp and Live Sleepy Sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getAllByText("Recent missing link").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("What this line means")).toBeInTheDocument();
    expect(within(drawer).getByText("What this does not prove")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/seen recently but is not in the latest usable snapshot|observed in a recent previous topology snapshot/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(/does not prove a failure|does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    // Historical aggregate facts.
    expect(within(drawer).getByText("First observed")).toBeInTheDocument();
    expect(within(drawer).getByText("Last observed")).toBeInTheDocument();
    expect(within(drawer).getByText("Times observed").nextElementSibling).toHaveTextContent("5");
    expect(within(drawer).getByText("Snapshots with this link").nextElementSibling).toHaveTextContent("3");
    expect(within(drawer).getByText("Link quality min").nextElementSibling).toHaveTextContent("60");
    expect(within(drawer).getByText("Link quality median").nextElementSibling).toHaveTextContent("75");
    expect(within(drawer).getByText("Link quality max").nextElementSibling).toHaveTextContent("90");
    // Neighbour evidence does not invent route fields.
    expect(within(drawer).queryByText("Route hints observed")).not.toBeInTheDocument();
    // No live-routing claims.
    expect(within(drawer).queryByText(/currently connected/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/lost connection/i)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/broken link/i)).not.toBeInTheDocument();
  });

  it("frames the historical route details panel with previous route-table evidence and counts", async () => {
    await renderLiveAndWaitForLayout();
    const edge = await screen.findByLabelText(
      "Recent missing route hint from Live Hall Router to Live Lamp",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("Recent missing route")).toBeInTheDocument();
    expect(within(drawer).getByText("What this does not prove")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(
        /route-table evidence was observed in a recent previous topology snapshot/i,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(/does not prove current live routing/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText("Route hints observed").nextElementSibling,
    ).toHaveTextContent("2");
    expect(within(drawer).getByText("Last route hint count").nextElementSibling).toHaveTextContent(
      "3",
    );
    expect(within(drawer).queryByText(/current route/i)).not.toBeInTheDocument();
  });

  it("adds a recent missing topology section to the node drawer", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Recent missing evidence")).toBeInTheDocument();
    // 0xe1 touches the historical neighbour and the historical route.
    expect(
      within(drawer).getByText(/2 recent missing links in the selected history window/i),
    ).toBeInTheDocument();
    expect(within(drawer).getByText(/last seen in topology evidence/i)).toBeInTheDocument();
  });

  it("omits recent missing evidence when a device has none", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xc0"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).queryByText("Recent missing evidence")).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/no recent missing/i)).not.toBeInTheDocument();
  });

  it("qualifies rather than overclaims when the latest layout is limited", async () => {
    const limitedNeighborCopy =
      "This neighbour link was observed in a recent previous topology snapshot. The latest snapshot has limited topology evidence, so absence from the latest graph is not meaningful by itself.";
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
    await renderLiveAndWaitForLayout();
    openDrawMoreLinks();
    expect(
      screen.getByText(
        "The latest topology layout is limited, so recent missing links cannot be measured reliably.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The latest topology layout is limited, so absence from it cannot be assessed for last known links.",
      ),
    ).toBeInTheDocument();
    const edge = await screen.findByLabelText(
      "Recent missing link between Live Lamp and Live Sleepy Sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /link details/i });
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
        /the latest snapshot has limited topology evidence, so absence from the latest graph is not meaningful by itself/i,
      ),
    ).toBeInTheDocument();
  });
});

describe("TopologyGraphPage historical evidence on large graphs", () => {
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
      last_known_links: [],
      last_known_window: {
        snapshots_considered: 2,
        earliest_captured_at: "2026-07-01T10:00:00+00:00",
        latest_captured_at: "2026-07-04T10:00:00+00:00",
      },
      passive_hints: [],
      passive_hint_window: { days: 7, event_window_minutes: 5, min_repeated_windows: 2 },
      investigations: [],
      investigation_counts: { available: 0, returned: 0 },
      device_stats: {},
      device_stats_window: { days: 7, max_snapshots: 10, snapshots_considered: 0 },
      limitations: [],
      counts: {
        latest_snapshot_neighbor_edges: 435,
        latest_snapshot_route_edges: 1,
        historical_neighbor_edges: neighbors.length,
        historical_route_edges: 0,
        recent_missing_link_count_total: neighbors.length,
        last_known_link_count: 0,
        passive_hint_count_available: 0,
        passive_hint_count_total: 0,
        passive_hint_count_drawn: null,
        hidden_for_readability: null,
        known_inventory_devices: dense.devices.length,
        observed_topology_nodes: 31,
      },
      topology_facts: emptyTopologyNetworkFacts,
    };
    return { detail, devices: dense.devices };
  }

  beforeEach(() => {
    const dense = makeDenseWithHistory();
    mockDetail = dense.detail;
    mockDevices = dense.devices;
  });

  it("keeps historical edges out of the Quiet view preset", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    await selectGraphViewPreset(user, "quiet_view");
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    });
    expect(screen.queryByTestId("dense-graph-banner")).not.toBeInTheDocument();
  });

  it("shows historical edges in dense mode only when Recent missing links is enabled", async () => {
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    const panel = connectionControlsPanel();

    const checkbox = panel.getByRole("checkbox", { name: /recent missing links/i });
    expect(checkbox).toBeEnabled();
    expect(checkbox).toBeChecked();
    expect(panel.queryByText(/previously seen/i)).not.toBeInTheDocument();
    // Enabled controls carry no helper copy — the explainer describes them.
    expect(
      panel.queryByText(/no recent missing links in the selected history window/i),
    ).not.toBeInTheDocument();

    await user.click(checkbox);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    });

    await user.click(checkbox);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(2);
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

    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");

    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(3);
    });
  });

  it("renders no concealment or live-routing phrasing anywhere on the page", async () => {
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
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
    const user = userEvent.setup();
    const { container } = renderGraphPage();
    await screen.findByTestId("mesh-node-0xr5");
    await selectGraphViewPreset(user, "quiet_view");
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
        "Recent missing link between Dense Router 1 and Dense Router 20",
      ),
    ).toBeInTheDocument();
    expect(nodePosition(container, "0xr20")).toBe(beforePos);
  });
});

describe("TopologyGraphPage passive-derived investigation hints", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithPassiveHints;
    mockDevices = liveDevices;
  });

  const investigationToggle = () => connectionCheckbox(/suggested investigation links/i);

  it("enables the control when passive hints exist, on with Troubleshooting preset", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    expect(investigationToggle()).toBeEnabled();
    expect(investigationToggle()).toBeChecked();
    // Enabled controls carry no helper copy — the explainer describes them.
    expect(
      screen.queryByText("No suggested investigation links are available for this network yet."),
    ).not.toBeInTheDocument();
    // On with Troubleshooting: passive edges render by default.
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(1);
    });
  });

  it("draws ghost passive edges without arrowheads when enabled", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    // Already on; toggle off then on to exercise the control.
    await clickConnectionCheckbox(user, /suggested investigation links/i);
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--passive_derived_association"),
      ).toHaveLength(0);
    });
    await clickConnectionCheckbox(user, /suggested investigation links/i);
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--passive_derived_association"),
      ).toHaveLength(1);
    });
    const path = container.querySelector(
      ".mesh-edge--passive_derived_association .react-flow__edge-path",
    ) as SVGPathElement;
    expect(path).not.toBeNull();
    // Ghost / faint investigation styling: fainter and thinner than every
    // topology evidence style, subtle dotted dash.
    expect(path.style.opacity).toBe("0.45");
    expect(path.style.strokeDasharray).toBe("1 8");
    // Never a route arrowhead: passive hints are not directional.
    expect(path.getAttribute("marker-end")).toBeNull();

    // Toggling off removes them again.
    await user.click(investigationToggle());
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--passive_derived_association"),
      ).toHaveLength(0);
    });
  });

  it("opens a drawer that explains the hint without topology or routing claims", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await openDrawMoreLinks(user);
    const edge = await screen.findByLabelText(
      "Suggested investigation link between Live Lamp and Live Sleepy Sensor",
    );
    fireEvent.click(edge);
    const drawer = screen.getByRole("dialog", { name: /suggested investigation link/i });
    // Required sections.
    expect(within(drawer).getByText("What this line means")).toBeInTheDocument();
    expect(within(drawer).getByText("Why ZigbeeLens drew it")).toBeInTheDocument();
    expect(within(drawer).getByText("Supporting evidence")).toBeInTheDocument();
    expect(within(drawer).getByText("What this does not prove")).toBeInTheDocument();
    expect(within(drawer).getByText("Suggested checks")).toBeInTheDocument();
    // Cautious framing.
    expect(
      within(drawer).getByText(/worth investigating together/i),
    ).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/not topology evidence/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getByText("This does not prove current live routing."),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(/repeatedly showed instability around the same time/i),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(
        /recent topology evidence also places these devices in a related router neighbourhood/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(/3 related instability windows in the last 7 days/i),
    ).toBeInTheDocument();
    // No forbidden wording.
    const text = drawer.textContent ?? "";
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/child device/i);
    expect(text).not.toMatch(/current route\b/i);
    expect(text).not.toMatch(/currently routed/i);
    expect(text).not.toMatch(/actual path/i);
    expect(text).not.toMatch(/connected through/i);
    expect(text).not.toMatch(/caused by/i);
    expect(text).not.toMatch(/failed because/i);
    expect(text).not.toMatch(/broken link/i);
    expect(text).not.toMatch(/lost link/i);
    expect(text).not.toMatch(/same parent/i);
  });

  it("adds a suggested investigation section to the node drawer when hints touch a device", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Suggested investigation links")).toBeInTheDocument();
    expect(
      within(drawer).getByText(
        /1 passive-derived investigation hint involves this device\. These are not topology links or proof of live routing\./i,
      ),
    ).toBeInTheDocument();
  });

  it("omits the passive hints section when a device has none", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xc0"));
    const drawer = screen.getByRole("dialog", { name: /device details/i });
    expect(within(drawer).queryByText("Suggested investigation links")).not.toBeInTheDocument();
  });

  it("includes the legend entry only when passive hints exist", async () => {
    await renderLiveAndWaitForLayout();
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    expect(within(legend).getByText("Suggested investigation link")).toBeInTheDocument();
    expect(
      within(legend).getByText("Not topology evidence"),
    ).toBeInTheDocument();
  });

  it("selecting a device reveals its passive hints even when the control is off", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await selectGraphViewPreset(user, "quiet_view");
    expect(container.querySelectorAll(".mesh-edge--passive_derived_association")).toHaveLength(
      0,
    );
    fireEvent.click(screen.getByTestId("mesh-node-0xe1"));
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--passive_derived_association"),
      ).toHaveLength(1);
    });
  });

  it("caps drawn passive hints per node in large graphs", async () => {
    // Many hints all touching one hub device: the per-node cap (3) applies.
    mockDetail = {
      ...liveDetailWithPassiveHints,
      passive_hints: ["0xe2", "0xr1", "0xc0", "0xe3", "0xe4", "0xe5"].map((other) =>
        makePassiveHint({ source_ieee: "0xe1", target_ieee: other }),
      ),
    };
    const { container } = await renderLiveAndWaitForLayout();
    await waitFor(() => {
      expect(
        container.querySelectorAll(".mesh-edge--passive_derived_association").length,
      ).toBeGreaterThan(0);
    });
    expect(
      container.querySelectorAll(".mesh-edge--passive_derived_association").length,
    ).toBeLessThanOrEqual(3);
  });

  it("renders no forbidden wording anywhere with passive hints enabled", async () => {
    await renderLiveAndWaitForLayout();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/currently routed/i);
    expect(text).not.toMatch(/current route\b/i);
    expect(text).not.toMatch(/caused by/i);
    expect(text).not.toMatch(/connected through/i);
  });
});

describe("TopologyGraphPage last known links", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithLastKnown;
  });

  it("draws last known links by default in a distinct dash-dot style without arrowheads", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    const edges = container.querySelectorAll(".mesh-edge--last_known_link");
    expect(edges).toHaveLength(1);
    const path = edges[0].querySelector("path.react-flow__edge-path");
    expect(path?.getAttribute("style") ?? "").toContain("stroke-dasharray");
    // Non-directional: last known evidence never implies a route.
    expect(path?.getAttribute("marker-end") ?? "").toBe("");
    // The control is on by default and enabled.
    const panel = connectionControlsPanel();
    const checkbox = panel.getByRole("checkbox", { name: /last known links/i });
    expect(checkbox).toBeEnabled();
    expect(checkbox).toBeChecked();
    expect(
      screen.getByText("1 last known link is available from stored evidence."),
    ).toBeInTheDocument();
  });

  it("turning the control off removes the drawn edge", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    const panel = connectionControlsPanel();
    await user.click(panel.getByRole("checkbox", { name: /last known links/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--last_known_link")).toHaveLength(0);
    });
  });

  it("includes the legend entry only when last known links exist", async () => {
    await renderLiveAndWaitForLayout();
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    expect(within(legend).getByText("Last known link")).toBeInTheDocument();
    expect(
      within(legend).getByText("Not currently reported"),
    ).toBeInTheDocument();
  });

  it("opens a drawer that presents last known evidence without claiming current connectivity", async () => {
    const { container } = await renderLiveAndWaitForLayout();
    fireEvent.click(container.querySelector(".mesh-edge--last_known_link")!);
    const drawer = await screen.findByRole("dialog", { name: /link details/i });
    expect(within(drawer).getByText("Last known link")).toBeInTheDocument();
    expect(
      within(drawer).getAllByText(/not a currently reported link/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(/sleepy battery devices routinely age out/i).length,
    ).toBeGreaterThan(0);
    const text = drawer.textContent ?? "";
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/current route\b/i);
    expect(text).not.toMatch(/currently routed/i);
  });

  it("disables the control with measured-empty copy after history was evaluated", async () => {
    mockDetail = liveDetailWithHistory;
    await renderLiveAndWaitForLayout();
    const panel = connectionControlsPanel();
    const checkbox = panel.getByRole("checkbox", { name: /last known links/i });
    expect(checkbox).toBeDisabled();
    expect(checkbox).not.toBeChecked();
    expect(
      panel.getByText(
        "Previous snapshots were evaluated, but no last known link qualified for display.",
      ),
    ).toBeInTheDocument();
    // And the legend does not advertise the entry.
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    expect(within(legend).queryByText("Last known link")).not.toBeInTheDocument();
  });

  it("mentions last known links in the explainer", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await openDrawMoreLinks(user);
    await user.click(screen.getByTestId("connections-explainer-toggle"));
    const explainer = screen.getByTestId("connections-explainer");
    const text = explainer.textContent ?? "";
    expect(text).toMatch(/last known links/i);
    expect(text).toMatch(/not currently reported/i);
    expect(text).toMatch(/sleepy battery devices/i);
  });
});

describe("TopologyGraphPage shared chrome", () => {
  it("renders the legend with topology classes, omitting data-dependent entries when absent", async () => {
    await renderLiveAndWaitForLayout();
    const legend = screen.getByRole("group", { name: /link evidence legend/i });
    for (const cls of LIVE_EVIDENCE_CLASSES) {
      if (cls === "passive_derived_association" || cls === "last_known_link") continue;
      expect(within(legend).getByText(evidenceClassLabel(cls))).toBeInTheDocument();
    }
    // No passive hints in this data: the legend must not advertise them.
    expect(
      within(legend).queryByText("Suggested investigation link"),
    ).not.toBeInTheDocument();
    expect(within(legend).queryByText(/passive-derived/i)).not.toBeInTheDocument();
    // No last known links in this data either: the entry stays out.
    expect(within(legend).queryByText("Last known link")).not.toBeInTheDocument();
    // Classes without a live source stay out of the legend.
    expect(within(legend).queryByText(/stale/i)).not.toBeInTheDocument();
  });

  it("renders a safety banner that frames the graph as evidence, not a live routing map", async () => {
    await renderLiveAndWaitForLayout();
    const note = screen.getByRole("note", { name: /evidence safety note/i });
    expect(note).toHaveTextContent(GRAPH_SAFETY_COPY_LIVE);
    expect(note).toHaveTextContent(/evidence view/i);
    expect(note).toHaveTextContent(/not a live routing map/i);
    expect(note).not.toHaveTextContent(/passive hints are drawn/i);
    expect(note).not.toHaveTextContent(/drawer/i);
  });
});

describe("TopologyGraphPage investigation panel", () => {
  beforeEach(() => {
    mockDetail = liveDetailWithInvestigations;
  });

  function focusButton() {
    return screen.getByRole("button", { name: /^focus (graph|router area):/i });
  }

  it("renders the Where to look first panel with ranked cards and priority labels", async () => {
    await renderLiveAndWaitForLayout();
    const panel = screen.getByRole("region", { name: /where to look first/i });
    expect(
      within(panel).getByText(
        /ranked from existing zigbeelens evidence.*places to look first, not root-cause claims/i,
      ),
    ).toBeInTheDocument();
    expect(within(panel).getAllByTestId("investigation-card")).toHaveLength(1);
    expect(
      within(panel).getByLabelText(/investigation priority: worth checking/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getByLabelText(/investigation action: check power\/reporting/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(/check whether affected devices have power and are reporting/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText("Several recent missing links involve Live Lamp"),
    ).toBeInTheDocument();
  });

  it("shows a calm empty state when no investigation patterns exist", async () => {
    mockDetail = liveDetailWithHistory;
    await renderLiveAndWaitForLayout();
    expect(screen.getByTestId("investigation-empty")).toHaveTextContent(
      "No investigation priorities from the current evidence yet.",
    );
    expect(document.body.textContent).not.toMatch(/error|failure|critical/i);
  });

  it("reveals supporting evidence, limitations and next steps behind View details", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const card = screen.getByTestId("investigation-card");
    await user.click(within(card).getByRole("button", { name: /view details/i }));
    expect(
      within(card).getByText("3 recent missing links involve Live Lamp."),
    ).toBeInTheDocument();
    expect(within(card).getByText(INVESTIGATION_GENERIC_LIMITATION)).toBeInTheDocument();
    expect(within(card).getByText("Check device power.")).toBeInTheDocument();
    // Suggested steps stay within safe manual checks.
    expect(within(card).queryByText(/re-pair|reset|heal|scan/i)).not.toBeInTheDocument();
  });

  it("Focus graph highlights involved nodes and draws involved edges without moving layout", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    const beforePos = nodePosition(container, "0xe1");
    await selectGraphViewPreset(user, "quiet_view");
    // The card's historical edge is not drawn when Recent missing links is off.
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);

    await user.click(focusButton());
    await waitFor(() => {
      expect(container.querySelector('.react-flow__node[data-id="0xe1"]')).toHaveClass(
        "mesh-node--investigation-focus",
      );
    });
    expect(container.querySelector('.react-flow__node[data-id="0xe2"]')).toHaveClass(
      "mesh-node--investigation-focus",
    );
    // Involved edges are drawn even though the connection control is off.
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    // Unrelated devices stay visible but quieter.
    expect(container.querySelector('.react-flow__node[data-id="0xc0"]')).toHaveClass(
      "mesh-node--muted",
    );
    // Layout is untouched: no node moved.
    expect(nodePosition(container, "0xe1")).toBe(beforePos);
  });

  it("focusing does not change connection-control choices", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const recentMissing = connectionCheckbox(/recent missing links/i);
    expect(recentMissing).toBeChecked();
    await user.click(focusButton());
    expect(connectionCheckbox(/recent missing links/i)).toBeChecked();
    expect(connectionCheckbox(/route hints/i)).toBeChecked();
  });

  it("router-area cards use Focus router area and open existing NodeDrawer", async () => {
    const user = userEvent.setup();
    mockDetail = {
      ...liveDetailWithInvestigations,
      investigations: [
        makeInvestigationCard({
          id: "router-area-0xr1",
          type: "router_neighbourhood_review",
          action_group: "review_observed_router_area",
          title: "Observed router area around Live Hall Router",
          summary: "Several issue devices are represented around this router in stored evidence.",
          device_ieees: ["0xr1", "0xe1"],
          edge_ids: ["neighbor-0xr1|0xe1"],
          primary_neighbourhood_ieee: "0xr1",
        }),
      ],
    };
    const { container } = await renderLiveAndWaitForLayout();
    const beforePos = nodePosition(container, "0xr1");
    const preset = screen.getByLabelText("Graph view preset") as HTMLSelectElement;
    const presetBefore = preset.value;

    const card = screen.getByTestId("investigation-card");
    expect(card).toHaveAttribute("data-investigation-type", "router_neighbourhood_review");
    expect(
      within(card).getByRole("button", { name: /^focus router area:/i }),
    ).toBeInTheDocument();
    expect(
      within(card).getByRole("button", { name: /^open router details:/i }),
    ).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: /^open router details:/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /device details/i })).toBeInTheDocument();
    });
    expect(within(screen.getByRole("dialog")).getByText("0xr1")).toBeInTheDocument();
    expect(nodePosition(container, "0xr1")).toBe(beforePos);
    expect(preset.value).toBe(presetBefore);
  });

  it("omits Open router details when the neighbourhood IEEE is absent from inventory", async () => {
    mockDetail = {
      ...liveDetailWithInvestigations,
      investigations: [
        makeInvestigationCard({
          id: "router-area-missing",
          type: "router_neighbourhood_review",
          action_group: "review_observed_router_area",
          primary_neighbourhood_ieee: "0xmissing",
          device_ieees: ["0xe1"],
        }),
      ],
    };
    await renderLiveAndWaitForLayout();
    const card = screen.getByTestId("investigation-card");
    expect(within(card).getByRole("button", { name: /^focus router area:/i })).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: /^open router details:/i }),
    ).not.toBeInTheDocument();
  });

  it("Clear focus restores the graph without touching positions or controls", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    const beforePos = nodePosition(container, "0xr1");
    await user.click(focusButton());
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-node--investigation-focus").length).toBe(2);
    });

    await user.click(screen.getByRole("button", { name: /clear focus/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-node--investigation-focus")).toHaveLength(0);
    });
    expect(container.querySelectorAll(".mesh-node--muted")).toHaveLength(0);
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    expect(nodePosition(container, "0xr1")).toBe(beforePos);
    expect(connectionCheckbox(/recent missing links/i)).toBeChecked();
  });

  it("keeps evidence-class edge styling intact while focused", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await user.click(focusButton());
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    // Focused edges keep their evidence-class styling (dotted historical),
    // and the route edge keeps its own class — focus never recolours classes.
    expect(container.querySelectorAll(".mesh-edge--latest_snapshot_route")).toHaveLength(1);
  });

  it("renders cards in backend ranking order with Show more beyond the first three", async () => {
    const user = userEvent.setup();
    mockDetail = {
      ...liveDetailWithInvestigations,
      investigations: [
        makeInvestigationCard({ id: "card-1", title: "Card One", priority: "Review first" }),
        makeInvestigationCard({ id: "card-2", title: "Card Two" }),
        makeInvestigationCard({ id: "card-3", title: "Card Three" }),
        makeInvestigationCard({ id: "card-4", title: "Card Four", priority: "Lower priority" }),
      ],
      investigation_counts: { available: 4, returned: 4 },
    };
    await renderLiveAndWaitForLayout();
    const panel = screen.getByRole("region", { name: /where to look first/i });
    const titles = () =>
      within(panel)
        .getAllByTestId("investigation-card")
        .map((card) => within(card).getByText(/^Card (One|Two|Three|Four)$/).textContent);
    expect(titles()).toEqual(["Card One", "Card Two", "Card Three"]);

    await user.click(within(panel).getByRole("button", { name: /show more/i }));
    expect(titles()).toEqual(["Card One", "Card Two", "Card Three", "Card Four"]);
  });

  it("renders no forbidden wording anywhere with investigation cards shown", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    const card = screen.getByTestId("investigation-card");
    await user.click(within(card).getByRole("button", { name: /view details/i }));
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/root cause/i);
    expect(text).not.toMatch(/caused by/i);
    expect(text).not.toMatch(/parent router/i);
    expect(text).not.toMatch(/child device/i);
    expect(text).not.toMatch(/current route\b/i);
    expect(text).not.toMatch(/currently routed/i);
    expect(text).not.toMatch(/actual path/i);
    expect(text).not.toMatch(/failed because/i);
    expect(text).not.toMatch(/broken link/i);
    expect(text).not.toMatch(/lost link/i);
    expect(text).not.toMatch(/same parent/i);
    expect(text).not.toMatch(/heal network/i);
  });
});

describe("device search", () => {
  function searchInput() {
    return screen.getByRole("combobox", { name: /search devices/i });
  }

  it("renders the search input with an accessible label and helper", async () => {
    await renderLiveAndWaitForLayout();
    const input = searchInput();
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Search devices…");
    expect(input).toHaveAttribute(
      "title",
      "Search by name, IEEE address, model, manufacturer or status.",
    );
  });

  it("shows no empty-state copy before the user has typed", async () => {
    await renderLiveAndWaitForLayout();
    expect(screen.queryByText(/no matching devices/i)).not.toBeInTheDocument();
  });

  it("shows no-results copy only after a query that matches nothing", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "zzzz");
    expect(await screen.findByText("No matching devices for “zzzz”.")).toBeInTheDocument();
  });

  it("matches friendly names and lists results as devices, not raw graph terms", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "lamp");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    expect(within(list).getByRole("option", { name: /live lamp/i })).toBeInTheDocument();
    expect(list.textContent).not.toMatch(/\bnode\b/i);
    expect(list.textContent).not.toMatch(/\bedge\b/i);
  });

  it("matches IEEE addresses", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "0xr1");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    expect(within(list).getByRole("option", { name: /live hall router/i })).toBeInTheDocument();
  });

  it("matches manufacturer and model when available", async () => {
    mockDevices = liveDevices.map((device) =>
      device.ieee_address === "0xe1"
        ? { ...device, manufacturer: "IKEA", model: "TRADFRI bulb" }
        : device,
    );
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "ikea");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    expect(within(list).getByRole("option", { name: /live lamp/i })).toBeInTheDocument();
    expect(within(list).getByText(/IKEA · TRADFRI bulb/)).toBeInTheDocument();
  });

  it("matches status terms and explains limited topology evidence honestly", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    // 0xe2 is inventory-known but absent from the latest snapshot nodes.
    await user.type(searchInput(), "limited topology");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    const option = within(list).getByRole("option", { name: /live sleepy sensor/i });
    expect(option).toHaveTextContent(
      "Known device. Limited topology evidence in the latest snapshot.",
    );
    expect(option).toHaveTextContent("Limited topology evidence");
    expect(list.textContent).not.toMatch(/offline|lost|broken|not found in mesh/i);
  });

  it("orders results deterministically by name within a rank", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "live");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    const names = within(list)
      .getAllByRole("option")
      .map((option) => option.querySelector("span span")?.textContent);
    expect(names).toEqual([
      "Live Coordinator",
      "Live Hall Router",
      "Live Lamp",
      "Live Sleepy Sensor",
    ]);
  });

  it("selecting a result selects the device and opens the Device details panel", async () => {
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "sleepy");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    await user.click(within(list).getByRole("option", { name: /live sleepy sensor/i }));

    const drawer = await screen.findByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Live Sleepy Sensor")).toBeInTheDocument();
    await waitFor(() => {
      expect(container.querySelector('.react-flow__node[data-id="0xe2"]')).toHaveClass(
        "selected",
      );
    });
    // The result list closes and the query clears after selection.
    expect(screen.queryByRole("listbox", { name: /device search results/i })).not.toBeInTheDocument();
    expect(searchInput()).toHaveValue("");
  });

  it("selecting a result draws the device's evidence neighbourhood without moving nodes or changing controls", async () => {
    mockDetail = liveDetailWithHistory;
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    const beforePos = nodePosition(container, "0xr1");
    await selectGraphViewPreset(user, "quiet_view");
    // The historical edge touching 0xe2 is not drawn when Recent missing links is off.
    expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(0);
    expect(connectionCheckbox(/recent missing links/i)).not.toBeChecked();

    await user.type(searchInput(), "sleepy");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    await user.click(within(list).getByRole("option", { name: /live sleepy sensor/i }));

    // Selected-device evidence neighbourhood: the recent missing link touching
    // 0xe2 is drawn even though the connection control stays off.
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-edge--historical_neighbor")).toHaveLength(1);
    });
    expect(connectionCheckbox(/recent missing links/i)).not.toBeChecked();
    // Layout stable: nothing moved; preset choice persisted, search did not change controls.
    expect(nodePosition(container, "0xr1")).toBe(beforePos);
    expect(localStorage.getItem(viewPresetStorageKey("home"))).toBe("quiet_view");
  });

  it("selecting a search result clears an active investigation focus", async () => {
    mockDetail = liveDetailWithInvestigations;
    const user = userEvent.setup();
    const { container } = await renderLiveAndWaitForLayout();
    await user.click(screen.getByRole("button", { name: /^focus graph:/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-node--investigation-focus").length).toBe(2);
    });

    await user.type(searchInput(), "coordinator");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    await user.click(within(list).getByRole("option", { name: /live coordinator/i }));
    await waitFor(() => {
      expect(container.querySelectorAll(".mesh-node--investigation-focus")).toHaveLength(0);
    });
    expect(await screen.findByRole("dialog", { name: /device details/i })).toBeInTheDocument();
  });

  it("supports keyboard navigation: arrows move, Enter selects", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "live");
    await screen.findByRole("listbox", { name: /device search results/i });
    await user.keyboard("{ArrowDown}{Enter}");
    const drawer = await screen.findByRole("dialog", { name: /device details/i });
    expect(within(drawer).getByText("Live Hall Router")).toBeInTheDocument();
  });

  it("Escape clears the query and closes the results", async () => {
    const user = userEvent.setup();
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "lamp");
    await screen.findByRole("listbox", { name: /device search results/i });
    await user.keyboard("{Escape}");
    expect(searchInput()).toHaveValue("");
    expect(screen.queryByRole("listbox", { name: /device search results/i })).not.toBeInTheDocument();
  });

  it("Cmd+K / Ctrl+K focuses the device search", async () => {
    await renderLiveAndWaitForLayout();
    expect(searchInput()).not.toHaveFocus();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(searchInput()).toHaveFocus();
    (document.activeElement as HTMLElement | null)?.blur();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(searchInput()).toHaveFocus();
  });

  it("search results contain no forbidden user-facing phrases", async () => {
    const user = userEvent.setup();
    mockDetail = liveDetailWithHistory;
    await renderLiveAndWaitForLayout();
    await user.type(searchInput(), "live");
    const list = await screen.findByRole("listbox", { name: /device search results/i });
    expect(findForbiddenUserFacingPhrases(list.textContent ?? "")).toEqual([]);
  });
});

function makeHistoryRow(
  overrides: Partial<DeviceSnapshotHistoryRow>,
): DeviceSnapshotHistoryRow {
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
      status: "no_notable_change",
      reasons: [
        "Similar number of links shown.",
        "No route-hint change that looks relevant.",
        "There is no current ZigbeeLens issue for this device.",
      ],
      suggested_checks: [],
      link_counts: {
        latest_count: 6,
        selected_count: 6,
        latest_only_count: 0,
        selected_only_count: 0,
        changed_count: 0,
      },
      route_hint_counts: {
        latest_count: 2,
        selected_count: 2,
        latest_only_count: 0,
        selected_only_count: 0,
        changed_count: 0,
      },
    },
    ...overrides,
  };
}

/** Device needing attention: no links in the latest snapshot, links before. */
const worthReviewingHistory: DeviceSnapshotHistoryDetail = {
  network_id: "home",
  device_ieee: "0xr1",
  friendly_name: "Live Hall Router",
  has_current_issue: true,
  availability_tracking: {
    enabled: true,
    earliest_observation_at: "2026-07-01T00:00:00+00:00",
  },
  latest_snapshot: makeHistoryRow({
    snapshot_id: "snap-live",
    captured_at: "2026-07-06T00:30:00+00:00",
    is_latest: true,
    links_for_device_count: 0,
    route_hints_for_device_count: 0,
    availability_state_near_snapshot: "offline",
    comparison_to_latest: null,
  }),
  snapshots: [
    // Previous usable snapshot: default comparison, worth reviewing.
    makeHistoryRow({
      snapshot_id: "snap-prev",
      captured_at: "2026-07-05T19:10:00+00:00",
      comparison_to_latest: {
        status: "worth_reviewing",
        reasons: [
          "Latest snapshot shows no links for this device.",
          "The selected snapshot showed 6 links.",
          "This device currently needs attention.",
        ],
        suggested_checks: [
          "Confirm the device is powered.",
          "Check whether it is reporting in Zigbee2MQTT.",
          "Compare with another earlier snapshot to see whether this is a one-off snapshot difference.",
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
    // Older snapshot: differences but nothing actionable.
    makeHistoryRow({
      snapshot_id: "snap-older",
      captured_at: "2026-07-03T09:03:00+00:00",
      links_for_device_count: 8,
      route_hints_for_device_count: 3,
      comparison_to_latest: {
        status: "changed",
        reasons: [
          "8 links only in the selected snapshot.",
          "Route hints differ between the two snapshots.",
          "There is no current ZigbeeLens issue for this device.",
        ],
        suggested_checks: [],
        link_counts: {
          latest_count: 0,
          selected_count: 8,
          latest_only_count: 0,
          selected_only_count: 8,
          changed_count: 0,
        },
        route_hint_counts: {
          latest_count: 0,
          selected_count: 3,
          latest_only_count: 0,
          selected_only_count: 3,
          changed_count: 0,
        },
      },
    }),
    // Oldest snapshot: before availability tracking started.
    makeHistoryRow({
      snapshot_id: "snap-oldest",
      captured_at: "2026-06-28T10:00:00+00:00",
      links_for_device_count: 7,
      route_hints_for_device_count: 0,
      availability_coverage_status: "building",
      availability_state_near_snapshot: null,
    }),
  ],
  topology_facts: emptyTopologyDeviceFacts,
};

/** Availability reporting not enabled in Zigbee2MQTT at all. */
const trackingOffHistory: DeviceSnapshotHistoryDetail = {
  ...worthReviewingHistory,
  has_current_issue: false,
  availability_tracking: { enabled: false, earliest_observation_at: null },
  latest_snapshot: makeHistoryRow({
    snapshot_id: "snap-live",
    captured_at: "2026-07-06T00:30:00+00:00",
    is_latest: true,
    availability_coverage_status: "off",
    availability_state_near_snapshot: null,
    comparison_to_latest: null,
  }),
  snapshots: [
    makeHistoryRow({
      snapshot_id: "snap-prev",
      availability_coverage_status: "off",
      availability_state_near_snapshot: null,
    }),
  ],
};

describe("NodeDrawer device details without snapshot history", () => {
  beforeEach(() => {
    vi.spyOn(api, "topologyDeviceSnapshotHistory").mockImplementation(() =>
      Promise.resolve(emptyDeviceHistory),
    );
  });

  it("shows Device story in the Device details panel", async () => {
    vi.spyOn(api, "deviceStory").mockResolvedValue({
      subject_type: "device",
      subject_id: "0xr1",
      status: "watch",
      priority: "low",
      headline_code: "topology_evidence_gap",
      reasons: [{ code: "latest_snapshot_no_links", params: {} }],
      evidence: [],
      limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
      suggested_checks: [{ code: "compare_earlier_snapshot", params: {} }],
      coverage: [],
      timeline: [],
    });
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });
    const section = await screen.findByTestId("device-story-section");
    await waitFor(() => {
      expect(within(section).queryByText(/loading device story/i)).not.toBeInTheDocument();
    });
    expect(within(section).getByText("Watch")).toBeInTheDocument();
    expect(within(section).getByText("Topology evidence gap")).toBeInTheDocument();
    expect(api.deviceStory).toHaveBeenCalledWith("home", "0xr1", undefined);
  });

  it("removes the global Compare snapshots control and panel from the graph view", async () => {
    await renderLiveAndWaitForLayout();
    expect(
      screen.queryByRole("button", { name: /compare snapshots/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: /snapshot compare/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/topology-evidence churn/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/compared with the previous usable snapshot/i),
    ).not.toBeInTheDocument();
  });

  it("opening NodeDrawer performs zero snapshot-history API requests", async () => {
    const historySpy = vi.spyOn(api, "topologyDeviceSnapshotHistory");
    historySpy.mockClear();
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });
    await screen.findByTestId("device-story-section");
    expect(historySpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId("snapshot-history-section")).not.toBeInTheDocument();
    expect(screen.queryByTestId("device-snapshot-history")).not.toBeInTheDocument();
  });

  it("links to the full Device Detail route with encoded ieee", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    const dialog = await screen.findByRole("dialog", { name: /device details/i });
    const link = within(dialog).getByRole("link", { name: /open full device details/i });
    expect(link).toHaveAttribute("href", "/devices/home/0xr1");
  });
});

describe("contextual network report", () => {
  beforeEach(() => {
    vi.spyOn(api, "previewReport").mockResolvedValue({
      id: "preview",
      product: "ZigbeeLens",
      report_version: 3,
      format: "json",
      scope: "network",
      version: "test",
      markdown_summary: "# preview",
      limitations: [],
      redaction: {
        applied: true,
        profile: "standard",
        mqtt_credentials: true,
        secrets: true,
        hostnames: false,
        ip_addresses: false,
        ieee_addresses_hashed: true,
        friendly_names: "preserved",
        network_names: "preserved",
      },
      decision_summary: {
        subject_count: 4,
        status_counts: { no_notable_change: 4 },
        coverage_warning_count: 0,
      },
      generated_at: "2026-07-18T00:00:00Z",
      device_stories: [],
      investigation_priorities: [],
      data_coverage_warnings: [],
      incidents: [],
      collector_status: {},
      config_summary: {},
      domain_details: { networks: [{}], devices: [], device_details: [], router_risks: [] },
      events_or_timeline: [],
      raw_counts: { networks_included: 1, devices_included: 4, incidents_included: 0 },
    } as never);
  });

  it("opens a fixed network-scope contextual report dialog", async () => {
    await renderLiveAndWaitForLayout();
    const button = screen.getByRole("button", { name: /create network report/i });
    fireEvent.click(button);
    const dialog = await screen.findByRole("dialog", { name: /create network report/i });
    expect(within(dialog).getByText(/Export stored evidence for/i)).toHaveTextContent("Home");
    expect(within(dialog).queryByRole("button", { name: /^device$/i })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /^incident$/i })).not.toBeInTheDocument();
    expect(api.previewReport).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: "network",
        network_id: "home",
        incident_id: null,
        device: null,
      }),
      undefined,
    );
  });

  it("Escape closes the dialog and returns focus to the launch control", async () => {
    await renderLiveAndWaitForLayout();
    const button = screen.getByRole("button", { name: /create network report/i });
    fireEvent.click(button);
    await screen.findByRole("dialog", { name: /create network report/i });
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /create network report/i })).not.toBeInTheDocument();
    });
    expect(button).toHaveFocus();
  });

  it("does not serialize selected graph state into the report request", async () => {
    await renderLiveAndWaitForLayout();
    fireEvent.click(screen.getByTestId("mesh-node-0xr1"));
    await screen.findByRole("dialog", { name: /device details/i });
    fireEvent.click(screen.getByRole("button", { name: /create network report/i }));
    await screen.findByRole("dialog", { name: /create network report/i });
    expect(api.previewReport).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: "network",
        network_id: "home",
        device: null,
      }),
      undefined,
    );
  });
});
