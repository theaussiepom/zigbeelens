import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NetworkDecisionCard } from "@/components/cards";
import { LIMITED_LAYOUT_COPY, TopologyPage } from "@/pages/TopologyPage";
import { makeNetworkSummary } from "@/test/decisionFixtures";

const overviewMulti = {
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

const detailHome = {
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

const detailHomeLimited = {
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

const topologyNetwork = vi.fn();

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.1.13",
      topology: { enabled: true },
    },
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      topology: vi.fn(async () => overviewMulti),
      topologyNetwork: (...args: unknown[]) => topologyNetwork(...args),
      captureTopology: vi.fn(),
    },
  };
});

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (fetcher: () => Promise<unknown>, deps: unknown[], options?: { enabled?: boolean }) => {
    if (options?.enabled === false) {
      return { data: null, loading: false, error: null, refetch: vi.fn() };
    }
    const key = JSON.stringify(deps);
    if (key === "[]") {
      return { data: overviewMulti, loading: false, error: null, refetch: vi.fn() };
    }
    if (key.includes("home2")) {
      topologyNetwork("home2");
      return { data: detailHomeLimited, loading: false, error: null, refetch: vi.fn() };
    }
    if (key.includes("home")) {
      topologyNetwork("home");
      return { data: detailHome, loading: false, error: null, refetch: vi.fn() };
    }
    return { data: overviewMulti, loading: false, error: null, refetch: vi.fn() };
  },
}));

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
    topologyNetwork.mockClear();
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
    // Closed <details> keeps markup in the document; assert it is not visible.
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
