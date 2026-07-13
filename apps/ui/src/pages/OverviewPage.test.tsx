import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
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
    model_patterns: [],
    investigation_priorities: [],
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
    model_patterns: [],
    investigation_priorities: [],
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

function headingIndex(text: string): number {
  const headings = screen.getAllByRole("heading").map((node) => node.textContent ?? "");
  const index = headings.findIndex((value) => value.includes(text));
  expect(index).toBeGreaterThanOrEqual(0);
  return index;
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

describe("OverviewPage model patterns", () => {
  beforeEach(() => {
    mockState.dashboard = makeDashboard();
  });

  it("omits the model-pattern section when the dashboard list is empty", () => {
    renderOverview();
    expect(screen.queryByText("Recent model patterns")).not.toBeInTheDocument();
  });

  it("renders one card per model pattern with limitation and mesh link", () => {
    mockState.dashboard = makeDashboard({
      model_patterns: [
        {
          pattern_id: "model-pattern-test",
          network_id: "home",
          manufacturer: "IKEA",
          model: "TS011F",
          group_size: 5,
          affected_count: 3,
          lookback_days: 7,
          affected_device_ieees: ["0xm00", "0xm01", "0xm02"],
          latest_supporting_evidence_at: "2026-07-06T08:22:00+00:00",
        },
      ],
    });
    renderOverview();
    expect(screen.getByText("Recent model patterns")).toBeInTheDocument();
    expect(screen.getByText("Review devices with the same model")).toBeInTheDocument();
    expect(
      screen.getByText(
        "3 of 5 devices with this model have gone offline in the last 7 days.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not prove the model is defective/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review mesh evidence/i })).toHaveAttribute(
      "href",
      "/topology/home",
    );
    expect(screen.queryByText(/faulty model/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/critical/i)).not.toBeInTheDocument();
  });
});

describe("OverviewPage investigation priorities", () => {
  beforeEach(() => {
    mockState.dashboard = makeDashboard();
  });

  it("shows cautious empty copy when there are no priorities", () => {
    renderOverview();
    expect(screen.getByText("What needs attention now")).toBeInTheDocument();
    expect(
      screen.getByText("No current investigation priorities from stored evidence."),
    ).toBeInTheDocument();
  });

  it("places investigation priorities before shared availability events", () => {
    mockState.dashboard = makeDashboard({
      investigation_priorities: [
        {
          id: "pri-1",
          network_id: "home",
          card_type: "shared_availability_event",
          priority: "Review first",
          score: 12,
          action_group: "investigate_shared_event",
          title: "Priority title A",
          summary: "Priority summary A",
          device_ieees: [],
          latest_supporting_evidence_at: "2026-07-06T08:00:00+00:00",
        },
      ],
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
    expect(headingIndex("What needs attention now")).toBeLessThan(
      headingIndex("Recent shared availability events"),
    );
  });

  it("renders priorities in backend order and links to Mesh", () => {
    mockState.dashboard = makeDashboard({
      investigation_priorities: [
        {
          id: "pri-high",
          network_id: "home",
          card_type: "issue_cluster",
          priority: "Review first",
          score: 12,
          action_group: "investigate_shared_event",
          title: "Highest priority title",
          summary: "Highest priority summary",
          device_ieees: [],
          latest_supporting_evidence_at: "2026-07-06T09:00:00+00:00",
        },
        {
          id: "pri-low",
          network_id: "home",
          card_type: "recent_missing_cluster",
          priority: "Worth checking",
          score: 8,
          action_group: "check_power_reporting",
          title: "Lower priority title",
          summary: "Lower priority summary",
          device_ieees: [],
          latest_supporting_evidence_at: "2026-07-06T08:00:00+00:00",
        },
      ],
    });
    renderOverview();
    const section = screen.getByLabelText("What needs attention now");
    const titles = within(section)
      .getAllByText(/priority title/i)
      .map((node) => node.textContent);
    expect(titles[0]).toBe("Highest priority title");
    expect(titles[1]).toBe("Lower priority title");
    expect(screen.getAllByRole("link", { name: /investigate in mesh/i })[0]).toHaveAttribute(
      "href",
      "/topology/home",
    );
    expect(screen.queryByText(/score 12/i)).not.toBeInTheDocument();
    expect(screen.queryByText("investigate_shared_event")).not.toBeInTheDocument();
  });

  it("keeps decision-priority hierarchy above raw count walls", () => {
    mockState.dashboard = makeDashboard({
      active_incident_count: 2,
      watching_incident_count: 1,
      health_snapshot: {
        timestamp: "2026-07-06T12:00:00+00:00",
        overall_severity: "watch",
        overall_health: "recently_unstable",
        network_count: 1,
        device_count: 40,
        unavailable_count: 3,
        incident_count: 2,
        networks: [],
      },
      recently_unstable: [],
      weak_links: [],
      low_batteries: [],
      stale_devices: [],
      investigation_priorities: [
        {
          id: "pri-1",
          network_id: "home",
          card_type: "shared_availability_event",
          priority: "Review first",
          score: 10,
          action_group: "investigate_shared_event",
          title: "Needs attention title",
          summary: "Needs attention summary",
          device_ieees: [],
        },
      ],
      model_patterns: [
        {
          pattern_id: "model-pattern-test",
          network_id: "home",
          manufacturer: "IKEA",
          model: "TS011F",
          group_size: 5,
          affected_count: 3,
          lookback_days: 7,
          affected_device_ieees: ["0xm00"],
        },
      ],
    });
    renderOverview();

    expect(screen.getByText("No notable issues right now.")).toBeInTheDocument();
    expect(screen.getByText("What needs attention now")).toBeInTheDocument();
    expect(screen.getAllByText("Active incidents").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Watching")).toBeInTheDocument();
    expect(screen.getByText("System summary")).toBeInTheDocument();
    expect(screen.getAllByText("Networks").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Devices").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Low battery").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Stale").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Weak links").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Recently unstable").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Top affected devices")).toBeInTheDocument();
    expect(screen.getByText("Recent model patterns")).toBeInTheDocument();

    const attentionIdx = headingIndex("What needs attention now");
    const systemIdx = headingIndex("System summary");
    const incidentsIdx = headingIndex("Active incidents");
    expect(attentionIdx).toBeLessThan(systemIdx);
    expect(attentionIdx).toBeLessThan(incidentsIdx);

    // Router risks must not appear as a primary summary StatTile or section when empty.
    expect(screen.queryByText("Router risks")).not.toBeInTheDocument();
  });
});

describe("InvestigationPriorityCard source boundary", () => {
  it("does not hard-code investigation action-group mappings", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(
      join(here, "../components/overview/InvestigationPriorityCard.tsx"),
      "utf8",
    );
    for (const code of [
      "review_observed_router_area",
      "review_model_pattern",
      "investigate_shared_event",
      "improve_data_coverage",
      "watch_only",
    ]) {
      expect(source).not.toContain(code);
    }
  });
});
