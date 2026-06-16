import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NetworkHealthCard } from "@/components/cards";
import { TopologyPage } from "@/pages/TopologyPage";
import type { NetworkSummary } from "@zigbeelens/shared";

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
      },
    },
    {
      network_id: "home2",
      network_name: "Home 2",
      latest_snapshot: null,
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
};

const detailHome2 = {
  network_id: "home2",
  network_name: "Home 2",
  latest_snapshot: null,
  nodes: [],
  links: [],
};

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.1.13",
      topology: { enabled: true },
    },
  }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (fetcher: () => Promise<unknown>, deps: unknown[]) => {
    const key = JSON.stringify(deps);
    if (key.includes("home2")) {
      return { data: detailHome2, loading: false, error: null, refetch: vi.fn() };
    }
    if (key.includes("home")) {
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
  it("renders network tabs for multiple networks", () => {
    renderTopology("/topology/home");
    expect(screen.getByRole("tablist", { name: /topology networks/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Home" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Home 2" })).toBeInTheDocument();
  });

  it("shows snapshot detail for the selected network", () => {
    renderTopology("/topology/home");
    expect(screen.getByText("Home snapshot")).toBeInTheDocument();
    expect(screen.getByText("Router hall")).toBeInTheDocument();
    expect(screen.getByText(/0xabc → 0xdef/)).toBeInTheDocument();
  });

  it("can switch to home2 and shows diagnostics-limited copy when snapshot missing", async () => {
    const user = userEvent.setup();
    renderTopology("/topology/home");
    await user.click(screen.getByRole("tab", { name: "Home 2" }));
    expect(screen.getByText("Diagnostics limited")).toBeInTheDocument();
    expect(screen.getByText(/Waiting for a topology snapshot/)).toBeInTheDocument();
    expect(screen.getByText(/not an incident by itself/i)).toBeInTheDocument();
  });

  it("network list exposes view topology links", () => {
    renderTopology("/topology/home");
    const links = screen.getAllByRole("link", { name: /view topology/i });
    expect(links.length).toBeGreaterThanOrEqual(2);
    expect(links.some((link) => link.getAttribute("href") === "/topology/home2")).toBe(true);
  });
});

describe("NetworkHealthCard topology link", () => {
  const network: NetworkSummary = {
    id: "home",
    name: "Home",
    base_topic: "home",
    bridge_state: "online",
    incident_state: "healthy",
    active_incident_count: 0,
    device_count: 12,
    unavailable_count: 0,
    recently_unstable_count: 0,
    weak_link_count: 0,
    low_battery_count: 0,
    stale_count: 0,
  };

  it("shows view topology link when enabled", () => {
    render(
      <MemoryRouter>
        <NetworkHealthCard network={network} topologyEnabled />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /view topology/i })).toHaveAttribute(
      "href",
      "/topology/home",
    );
  });

  it("hides view topology link when disabled", () => {
    render(
      <MemoryRouter>
        <NetworkHealthCard network={network} topologyEnabled={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: /view topology/i })).not.toBeInTheDocument();
  });
});
