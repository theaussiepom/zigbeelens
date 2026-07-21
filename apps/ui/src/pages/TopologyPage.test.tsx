import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NetworkDecisionCard } from "@/components/cards";
import {
  CAPTURE_DISABLED_NOTICE,
  LIMITED_LAYOUT_COPY,
  TopologyPage,
} from "@/pages/TopologyPage";
import { makeNetworkSummary } from "@/test/decisionFixtures";
import { topologySnapshotPath } from "@/lib/routes";
import type { TopologyNetworkDetail, TopologyOverview } from "@/lib/api";

const overviewMulti: TopologyOverview = {
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
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 2,
        link_count: 4,
        end_device_count: 8,
        status: "complete",
      },
    },
    {
      network_id: "home2",
      network_name: "Home 2",
      latest_snapshot: {
        snapshot_id: "snap-home2",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 0,
        link_count: 0,
        end_device_count: 0,
        status: "complete",
      },
    },
  ],
};

const detailHome: TopologyNetworkDetail = {
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

const detailHomeLimited: TopologyNetworkDetail = {
  network_id: "home2",
  network_name: "Home 2",
  latest_snapshot: {
    snapshot_id: "snap-home2",
    captured_at: "2026-06-16T02:17:53.509572+00:00",
    requested_by: "startup_scan",
    status: "complete",
    router_count: 0,
    link_count: 0,
    end_device_count: 0,
  },
  nodes: [],
  links: [],
  inventory: {
    device_count: 102,
    router_count: 14,
    end_device_count: 88,
  },
  layout_available: false,
};

const mockState = vi.hoisted(() => ({
  overview: null as TopologyOverview | null,
  details: new Map<string, TopologyNetworkDetail>(),
  scenarioTopologyEnabled: true,
}));

const topologyNetwork = vi.fn();

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.1.13",
      topology: { enabled: mockState.scenarioTopologyEnabled },
    },
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      topology: vi.fn(async () => mockState.overview),
      topologyNetwork: (...args: unknown[]) => topologyNetwork(...args),
      captureTopology: vi.fn(),
    },
  };
});

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (
    fetcher: () => Promise<unknown>,
    deps: unknown[],
    options?: { enabled?: boolean },
  ) => {
    if (options?.enabled === false) {
      return { data: null, loading: false, error: null, refetch: vi.fn() };
    }
    const key = JSON.stringify(deps);
    if (key === "[]") {
      return { data: mockState.overview, loading: false, error: null, refetch: vi.fn() };
    }
    const networkId = String(deps[0] ?? "");
    void fetcher();
    topologyNetwork(networkId);
    const detail = mockState.details.get(networkId) ?? null;
    return { data: detail, loading: false, error: null, refetch: vi.fn() };
  },
}));

function resetMocks() {
  mockState.overview = structuredClone(overviewMulti);
  mockState.details = new Map([
    ["home", structuredClone(detailHome)],
    ["home2", structuredClone(detailHomeLimited)],
  ]);
  mockState.scenarioTopologyEnabled = true;
  topologyNetwork.mockClear();
}

function renderTopology(initialEntry = "/topology/home") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/topology/:networkId" element={<TopologyPage />} />
        <Route path="/topology" element={<TopologyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TopologyPage", () => {
  beforeEach(() => {
    resetMocks();
  });

  it("renders /topology as a support landing without redirecting", async () => {
    renderTopology("/topology");
    expect(screen.getByRole("heading", { name: /topology snapshots/i })).toBeInTheDocument();
    expect(screen.getByText("Configured networks")).toBeInTheDocument();
    const homeLink = screen
      .getAllByRole("link")
      .find((link) => link.getAttribute("href") === "/topology/home");
    expect(homeLink).toBeTruthy();
    expect(homeLink).toHaveTextContent(/view snapshot details/i);
    expect(screen.queryByText("Home snapshot")).not.toBeInTheDocument();
    expect(screen.queryByText("Router hall")).not.toBeInTheDocument();
    expect(topologyNetwork).not.toHaveBeenCalled();
  });

  it("uses navigation links, not ARIA tabs, for network selection", () => {
    renderTopology("/topology/home");
    expect(screen.getByRole("navigation", { name: /topology snapshot networks/i })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Home 2" })).toBeInTheDocument();
  });

  it("shows snapshot detail for the requested network with raw contents collapsed", () => {
    renderTopology("/topology/home");
    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Startup scan")).toBeInTheDocument();
    expect(screen.getByText("Known devices")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/point-in-time snapshot evidence/i)).toBeInTheDocument();

    const disclosure = screen.getByText("Raw snapshot contents").closest("details");
    expect(disclosure).toBeTruthy();
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.getByText("Router hall")).not.toBeVisible();
    expect(screen.getByText(/0xabc → 0xdef/)).not.toBeVisible();
  });

  it("opens raw snapshot contents on activation", async () => {
    const user = userEvent.setup();
    renderTopology("/topology/home");
    const summary = screen.getByText("Raw snapshot contents");
    await user.click(summary);
    expect(screen.getByText("Router hall")).toBeInTheDocument();
    expect(screen.getByText(/0xabc → 0xdef/)).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0);
  });

  it("can navigate to home2 via network link", async () => {
    const user = userEvent.setup();
    renderTopology("/topology/home");
    await user.click(screen.getByRole("link", { name: "Home 2" }));
    expect(screen.getByText("Home 2 snapshot")).toBeInTheDocument();
    expect(screen.getByText(LIMITED_LAYOUT_COPY)).toBeInTheDocument();
    expect(screen.getByText("Known devices")).toBeInTheDocument();
    expect(screen.getByText("102")).toBeInTheDocument();
  });

  it("does not show misleading zero topology counts when layout is limited", async () => {
    const user = userEvent.setup();
    renderTopology("/topology/home");
    await user.click(screen.getByRole("link", { name: "Home 2" }));
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("startup_scan")).not.toBeInTheDocument();
  });

  it("does not fall back when the network id is unknown", () => {
    renderTopology("/topology/missing");
    expect(screen.getByText(/network “missing” was not found/i)).toBeInTheDocument();
    expect(screen.queryByText("Home snapshot")).not.toBeInTheDocument();
    expect(topologyNetwork).not.toHaveBeenCalled();
  });

  it("landing network cards link to /topology/<networkId>", () => {
    renderTopology("/topology");
    const rowLinks = screen
      .getAllByRole("link")
      .filter((link) => link.textContent?.includes("View snapshot details →"));
    expect(rowLinks).toHaveLength(2);
    expect(rowLinks.map((link) => link.getAttribute("href")).sort()).toEqual([
      "/topology/home",
      "/topology/home2",
    ]);
  });

  it("passes logical decoded network IDs to the detail API without double decoding", () => {
    const vectors: Array<[string, string]> = [
      ["home", "home"],
      ["Home Office", "Home Office"],
      ["home#2", "home#2"],
      ["home?test", "home?test"],
      ["münchen", "münchen"],
      ["50%mesh", "50%mesh"],
      ["home%20office", "home%20office"],
    ];
    for (const [logicalId] of vectors) {
      topologyNetwork.mockClear();
      mockState.overview = {
        ...structuredClone(overviewMulti),
        networks: [
          {
            network_id: logicalId,
            network_name: logicalId,
            latest_snapshot: {
              snapshot_id: "snap",
              status: "complete",
              captured_at: "2026-06-16T02:17:53.509572+00:00",
              router_count: 1,
              link_count: 1,
              end_device_count: 0,
            },
          },
        ],
      };
      mockState.details = new Map([
        [
          logicalId,
          {
            ...structuredClone(detailHome),
            network_id: logicalId,
            network_name: logicalId,
          },
        ],
      ]);
      const { unmount } = renderTopology(topologySnapshotPath(logicalId));
      expect(topologyNetwork).toHaveBeenCalledWith(logicalId);
      const encoded = encodeURIComponent(logicalId);
      if (encoded !== logicalId) {
        expect(topologyNetwork).not.toHaveBeenCalledWith(encoded);
      }
      // Consuming the already-decoded param must not re-decode (would URIError on e.g. 50%mesh).
      expect(screen.getByRole("heading", { name: /raw snapshot/i })).toBeInTheDocument();
      unmount();
    }
  });
});

describe("TopologyPage retained reads when capture disabled", () => {
  beforeEach(() => {
    resetMocks();
    mockState.overview = {
      ...structuredClone(overviewMulti),
      enabled: false,
      manual_capture_enabled: false,
    };
    mockState.scenarioTopologyEnabled = false;
  });

  it("lists known networks and retained snapshots on the landing", () => {
    renderTopology("/topology");
    expect(screen.getByText("Topology capture disabled")).toBeInTheDocument();
    expect(screen.getByText(CAPTURE_DISABLED_NOTICE)).toBeInTheDocument();
    expect(screen.getByText("Configured networks")).toBeInTheDocument();
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /capture snapshot/i })).not.toBeInTheDocument();
    const homeLink = screen
      .getAllByRole("link")
      .find((link) => link.getAttribute("href") === "/topology/home");
    expect(homeLink).toBeTruthy();
    expect(topologyNetwork).not.toHaveBeenCalled();
  });

  it("loads retained raw detail for a known network without a capture action", async () => {
    renderTopology("/topology/home");
    expect(screen.getByText("Topology capture disabled")).toBeInTheDocument();
    expect(topologyNetwork).toHaveBeenCalledWith("home");
    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Router hall")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /capture snapshot/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/after startup, zigbeelens requests/i)).not.toBeInTheDocument();
  });

  it("shows a calm no-snapshot state when capture is disabled", () => {
    mockState.details.set("home", {
      ...structuredClone(detailHome),
      latest_snapshot: null,
      nodes: [],
      links: [],
      layout_available: false,
    });
    renderTopology("/topology/home");
    expect(screen.getByText(/no topology snapshot is stored/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /capture snapshot/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/after startup, zigbeelens requests/i)).not.toBeInTheDocument();
  });

  it("returns not-found for unknown networks without fetching detail", () => {
    renderTopology("/topology/missing");
    expect(screen.getByText(/network “missing” was not found/i)).toBeInTheDocument();
    expect(topologyNetwork).not.toHaveBeenCalled();
    expect(screen.queryByText("Home snapshot")).not.toBeInTheDocument();
  });
});

describe("TopologyPage landing snapshot status matrix", () => {
  beforeEach(() => {
    resetMocks();
  });

  it.each([
    {
      name: "no snapshot",
      latest: null,
      label: "No snapshot",
      summary: /no topology snapshot captured yet/i,
    },
    {
      name: "complete",
      latest: {
        snapshot_id: "s",
        status: "complete",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 2,
        link_count: 4,
        end_device_count: 8,
      },
      label: "Complete",
      summary: /2 topology routers/,
    },
    {
      name: "complete limited",
      latest: {
        snapshot_id: "s",
        status: "complete",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 0,
        link_count: 0,
        end_device_count: 0,
      },
      label: "Complete · layout limited",
      summary: /layout limited/i,
    },
    {
      name: "pending",
      latest: {
        snapshot_id: "s",
        status: "pending",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 2,
        link_count: 4,
        end_device_count: 8,
      },
      label: "Pending",
      summary: /pending/i,
    },
    {
      name: "error",
      latest: {
        snapshot_id: "s",
        status: "error",
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 0,
        link_count: 0,
        end_device_count: 0,
      },
      label: "Error",
      summary: /error/i,
    },
    {
      name: "unknown status",
      latest: {
        snapshot_id: "s",
        status: null,
        captured_at: "2026-06-16T02:17:53.509572+00:00",
        router_count: 2,
        link_count: 4,
        end_device_count: 8,
      },
      label: "Status unknown",
      summary: /latest snapshot/i,
    },
  ])("renders $name on the landing card", ({ latest, label, summary }) => {
    mockState.overview = {
      ...structuredClone(overviewMulti),
      networks: [
        {
          network_id: "home",
          network_name: "Home",
          latest_snapshot: latest,
        },
      ],
    };
    renderTopology("/topology");
    const card = screen.getByRole("link", { name: /view snapshot details/i });
    expect(within(card).getByText(label, { exact: true })).toBeInTheDocument();
    expect(card.textContent ?? "").toMatch(summary);
    if (label === "Error") {
      expect(within(card).queryByText(/^snapshot$/i)).not.toBeInTheDocument();
    }
    if (label === "Pending" || label === "Error" || label === "Status unknown") {
      expect(card.textContent ?? "").not.toMatch(/topology routers/i);
    }
  });
});

describe("NetworkDecisionCard raw snapshot link", () => {
  const network = makeNetworkSummary({
    id: "home",
    name: "Home",
    base_topic: "home",
    device_count: 12,
    router_count: 2,
    end_device_count: 8,
  });

  it("shows Raw snapshot when explicitly enabled", () => {
    render(
      <MemoryRouter>
        <NetworkDecisionCard network={network} showRawSnapshotLink />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /raw snapshot/i })).toHaveAttribute(
      "href",
      "/topology/home",
    );
    expect(screen.queryByRole("link", { name: /view topology/i })).not.toBeInTheDocument();
  });

  it("hides Raw snapshot by default for Overview-style presentation", () => {
    render(
      <MemoryRouter>
        <NetworkDecisionCard network={network} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: /raw snapshot/i })).not.toBeInTheDocument();
  });
});
