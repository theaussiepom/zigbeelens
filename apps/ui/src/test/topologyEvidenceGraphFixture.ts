import type {
  TopologyEvidenceGraphCounts,
  TopologyEvidenceGraphDetail,
} from "@/types/topology";

type FixtureOverrides = Omit<Partial<TopologyEvidenceGraphDetail>, "counts"> & {
  counts?: Partial<TopologyEvidenceGraphCounts>;
};

/**
 * Canonical exact evidence-graph DTO fixture.
 *
 * Every required public field is populated. Callers can override the evidence
 * they care about without silently falling back to the smaller network-detail
 * response shape.
 */
export function makeTopologyEvidenceGraphDetail(
  overrides: FixtureOverrides = {},
): TopologyEvidenceGraphDetail {
  const nodes = overrides.nodes ?? [];
  const historicalNeighbors = overrides.historical_neighbors ?? [];
  const historicalRoutes = overrides.historical_routes ?? [];
  const lastKnownLinks = overrides.last_known_links ?? [];
  const passiveHints = overrides.passive_hints ?? [];
  const investigations = overrides.investigations ?? [];
  const inventory =
    overrides.inventory === undefined
      ? { device_count: 0, router_count: 0, end_device_count: 0 }
      : overrides.inventory;

  const counts: TopologyEvidenceGraphCounts = {
    latest_snapshot_neighbor_edges: 0,
    latest_snapshot_route_edges: 0,
    historical_neighbor_edges: historicalNeighbors.length,
    historical_route_edges: historicalRoutes.length,
    recent_missing_link_count_total: historicalNeighbors.length + historicalRoutes.length,
    last_known_link_count: lastKnownLinks.length,
    passive_hint_count_available: passiveHints.length,
    passive_hint_count_total: passiveHints.length,
    passive_hint_count_drawn: null,
    hidden_for_readability: null,
    known_inventory_devices: inventory?.device_count ?? 0,
    observed_topology_nodes: nodes.length,
    ...overrides.counts,
  };

  return {
    network_id: "home",
    network_name: "Home",
    latest_snapshot: {
      snapshot_id: "snap-fixture",
      network_id: "home",
      captured_at: "2026-07-06T00:30:00+00:00",
      requested_by: "startup_scan",
      status: "complete",
      router_count: 0,
      end_device_count: 0,
      link_count: 0,
      error: null,
    },
    links: overrides.links ?? [],
    layout_available: overrides.layout_available ?? true,
    data_source: "latest_snapshot_plus_history",
    latest_layout_limited: false,
    history_window: {
      days: 7,
      max_snapshots: 30,
      snapshots_considered: 0,
      earliest_captured_at: null,
      latest_captured_at: null,
    },
    last_known_window: {
      snapshots_considered: 0,
      earliest_captured_at: null,
      latest_captured_at: null,
    },
    passive_hint_window: {
      days: 7,
      event_window_minutes: 5,
      min_repeated_windows: 2,
    },
    investigation_counts: {
      available: investigations.length,
      returned: investigations.length,
    },
    device_stats: {},
    device_stats_window: {
      days: 7,
      max_snapshots: 30,
      snapshots_considered: 0,
    },
    limitations: [],
    topology_facts: {
      stale_threshold_hours: null,
      network_facts: [],
      coverage: [],
    },
    ...overrides,
    nodes,
    historical_neighbors: historicalNeighbors,
    historical_routes: historicalRoutes,
    last_known_links: lastKnownLinks,
    passive_hints: passiveHints,
    investigations,
    inventory,
    counts,
  };
}
