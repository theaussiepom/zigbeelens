import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DashboardPayload, DiagnosticConclusion } from "@zigbeelens/shared";
import { OverviewPage } from "./OverviewPage";

const finding: DiagnosticConclusion = {
  classification: "healthy",
  severity: "healthy",
  scope: "network",
  confidence: "high",
  summary: "No notable issues right now.",
  evidence: [],
  counter_evidence: [],
  limitations: [],
};

function makeDashboard(
  overrides: Partial<DashboardPayload> = {},
): DashboardPayload {
  return {
    generated_at: "2026-07-06T12:00:00+00:00",
    overall_severity: "healthy",
    current_finding: finding,
    active_incident_count: 0,
    watching_incident_count: 0,
    networks: [{ id: "home", name: "Home" } as DashboardPayload["networks"][number]],
    top_affected_devices: [],
    router_risks: [],
    recently_unstable: [],
    weak_links: [],
    low_batteries: [],
    stale_devices: [],
    recent_timeline: [],
    health_snapshot: {
      timestamp: "2026-07-06T12:00:00+00:00",
      overall_severity: "healthy",
      overall_health: "healthy",
      network_count: 1,
      device_count: 0,
      unavailable_count: 0,
      incident_count: 0,
      networks: [],
    },
    shared_availability_events: [],
    ...overrides,
  };
}

const mockState = vi.hoisted(() => ({
  dashboard: {
    generated_at: "2026-07-06T12:00:00+00:00",
    overall_severity: "healthy",
    current_finding: {
      classification: "healthy",
      severity: "healthy",
      scope: "network",
      confidence: "high",
      summary: "No notable issues right now.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    } satisfies DiagnosticConclusion,
    active_incident_count: 0,
    watching_incident_count: 0,
    networks: [{ id: "home", name: "Home" }],
    top_affected_devices: [],
    router_risks: [],
    recently_unstable: [],
    weak_links: [],
    low_batteries: [],
    stale_devices: [],
    recent_timeline: [],
    health_snapshot: {
      timestamp: "2026-07-06T12:00:00+00:00",
      overall_severity: "healthy",
      overall_health: "healthy",
      network_count: 1,
      device_count: 0,
      unavailable_count: 0,
      incident_count: 0,
      networks: [],
    },
    shared_availability_events: [],
  } as DashboardPayload,
}));

vi.mock("@/lib/api", () => ({
  api: {
    dashboard: vi.fn(),
    incidents: vi.fn(),
  },
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({ scenario: "", status: { topology: { enabled: true } } }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (fetcher: () => unknown) => {
    if (fetcher.toString().includes("incidents")) {
      return { data: [], loading: false, error: null, refetch: vi.fn() };
    }
    return {
      data: mockState.dashboard,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
  },
}));

function renderOverview() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
}

describe("OverviewPage shared availability events", () => {
  beforeEach(() => {
    mockState.dashboard = makeDashboard();
  });

  it("omits the shared-event section when the dashboard list is empty", () => {
    renderOverview();
    expect(screen.queryByText("Recent shared availability events")).not.toBeInTheDocument();
  });

  it("renders one card per shared availability event with limitation and mesh link", () => {
    mockState.dashboard = makeDashboard({
      shared_availability_events: [
        {
          event_id: "shared-availability-test",
          network_id: "home",
          started_at: "2026-07-06T08:00:00+00:00",
          ended_at: "2026-07-06T08:04:00+00:00",
          device_count: 11,
          duration_minutes: 4,
          device_ieees: ["0xd00"],
        },
      ],
    });
    renderOverview();
    expect(screen.getByText("Recent shared availability events")).toBeInTheDocument();
    expect(
      screen.getByText("Several devices went offline around the same time"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not prove they share a Zigbee route, path, parent, or root cause/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review mesh evidence/i })).toHaveAttribute(
      "href",
      "/topology/home",
    );
    expect(screen.queryByText(/network failure/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/critical/i)).not.toBeInTheDocument();
  });
});
