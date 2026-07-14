import { describe, expect, it } from "vitest";
import type {
  DashboardPayload,
  Incident,
  InvestigationPrioritySummary,
} from "@zigbeelens/shared";
import {
  MAX_OVERVIEW_RECENT_CHANGES,
  RECENT_CHANGES_FIRST_VISIT_COPY,
  RECENT_CHANGES_SECTION_TITLE,
  RECENT_CHANGES_SUBTITLE,
  buildRecentChangesSectionViewModel,
} from "./recentChangesViewModel";

function makeDashboard(overrides: Partial<DashboardPayload> = {}): DashboardPayload {
  return {
    generated_at: "2026-07-14T12:00:00+00:00",
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
    },
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
      timestamp: "2026-07-14T12:00:00+00:00",
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
    data_coverage_warnings: [],
    ...overrides,
  };
}

function makePriority(
  overrides: Partial<InvestigationPrioritySummary> = {},
): InvestigationPrioritySummary {
  return {
    id: "shared-availability-same",
    network_id: "home",
    card_type: "shared_availability_event",
    priority: "Review first",
    score: 12,
    action_group: "investigate_shared_event",
    title: "Several devices went offline around the same time",
    summary: "Shared-event investigation summary",
    device_ieees: [],
    latest_supporting_evidence_at: "2026-07-13T10:00:00+00:00",
    ...overrides,
  };
}

describe("recentChangesViewModel", () => {
  it("shows cautious first-visit copy without a previous timestamp", () => {
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: null,
      dashboard: makeDashboard({
        shared_availability_events: [
          {
            event_id: "shared-availability-same",
            network_id: "home",
            started_at: "2026-07-13T09:00:00+00:00",
            ended_at: "2026-07-13T10:00:00+00:00",
            device_count: 11,
            duration_minutes: 60,
            device_ieees: [],
          },
        ],
      }),
      incidents: [],
    });
    expect(section.title).toBe(RECENT_CHANGES_SECTION_TITLE);
    expect(section.mode).toBe("first_visit");
    expect(section.firstVisitCopy).toBe(RECENT_CHANGES_FIRST_VISIT_COPY);
    expect(section.items).toEqual([]);
  });

  it("excludes events before the previous visit and includes later ones", () => {
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T12:00:00+00:00",
      dashboard: makeDashboard({
        shared_availability_events: [
          {
            event_id: "shared-old",
            network_id: "home",
            started_at: "2026-07-11T09:00:00+00:00",
            ended_at: "2026-07-11T10:00:00+00:00",
            device_count: 5,
            duration_minutes: 60,
            device_ieees: [],
          },
          {
            event_id: "shared-new",
            network_id: "home",
            started_at: "2026-07-13T09:00:00+00:00",
            ended_at: "2026-07-13T10:00:00+00:00",
            device_count: 8,
            duration_minutes: 60,
            device_ieees: [],
          },
        ],
      }),
      incidents: [],
    });
    expect(section.mode).toBe("changes");
    expect(section.subtitle).toBe(RECENT_CHANGES_SUBTITLE);
    expect(section.items.map((item) => item.id)).toEqual(["shared-new"]);
  });

  it("sorts newest first and enforces the presentation cap", () => {
    const events = Array.from({ length: MAX_OVERVIEW_RECENT_CHANGES + 2 }, (_, index) => ({
      event_id: `shared-${index}`,
      network_id: "home",
      started_at: `2026-07-13T0${index}:00:00+00:00`,
      ended_at: `2026-07-13T0${index}:30:00+00:00`,
      device_count: 5,
      duration_minutes: 30,
      device_ieees: [] as string[],
    }));
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T00:00:00+00:00",
      dashboard: makeDashboard({ shared_availability_events: events }),
      incidents: [],
    });
    expect(section.items).toHaveLength(MAX_OVERVIEW_RECENT_CHANGES);
    expect(section.items[0]?.id).toBe(`shared-${MAX_OVERVIEW_RECENT_CHANGES + 1}`);
  });

  it("dedupes shared-event investigation cards that share the event id", () => {
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T00:00:00+00:00",
      dashboard: makeDashboard({
        shared_availability_events: [
          {
            event_id: "shared-availability-same",
            network_id: "home",
            started_at: "2026-07-13T09:00:00+00:00",
            ended_at: "2026-07-13T10:00:00+00:00",
            device_count: 11,
            duration_minutes: 60,
            device_ieees: [],
          },
        ],
        investigation_priorities: [makePriority()],
      }),
      incidents: [],
    });
    expect(section.items).toHaveLength(1);
    expect(section.items[0]?.kind).toBe("shared_event");
    expect(section.items[0]?.title).toBe("Shared availability event recorded");
  });

  it("dedupes model-pattern investigation cards that share the pattern id", () => {
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T00:00:00+00:00",
      dashboard: makeDashboard({
        model_patterns: [
          {
            pattern_id: "model-pattern-same",
            network_id: "home",
            manufacturer: "IKEA",
            model: "TS011F",
            group_size: 5,
            affected_count: 3,
            lookback_days: 7,
            affected_device_ieees: [],
            latest_supporting_evidence_at: "2026-07-13T11:00:00+00:00",
          },
        ],
        investigation_priorities: [
          makePriority({
            id: "model-pattern-same",
            card_type: "model_pattern_review",
            action_group: "review_model_pattern",
            latest_supporting_evidence_at: "2026-07-13T11:00:00+00:00",
          }),
        ],
      }),
      incidents: [],
    });
    expect(section.items).toHaveLength(1);
    expect(section.items[0]?.kind).toBe("model_pattern");
  });

  it("never exposes raw scores or action-group codes", () => {
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T00:00:00+00:00",
      dashboard: makeDashboard({
        investigation_priorities: [
          makePriority({
            id: "recent-missing-1",
            card_type: "recent_missing_cluster",
            score: 99,
            action_group: "check_power_reporting",
          }),
        ],
      }),
      incidents: [],
    });
    const serialized = JSON.stringify(section.items);
    expect(serialized).not.toContain("99");
    expect(serialized).not.toContain("check_power_reporting");
    expect(serialized.toLowerCase()).not.toContain("score");
  });

  it("links incidents and mesh contexts with existing routes", () => {
    const incident = {
      id: "inc-1",
      type: "group_offline",
      status: "open",
      severity: "watch",
      scope: "network",
      confidence: "medium",
      title: "Incident title",
      summary: "Incident summary",
      interpretation: "",
      network_ids: ["home"],
      affected_device_count: 1,
      affected_devices: [],
      opened_at: "2026-07-13T08:00:00+00:00",
      updated_at: "2026-07-13T09:00:00+00:00",
      evidence: [],
      counter_evidence: [],
      limitations: [],
      timeline: [],
      conclusion: {
        classification: "watch",
        severity: "watch",
        scope: "network",
        confidence: "medium",
        summary: "Incident summary",
        evidence: [],
        counter_evidence: [],
        limitations: [],
      },
    } as Incident;
    const section = buildRecentChangesSectionViewModel({
      previousLastViewedAt: "2026-07-12T00:00:00+00:00",
      dashboard: makeDashboard({
        investigation_priorities: [
          makePriority({
            id: "recent-missing-1",
            card_type: "recent_missing_cluster",
            action_group: "check_power_reporting",
          }),
        ],
      }),
      incidents: [incident],
    });
    const mesh = section.items.find((item) => item.id === "recent-missing-1");
    const inc = section.items.find((item) => item.id === "inc-1");
    expect(mesh?.href).toBe("/topology/home");
    expect(inc?.href).toBe("/incidents/inc-1");
  });
});
