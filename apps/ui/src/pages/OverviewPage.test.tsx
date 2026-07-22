import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DashboardPayload, Incident } from "@zigbeelens/shared";
import { OVERVIEW_LAST_VIEWED_STORAGE_KEY } from "@/lib/overviewVisitStorage";
import { makeDashboardPayload, makeNetworkSummary } from "@/test/decisionFixtures";
import { OverviewPage } from "./OverviewPage";

function makeDashboard(
  overrides: Partial<DashboardPayload> = {},
): DashboardPayload {
  return makeDashboardPayload({
    generated_at: "2026-07-06T12:00:00+00:00",
    networks: [makeNetworkSummary({ id: "home", name: "Home" })],
    decision_summary: {
      subject_count: 0,
      overall_status: "data_unavailable",
      highest_priority: "none",
      status_counts: {},
      priority_counts: {},
      coverage_warning_count: 0,
    },
    ...overrides,
  });
}

const mockState = vi.hoisted(() => {
  const decision_summary = {
    subject_count: 0,
    overall_status: "data_unavailable",
    highest_priority: "none",
    status_counts: {} as Record<string, number>,
    priority_counts: {} as Record<string, number>,
    coverage_warning_count: 0,
  };
  return {
    dashboard: {
      generated_at: "2026-07-06T12:00:00+00:00",
      active_incident_count: 0,
      watching_incident_count: 0,
      network_count: 1,
      device_count: 0,
      unavailable_device_count: 0,
      networks: [
        {
          id: "home",
          name: "Home",
          base_topic: "zigbee2mqtt",
          bridge_state: "online" as const,
          device_count: 0,
          router_count: 0,
          end_device_count: 0,
          unavailable_count: 0,
          active_incident_severity: "healthy" as const,
          active_incident_count: 0,
          recent_bridge_warnings: 0,
          recent_bridge_errors: 0,
          decision: {
            status: "data_unavailable",
            priority: "none",
            headline_code: "network_data_unavailable",
            coverage_label_codes: [] as string[],
          },
          decision_summary,
        },
      ],
      router_risks: [],
      recent_timeline: [],
      decision_summary,
      shared_availability_events: [],
      model_patterns: [],
      investigation_priorities: [],
      data_coverage_warnings: [],
    } as DashboardPayload,
    activeIncidents: [] as Incident[],
    recentIncidents: [] as Incident[],
    activeResource: {
      dataOverride: undefined as Incident[] | null | undefined,
      loading: false,
      error: null as string | null,
      refetch: vi.fn(),
    },
    recentResource: {
      dataOverride: undefined as Incident[] | null | undefined,
      loading: false,
      error: null as string | null,
      refetch: vi.fn(),
    },
  };
});

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
    const source = fetcher.toString();
    if (source.includes("incidents")) {
      if (source.includes("updated_after") || source.includes("previousLastViewedAt")) {
        return {
          data: mockState.recentResource.dataOverride === undefined
            ? mockState.recentIncidents
            : mockState.recentResource.dataOverride,
          loading: mockState.recentResource.loading,
          error: mockState.recentResource.error,
          refetch: mockState.recentResource.refetch,
        };
      }
      return {
        data: mockState.activeResource.dataOverride === undefined
          ? mockState.activeIncidents
          : mockState.activeResource.dataOverride,
        loading: mockState.activeResource.loading,
        error: mockState.activeResource.error,
        refetch: mockState.activeResource.refetch,
      };
    }
    return {
      data: mockState.dashboard,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
  },
}));

function makeOverviewIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    title: "Incident one",
    status: "open",
    type: "single_device_unavailable",
    severity: "watch",
    scope: "device",
    confidence: "medium",
    summary: "summary",
    interpretation: "",
    network_ids: ["home"],
    affected_device_count: 0,
    affected_devices: [],
    opened_at: "2026-07-16T10:00:00Z",
    updated_at: "2026-07-16T12:00:00Z",
    resolved_at: null,
    evidence: [],
    counter_evidence: [],
    limitations: [],
    timeline: [],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "watch",
      scope: "device",
      confidence: "medium",
      summary: "summary",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

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

beforeEach(() => {
  mockState.activeResource.dataOverride = undefined;
  mockState.activeResource.loading = false;
  mockState.activeResource.error = null;
  mockState.activeResource.refetch = vi.fn();
  mockState.recentResource.dataOverride = undefined;
  mockState.recentResource.loading = false;
  mockState.recentResource.error = null;
  mockState.recentResource.refetch = vi.fn();
});

describe("OverviewPage shared availability events", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
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
      screen.getByText(/does not prove they share a Zigbee route, path, parent, or common cause/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review mesh evidence/i })).toHaveAttribute(
      "href",
      "/investigate/home",
    );
  });
});

describe("OverviewPage model patterns", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
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
  });
});

describe("OverviewPage investigation priorities", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
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
      "/investigate/home",
    );
    expect(screen.queryByText(/score 12/i)).not.toBeInTheDocument();
  });

  it("keeps a calm decision status alongside stored investigation priorities", () => {
    mockState.dashboard = makeDashboard({
      investigation_priorities: [
        {
          id: "pri-historical",
          network_id: "home",
          card_type: "shared_availability_event",
          priority: "Worth checking",
          score: 8,
          action_group: "investigate_shared_event",
          title: "Historical shared event worth reviewing",
          summary: "Stored shared-event evidence remains useful to review.",
          device_ieees: [],
          latest_supporting_evidence_at: "2026-07-05T08:00:00+00:00",
        },
      ],
    });
    renderOverview();
    expect(screen.getAllByText("Data unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Historical shared event worth reviewing")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Stored evidence can still suggest useful checks even when no current incident is active.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps decision-priority hierarchy above raw count walls", () => {
    mockState.dashboard = makeDashboard({
      active_incident_count: 2,
      watching_incident_count: 1,
      device_count: 40,
      unavailable_device_count: 3,
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

    expect(headingIndex("What needs attention now")).toBeLessThan(
      headingIndex("Networks"),
    );
    expect(headingIndex("What needs attention now")).toBeLessThan(
      headingIndex("Active incidents"),
    );
    expect(screen.queryByText("Router risks")).not.toBeInTheDocument();
    expect(screen.queryByText("Health signal summaries")).not.toBeInTheDocument();
  });
});

describe("OverviewPage recent changes and data coverage", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
  });

  it("shows first-visit copy when no previous Overview visit is stored", async () => {
    renderOverview();
    expect(screen.getByText("Since your last visit")).toBeInTheDocument();
    expect(
      screen.getByText("Recent changes will appear here after your next visit."),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBeTruthy();
    });
  });

  it("renders recent shared events since the previous visit", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.dashboard = makeDashboard({
      shared_availability_events: [
        {
          event_id: "shared-new",
          network_id: "home",
          started_at: "2026-07-06T08:00:00+00:00",
          ended_at: "2026-07-06T08:04:00+00:00",
          device_count: 11,
          duration_minutes: 4,
          device_ieees: [],
        },
      ],
    });
    renderOverview();
    expect(screen.getByText("Changes recorded after your previous Overview visit.")).toBeInTheDocument();
    expect(screen.getByText("Shared availability event recorded")).toBeInTheDocument();
  });

  it("places recent changes and coverage between priorities and shared events", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.dashboard = makeDashboard({
      investigation_priorities: [
        {
          id: "pri-1",
          network_id: "home",
          card_type: "issue_cluster",
          priority: "Review first",
          score: 10,
          action_group: "investigate_shared_event",
          title: "Priority title",
          summary: "Priority summary",
          device_ieees: [],
        },
      ],
      data_coverage_warnings: [
        {
          id: "coverage-home-availability_tracking_off",
          network_id: "home",
          dimension: "availability",
          state: "off",
          label_code: "availability_tracking_off",
          scope_type: "network",
          params: {},
        },
      ],
      shared_availability_events: [
        {
          event_id: "shared-new",
          network_id: "home",
          started_at: "2026-07-06T08:00:00+00:00",
          ended_at: "2026-07-06T08:04:00+00:00",
          device_count: 11,
          duration_minutes: 4,
          device_ieees: [],
        },
      ],
    });
    renderOverview();
    expect(headingIndex("What needs attention now")).toBeLessThan(
      headingIndex("Since your last visit"),
    );
    expect(headingIndex("Since your last visit")).toBeLessThan(headingIndex("Data coverage"));
    expect(headingIndex("Data coverage")).toBeLessThan(
      headingIndex("Recent shared availability events"),
    );
    expect(screen.getByText("Availability tracking off")).toBeInTheDocument();
  });

  it("does not render a reassuring empty data coverage section", () => {
    renderOverview();
    expect(screen.queryByText("Data coverage")).not.toBeInTheDocument();
    expect(screen.queryByText(/data coverage complete/i)).not.toBeInTheDocument();
  });
});

describe("Overview presentation source boundaries", () => {
  it("keeps localStorage out of RecentChangesSection", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(
      join(here, "../components/overview/RecentChangesSection.tsx"),
      "utf8",
    );
    expect(source).not.toContain("localStorage");
    expect(source).not.toContain("lastViewedAt");
  });

  it("does not hard-code investigation action-group mappings in the priority card", () => {
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

describe("OverviewPage server incident order", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard({
      decision_summary: {
        subject_count: 2,
        overall_status: "review_first",
        highest_priority: "high",
        status_counts: { review_first: 2 },
        priority_counts: { high: 2 },
        coverage_warning_count: 0,
      },
      active_incident_count: 2,
    });
    mockState.recentIncidents = [];
  });

  it("requests recent changes with order=recent and updated_after", () => {
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "OverviewPage.tsx"), "utf8");
    expect(source).toMatch(/order:\s*["']recent["']/);
    expect(source).toMatch(/updated_after:\s*previousLastViewedAt/);
    expect(source).toMatch(/limit:\s*50/);
    // Active incidents remain lifecycle-ranked (no order override).
    expect(source).toMatch(/status:\s*\[["']open["'],\s*["']watching["']\]/);
  });

  it("keeps server order when an older open incident has higher severity", () => {
    // Server order: newer open first. Client must not promote older higher severity.
    mockState.activeIncidents = [
      makeOverviewIncident({
        id: "newer-open",
        title: "Newer open incident",
        status: "open",
        severity: "watch",
        updated_at: "2026-07-16T12:00:00Z",
      }),
      makeOverviewIncident({
        id: "older-severe",
        title: "Older severe open incident",
        status: "open",
        severity: "incident",
        updated_at: "2026-07-16T10:00:00Z",
      }),
    ];

    renderOverview();

    const incidentLinks = screen.getAllByRole("link").filter((node) =>
      (node.getAttribute("href") || "").startsWith("/incidents/"),
    );
    expect(incidentLinks[0]).toHaveAttribute("href", "/incidents/newer-open");

    const titles = screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent);
    expect(titles.indexOf("Newer open incident")).toBeGreaterThanOrEqual(0);
    expect(titles.indexOf("Newer open incident")).toBeLessThan(
      titles.indexOf("Older severe open incident"),
    );
  });
});

describe("OverviewPage secondary incident resource states", () => {
  beforeEach(() => {
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
  });

  it("keeps dashboard content visible while active incidents load", () => {
    mockState.activeResource.dataOverride = null;
    mockState.activeResource.loading = true;
    renderOverview();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("Loading active incidents…")).toBeInTheDocument();
    expect(screen.queryByText("No active incidents")).not.toBeInTheDocument();
  });

  it("shows an active-incident unavailable state with Retry", () => {
    mockState.activeResource.dataOverride = null;
    mockState.activeResource.error = "request failed";
    renderOverview();
    expect(screen.getByText("Active incidents are unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry active incidents" })).toBeInTheDocument();
    expect(screen.queryByText("No active incidents")).not.toBeInTheDocument();
  });

  it("shows factual active-incident empty copy for an accepted empty result", () => {
    renderOverview();
    expect(screen.getByText("No active incidents")).toBeInTheDocument();
  });

  it("renders accepted active incidents", () => {
    mockState.activeIncidents = [makeOverviewIncident({ title: "Accepted active incident" })];
    renderOverview();
    expect(screen.getByText("Accepted active incident")).toBeInTheDocument();
    expect(screen.queryByText("No active incidents")).not.toBeInTheDocument();
  });

  it("retains accepted active incidents after a refresh error", () => {
    mockState.activeIncidents = [makeOverviewIncident({ title: "Retained active incident" })];
    mockState.activeResource.error = "refresh failed";
    renderOverview();
    expect(screen.getByText("Retained active incident")).toBeInTheDocument();
    expect(
      screen.getByText("Active incidents could not be refreshed. Showing the last loaded results."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry active incidents" })).toBeInTheDocument();
  });

  it("does not claim no changes while recent incidents are loading", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.loading = true;
    renderOverview();
    expect(screen.getByText("Loading incident changes…")).toBeInTheDocument();
    expect(
      screen.queryByText("No recorded changes since your previous Overview visit."),
    ).not.toBeInTheDocument();
  });

  it("retains dashboard-derived changes with a partial-data warning while incidents load", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.dashboard = makeDashboard({
      shared_availability_events: [
        {
          event_id: "shared-partial",
          network_id: "home",
          started_at: "2026-07-06T08:00:00+00:00",
          ended_at: "2026-07-06T08:04:00+00:00",
          device_count: 4,
          duration_minutes: 4,
          device_ieees: [],
        },
      ],
    });
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.loading = true;
    renderOverview();
    expect(screen.getByText("Shared availability event recorded")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Incident changes are still loading. Showing changes from the loaded dashboard evidence.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No recorded changes since your previous Overview visit."),
    ).not.toBeInTheDocument();
  });

  it("does not claim no changes when the initial recent-incident request fails", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.error = "request failed";
    renderOverview();
    expect(screen.getByText("Incident changes are unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry incident changes" })).toBeInTheDocument();
    expect(
      screen.queryByText("No recorded changes since your previous Overview visit."),
    ).not.toBeInTheDocument();
  });

  it("shows factual no-change copy when recent incidents are accepted empty", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    renderOverview();
    expect(
      screen.getByText("No recorded changes since your previous Overview visit."),
    ).toBeInTheDocument();
  });

  it("retains accepted recent incidents after a refresh error", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.recentIncidents = [
      makeOverviewIncident({
        title: "Retained recent incident",
        updated_at: "2026-07-16T12:00:00Z",
      }),
    ];
    mockState.recentResource.error = "refresh failed";
    renderOverview();
    expect(screen.getByText("Retained recent incident")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Incident changes could not be refreshed. Showing the last loaded incident evidence.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry incident changes" })).toBeInTheDocument();
  });

  it("gives simultaneous active-incident and incident-change retries unique accessible names", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2026-07-05T00:00:00.000Z");
    mockState.activeResource.dataOverride = null;
    mockState.activeResource.error = "active request failed";
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.error = "recent request failed";

    renderOverview();

    const retryNames = screen.getAllByRole("button", { name: /^Retry / }).map(
      (button) => button.getAttribute("aria-label") ?? button.textContent,
    );
    expect(retryNames).toEqual(["Retry incident changes", "Retry active incidents"]);
    expect(new Set(retryNames).size).toBe(retryNames.length);
  });
});

describe("OverviewPage visit watermark", () => {
  const previousBoundary = "2026-07-05T00:00:00.000Z";
  const browserTimestamp = "2026-07-22T03:04:05.000Z";
  const coreTimestamp = "2026-07-06T12:00:00+00:00";

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(browserTimestamp));
    localStorage.clear();
    mockState.dashboard = makeDashboard();
    mockState.activeIncidents = [];
    mockState.recentIncidents = [];
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("writes the first watermark once dashboard data is accepted", () => {
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.loading = true;
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("preserves a previous boundary while recent incidents are initially loading", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.loading = true;
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(previousBoundary);
  });

  it("preserves a previous boundary after an initial recent-incident failure", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.error = "request failed";
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(previousBoundary);
  });

  it("advances after an accepted empty recent-incident result", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("advances after an accepted nonempty recent-incident result", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    mockState.recentIncidents = [makeOverviewIncident()];
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("advances with retained accepted incident data after a refresh error", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    mockState.recentIncidents = [makeOverviewIncident()];
    mockState.recentResource.error = "refresh failed";
    renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("advances when retry produces the first accepted incident result", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, previousBoundary);
    mockState.recentResource.dataOverride = null;
    mockState.recentResource.error = "request failed";
    const view = renderOverview();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(previousBoundary);

    fireEvent.click(screen.getByRole("button", { name: "Retry incident changes" }));
    expect(mockState.recentResource.refetch).toHaveBeenCalledTimes(1);
    mockState.dashboard = makeDashboard({ generated_at: "2026-07-06T13:00:00+00:00" });
    mockState.recentResource.dataOverride = [];
    mockState.recentResource.error = null;
    view.rerender(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );

    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("uses Core time when the browser clock is behind", () => {
    vi.setSystemTime(new Date("2020-01-01T00:00:00.000Z"));
    renderOverview();

    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
  });

  it("repairs a pre-existing future browser-clock boundary conservatively", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "2027-01-01T00:00:00.000Z");
    renderOverview();

    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBe(coreTimestamp);
    expect(
      screen.getByText("Recent changes will appear here after your next visit."),
    ).toBeInTheDocument();
  });

  it("writes the Core boundary only once per mount", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const view = renderOverview();
    mockState.dashboard = makeDashboard({ generated_at: "2026-07-06T14:00:00+00:00" });
    view.rerender(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );

    expect(
      setItem.mock.calls.filter(([key]) => key === OVERVIEW_LAST_VIEWED_STORAGE_KEY),
    ).toEqual([[OVERVIEW_LAST_VIEWED_STORAGE_KEY, coreTimestamp]]);
    setItem.mockRestore();
  });

  it("does not persist an invalid Core dashboard timestamp", () => {
    mockState.dashboard = makeDashboard({ generated_at: "not-a-timestamp" });
    renderOverview();

    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBeNull();
  });
});
