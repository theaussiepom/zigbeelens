import { describe, expect, it } from "vitest";
import type {
  HistoricalEdgeAggregate,
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
    expect(detail.device_stats_window).toMatchObject({ days: 7, max_snapshots: 10 });
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

  it("requires a named opt-in for a deliberately inconsistent DTO", () => {
    const detail = makeTopologyEvidenceGraphDetail(
      {
        nodes: [{ ieee_address: "0x1" }],
        latest_snapshot: null,
        layout_available: true,
        latest_layout_limited: true,
        historical_neighbors: [historicalNeighbor],
        last_known_links: [lastKnownLink],
        counts: { observed_topology_nodes: 99 },
      },
      { allowInconsistentOverrides: true },
    );

    expect(detail.latest_snapshot).toBeNull();
    expect(detail.layout_available).toBe(true);
    expect(detail.latest_layout_limited).toBe(true);
    expect(detail.history_window.snapshots_considered).toBe(0);
    expect(detail.last_known_window.snapshots_considered).toBe(0);
    expect(detail.counts.observed_topology_nodes).toBe(99);
  });
});
