import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvestigateLandingPage } from "@/pages/InvestigateLandingPage";
import { makeNetworkSummary } from "@/test/decisionFixtures";
import type { NetworkSummary } from "@zigbeelens/shared";

let mockNetworks: NetworkSummary[] = [];

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: { version: "0.1.13", topology: { enabled: true } },
  }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: () => ({
    data: mockNetworks,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

function renderLanding() {
  return render(
    <MemoryRouter initialEntries={["/investigate"]}>
      <Routes>
        <Route path="/investigate" element={<InvestigateLandingPage />} />
        <Route path="/settings" element={<div>settings</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InvestigateLandingPage", () => {
  beforeEach(() => {
    mockNetworks = [];
  });

  it("renders zero-network state with Settings link", () => {
    renderLanding();
    expect(screen.getByRole("heading", { name: "Mesh / Investigate" })).toBeInTheDocument();
    expect(screen.getByText(/no networks configured/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open settings/i })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("lists one network linking to /investigate/:networkId", () => {
    mockNetworks = [makeNetworkSummary({ id: "home", name: "Home", device_count: 3 })];
    renderLanding();
    expect(screen.getByRole("link", { name: /home/i })).toHaveAttribute(
      "href",
      "/investigate/home",
    );
  });

  it("lists multiple networks in server order", () => {
    mockNetworks = [
      makeNetworkSummary({ id: "office", name: "Office", device_count: 2 }),
      makeNetworkSummary({ id: "home", name: "Home", device_count: 4 }),
    ];
    renderLanding();
    const links = screen
      .getAllByRole("link")
      .filter((el) => (el.getAttribute("href") || "").startsWith("/investigate/"));
    expect(links.map((el) => el.getAttribute("href"))).toEqual([
      "/investigate/office",
      "/investigate/home",
    ]);
  });
});
