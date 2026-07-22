import { describe, expect, it } from "vitest";
import type {
  HistoricalEdgeAggregate,
  InvestigationCard,
  LastKnownLinkAggregate,
  PassiveHintAggregate,
} from "@/types/topology";
import { makeTopologyEvidenceGraphDetail } from "./topologyEvidenceGraphFixture";

const historicalNeighbor: HistoricalEdgeAggregate = {
  source_ieee: "0x2",
  target_ieee: "0x3",
  evidence_class: "historical_neighbor",
  directional: false,
  not_seen_in_latest_snapshot: true,
  latest_layout_limited: false,
  confidence: "medium",
  limitations: [],
};

const historicalRoute: HistoricalEdgeAggregate = {
  ...historicalNeighbor,
  source_ieee: "0x3",
  target_ieee: "0x4",
  evidence_class: "historical_route",
  directional: true,
};

const lastKnownLink: LastKnownLinkAggregate = {
  source_ieee: "0x2",
  target_ieee: "0x5",
  evidence_class: "last_known_link",
  directional: false,
  last_reported_at: "2026-07-05T00:00:00Z",
  last_snapshot_id: "snap-previous",
  not_seen_in_latest_snapshot: true,
  confidence: "low",
  limitations: [],
};

const passiveHint: PassiveHintAggregate = {
  source_ieee: "0x2",
  target_ieee: "0x6",
  evidence_class: "passive_derived_association",
  directional: false,
  confidence: "low",
  issue_related: false,
  rules_matched: [],
  supporting_observations: [],
  limitations: [],
  suggested_investigation: [],
};

const sharedAvailabilityInvestigation: InvestigationCard = {
  id: "shared-event-fixture",
  type: "shared_availability_event",
  priority: "Worth checking",
  score: 8,
  title: "Several devices went offline around the same time",
  summary: "Two devices had a shared recorded availability event.",
  why_it_matters: "The shared timing is worth reviewing as one recorded event.",
  supporting_evidence: ["Two recorded offline transitions occurred together."],
  limitations: ["Shared timing does not prove a shared cause."],
  suggested_next_steps: ["Review the recorded availability timelines."],
  device_ieees: ["0x2", "0x6"],
  edge_ids: [],
  primary_device_ieee: null,
  primary_neighbourhood_ieee: null,
  created_from_evidence_classes: ["availability_transition"],
  latest_supporting_evidence_at: "2026-07-05T00:00:00Z",
  action_group: "investigate_shared_event",
};

const evaluatedHistoryWindow = {
  days: 7,
  max_snapshots: 3,
  snapshots_considered: 2,
  earliest_captured_at: "2026-07-01T00:00:00Z",
  latest_captured_at: "2026-07-05T00:00:00Z",
};

const evaluatedLastKnownWindow = {
  snapshots_considered: 2,
  earliest_captured_at: "2026-07-01T00:00:00Z",
  latest_captured_at: "2026-07-05T00:00:00Z",
};

describe("makeTopologyEvidenceGraphDetail", () => {
  it("derives a semantically coherent graph from the evidence arrays", () => {
    const detail = makeTopologyEvidenceGraphDetail({
      nodes: [
        { ieee_address: "0x1", node_type: "Coordinator" },
        { ieee_address: "0x2", node_type: "Router" },
      ],
      links: [
        { source_ieee: "0x1", target_ieee: "0x2", route_count: 2 },
        { source_ieee: "0X2", target_ieee: " 0x1 ", route_count: 0 },
        { source_ieee: "0x2", target_ieee: "0x3", route_count: null },
      ],
      inventory: { device_count: 4, router_count: 1, end_device_count: 2 },
      historical_neighbors: [historicalNeighbor],
      historical_routes: [historicalRoute],
      history_window: evaluatedHistoryWindow,
      last_known_links: [lastKnownLink],
      last_known_window: evaluatedLastKnownWindow,
      passive_hints: [passiveHint],
    });

    expect(detail.layout_available).toBe(true);
    expect(detail.latest_layout_limited).toBe(false);
    expect(detail.latest_snapshot?.link_count).toBe(3);
    expect(detail.latest_snapshot?.router_count).toBe(1);
    expect(detail.latest_snapshot?.end_device_count).toBe(0);
    expect(detail.counts).toEqual({
      latest_snapshot_neighbor_edges: 2,
      latest_snapshot_route_edges: 1,
      historical_neighbor_edges: 1,
      historical_route_edges: 1,
      recent_missing_link_count_total: 2,
      last_known_link_count: 1,
      passive_hint_count_available: 1,
      passive_hint_count_total: 1,
      passive_hint_count_drawn: null,
      hidden_for_readability: null,
      known_inventory_devices: 4,
      observed_topology_nodes: 2,
    });
  });

  it("derives an honest limited layout for an empty latest snapshot", () => {
    const detail = makeTopologyEvidenceGraphDetail();

    expect(detail.layout_available).toBe(false);
    expect(detail.latest_layout_limited).toBe(true);
    expect(detail.latest_snapshot?.link_count).toBe(0);
    expect(detail.history_window.snapshots_considered).toBe(0);
    expect(detail.history_window.max_snapshots).toBe(3);
    expect(detail.last_known_window.snapshots_considered).toBe(0);
    expect(detail.device_stats_window).toEqual({
      days: 7,
      max_snapshots: 10,
      snapshots_considered: 0,
    });
  });

  it("does not count route_count zero as a latest route edge", () => {
    const detail = makeTopologyEvidenceGraphDetail({
      links: [{ source_ieee: "0x1", target_ieee: "0x2", route_count: 0 }],
    });

    expect(detail.counts.latest_snapshot_neighbor_edges).toBe(1);
    expect(detail.counts.latest_snapshot_route_edges).toBe(0);
  });

  it("rejects structural overrides that contradict the evidence", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        layout_available: false,
      }),
    ).toThrow(/layout_available/);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        latest_layout_limited: true,
      }),
    ).toThrow(/latest_layout_limited/);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_layout_limited: false,
      }),
    ).toThrow(/latest_layout_limited/);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        links: [{ source_ieee: "0x1", target_ieee: "0x2" }],
        counts: { latest_snapshot_neighbor_edges: 9 },
      }),
    ).toThrow(/latest_snapshot_neighbor_edges/);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        links: [{ source_ieee: "0x1", target_ieee: "0x2" }],
        latest_snapshot: { snapshot_id: "bad", link_count: 0 },
      }),
    ).toThrow(/latest_snapshot\.link_count/);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        investigation_counts: { available: 1, returned: 1 },
      }),
    ).toThrow(/investigation_counts\.returned/);
  });

  it("rejects history evidence and timestamps that contradict evaluation windows", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({ historical_neighbors: [historicalNeighbor] }),
    ).toThrow(/history_window.*snapshots_considered > 0/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 3,
          snapshots_considered: 0,
          earliest_captured_at: "2026-07-01T00:00:00Z",
          latest_captured_at: null,
        },
      }),
    ).toThrow(/zero window requires null/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 3,
          snapshots_considered: 1,
          earliest_captured_at: null,
          latest_captured_at: null,
        },
      }),
    ).toThrow(/positive window requires valid/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 3,
          snapshots_considered: 1,
          earliest_captured_at: "2026-07-06T00:00:00Z",
          latest_captured_at: "2026-07-05T00:00:00Z",
        },
      }),
    ).toThrow(/earliest_captured_at cannot be later/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 3,
          snapshots_considered: 4,
          earliest_captured_at: "2026-07-01T00:00:00Z",
          latest_captured_at: "2026-07-05T00:00:00Z",
        },
      }),
    ).toThrow(/snapshots_considered cannot exceed max_snapshots/i);
  });

  it("rejects last-known evidence and timestamps that contradict evaluation windows", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({ last_known_links: [lastKnownLink] }),
    ).toThrow(/last_known_window.*snapshots_considered > 0/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        last_known_window: {
          snapshots_considered: 0,
          earliest_captured_at: null,
          latest_captured_at: "2026-07-05T00:00:00Z",
        },
      }),
    ).toThrow(/zero window requires null/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        last_known_window: {
          snapshots_considered: 1,
          earliest_captured_at: "not-a-timestamp",
          latest_captured_at: "2026-07-05T00:00:00Z",
        },
      }),
    ).toThrow(/positive window requires valid/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        last_known_window: {
          snapshots_considered: 1,
          earliest_captured_at: "2026-07-06T00:00:00Z",
          latest_captured_at: "2026-07-05T00:00:00Z",
        },
      }),
    ).toThrow(/earliest_captured_at cannot be later/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        last_known_window: evaluatedLastKnownWindow,
      }),
    ).toThrow(/zeroed last-known result when the latest layout is limited/i);
  });

  it("rejects latest evidence when there is no latest snapshot", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        nodes: [{ ieee_address: "0x1" }],
      }),
    ).toThrow(/latest_snapshot.*requires empty nodes and links/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        links: [{ source_ieee: "0x1", target_ieee: "0x2" }],
      }),
    ).toThrow(/latest_snapshot.*requires empty nodes and links/i);
  });

  it("rejects recent topology history when there is no latest snapshot", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        history_window: evaluatedHistoryWindow,
      }),
    ).toThrow(/latest_snapshot.*zeroed history_window/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        history_window: evaluatedHistoryWindow,
        historical_neighbors: [
          { ...historicalNeighbor, latest_layout_limited: true },
        ],
      }),
    ).toThrow(/latest_snapshot.*historical_neighbors/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        history_window: evaluatedHistoryWindow,
        historical_routes: [
          { ...historicalRoute, latest_layout_limited: true },
        ],
      }),
    ).toThrow(/latest_snapshot.*historical_routes/i);
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        history_window: {
          days: 7,
          max_snapshots: 3,
          snapshots_considered: 0,
          earliest_captured_at: "2026-07-01T00:00:00Z",
          latest_captured_at: null,
        },
      }),
    ).toThrow(/latest_snapshot.*zeroed history_window/i);
  });

  it("rejects last-known topology history when there is no latest snapshot", () => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({
        latest_snapshot: null,
        last_known_window: evaluatedLastKnownWindow,
        last_known_links: [lastKnownLink],
      }),
    ).toThrow(/latest_snapshot.*zeroed last_known_window/i);
  });

  it("permits null-snapshot topology history only through the named malformed opt-in", () => {
    const detail = makeTopologyEvidenceGraphDetail(
      {
        latest_snapshot: null,
        history_window: evaluatedHistoryWindow,
        historical_neighbors: [
          { ...historicalNeighbor, latest_layout_limited: true },
        ],
        historical_routes: [
          { ...historicalRoute, latest_layout_limited: true },
        ],
      },
      { allowInconsistentOverrides: true },
    );

    expect(detail.latest_snapshot).toBeNull();
    expect(detail.history_window.snapshots_considered).toBe(2);
    expect(detail.historical_neighbors).toHaveLength(1);
    expect(detail.historical_routes).toHaveLength(1);
  });

  it("allows non-topology evidence when there is no latest snapshot", () => {
    const detail = makeTopologyEvidenceGraphDetail({
      latest_snapshot: null,
      inventory: { device_count: 2, router_count: 0, end_device_count: 2 },
      passive_hints: [passiveHint],
      investigations: [sharedAvailabilityInvestigation],
    });

    expect(detail.latest_snapshot).toBeNull();
    expect(detail.passive_hints).toEqual([passiveHint]);
    expect(detail.investigations).toEqual([sharedAvailabilityInvestigation]);
    expect(detail.history_window.snapshots_considered).toBe(0);
  });

  it("allows evaluated history with a non-null but empty-layout latest snapshot", () => {
    const detail = makeTopologyEvidenceGraphDetail({
      history_window: evaluatedHistoryWindow,
    });

    expect(detail.latest_snapshot).not.toBeNull();
    expect(detail.layout_available).toBe(false);
    expect(detail.latest_layout_limited).toBe(true);
    expect(detail.history_window.snapshots_considered).toBe(2);
  });

  it.each([
    {
      name: "negative snapshots_considered",
      window: { days: 7, max_snapshots: 10, snapshots_considered: -1 },
      error: /device_stats_window\.snapshots_considered.*non-negative integer/i,
    },
    {
      name: "fractional snapshots_considered",
      window: { days: 7, max_snapshots: 10, snapshots_considered: 1.5 },
      error: /device_stats_window\.snapshots_considered.*non-negative integer/i,
    },
    {
      name: "zero max_snapshots",
      window: { days: 7, max_snapshots: 0, snapshots_considered: 0 },
      error: /device_stats_window\.max_snapshots.*positive integer/i,
    },
    {
      name: "negative max_snapshots",
      window: { days: 7, max_snapshots: -1, snapshots_considered: 0 },
      error: /device_stats_window\.max_snapshots.*positive integer/i,
    },
    {
      name: "fractional max_snapshots",
      window: { days: 7, max_snapshots: 2.5, snapshots_considered: 0 },
      error: /device_stats_window\.max_snapshots.*positive integer/i,
    },
    {
      name: "zero days",
      window: { days: 0, max_snapshots: 10, snapshots_considered: 0 },
      error: /device_stats_window\.days.*positive integer/i,
    },
    {
      name: "negative days",
      window: { days: -1, max_snapshots: 10, snapshots_considered: 0 },
      error: /device_stats_window\.days.*positive integer/i,
    },
    {
      name: "fractional days",
      window: { days: 1.5, max_snapshots: 10, snapshots_considered: 0 },
      error: /device_stats_window\.days.*positive integer/i,
    },
    {
      name: "snapshots_considered over the cap",
      window: { days: 7, max_snapshots: 2, snapshots_considered: 3 },
      error: /snapshots_considered cannot exceed max_snapshots/i,
    },
  ])("rejects a device-stat window with $name", ({ window, error }) => {
    expect(() =>
      makeTopologyEvidenceGraphDetail({ device_stats_window: window }),
    ).toThrow(error);
  });

  it("accepts a positive integer device-stat window within its cap", () => {
    const detail = makeTopologyEvidenceGraphDetail({
      device_stats_window: { days: 1, max_snapshots: 4, snapshots_considered: 4 },
    });

    expect(detail.device_stats_window).toEqual({
      days: 1,
      max_snapshots: 4,
      snapshots_considered: 4,
    });
  });

  it("requires a named opt-in for a deliberately inconsistent DTO", () => {
    const detail = makeTopologyEvidenceGraphDetail(
      {
        nodes: [{ ieee_address: "0x1" }],
        latest_snapshot: null,
        layout_available: true,
        latest_layout_limited: true,
        historical_neighbors: [historicalNeighbor],
        last_known_links: [lastKnownLink],
        device_stats_window: { days: 0, max_snapshots: 0, snapshots_considered: -1 },
        counts: { observed_topology_nodes: 99 },
      },
      { allowInconsistentOverrides: true },
    );

    expect(detail.latest_snapshot).toBeNull();
    expect(detail.layout_available).toBe(true);
    expect(detail.latest_layout_limited).toBe(true);
    expect(detail.history_window.snapshots_considered).toBe(0);
    expect(detail.last_known_window.snapshots_considered).toBe(0);
    expect(detail.device_stats_window).toEqual({
      days: 0,
      max_snapshots: 0,
      snapshots_considered: -1,
    });
    expect(detail.counts.observed_topology_nodes).toBe(99);
  });
});
