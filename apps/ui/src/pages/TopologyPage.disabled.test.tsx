import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { TopologyPage } from "@/pages/TopologyPage";

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.1.0",
      features: { manual_network_map: false },
      topology: { enabled: false },
      configured_networks: [],
    },
  }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: () => ({
    data: { enabled: false, networks: [], manual_capture_enabled: false },
    loading: false,
    refetch: vi.fn(),
  }),
}));

describe("TopologyPage disabled", () => {
  it("shows disabled state calmly", () => {
    render(
      <MemoryRouter>
        <TopologyPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Topology disabled")).toBeInTheDocument();
  });
});
