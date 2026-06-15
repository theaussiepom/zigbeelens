import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MonitoringGuidePage } from "@/pages/MonitoringGuidePage";

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      diagnostics: {
        incident_window_seconds: 180,
        bridge_stale_after_minutes: 10,
        flapping_threshold: 3,
      },
    },
  }),
}));

describe("MonitoringGuidePage", () => {
  it("renders key monitoring guide sections", () => {
    render(
      <MemoryRouter>
        <MonitoringGuidePage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: /how monitoring works/i })).toBeInTheDocument();
    expect(screen.getByText(/device health flags/i)).toBeInTheDocument();
    expect(screen.getByText(/incident rules/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^bridge health$/i })).toBeInTheDocument();
  });
});
