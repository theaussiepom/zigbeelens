import type {
  TopologyEvidenceGraphCounts,
  TopologyEvidenceGraphDetail,
  TopologyLinkRow,
  TopologySnapshotSummary,
} from "@/types/topology";

type FixtureOverrides = Omit<Partial<TopologyEvidenceGraphDetail>, "counts"> & {
  counts?: Partial<TopologyEvidenceGraphCounts>;
};

interface FixtureOptions {
  /** Named escape hatch for tests that deliberately exercise malformed DTOs. */
  allowInconsistentOverrides?: boolean;
}

function normalizedEndpoint(value: string): string {
  return value.trim().toLowerCase();
}

function isUsableLink(link: TopologyLinkRow): boolean {
  const source = normalizedEndpoint(link.source_ieee);
  const target = normalizedEndpoint(link.target_ieee);
  return source.length > 0 && target.length > 0 && source !== target;
}

function latestNeighborPairCount(links: TopologyLinkRow[]): number {
  const pairs = new Set<string>();
  for (const link of links) {
    if (!isUsableLink(link)) continue;
    const pair = [normalizedEndpoint(link.source_ieee), normalizedEndpoint(link.target_ieee)]
      .sort()
      .join("|");
    pairs.add(pair);
  }
  return pairs.size;
}

function snapshotNodeCount(
  nodes: TopologyEvidenceGraphDetail["nodes"],
  nodeType: "router" | "enddevice",
): number {
  return nodes.filter(
    (node) => node.node_type?.trim().toLowerCase().replace(/[_\s-]/g, "") === nodeType,
  ).length;
}

function assertConsistent(
  field: string,
  explicit: unknown,
  derived: unknown,
  allowInconsistentOverrides: boolean,
): void {
  if (
    !allowInconsistentOverrides &&
    explicit !== undefined &&
    explicit !== derived
  ) {
    throw new Error(
      `Inconsistent topology evidence fixture override for ${field}: expected ${String(derived)}, received ${String(explicit)}`,
    );
  }
}

function isValidTimestamp(value: string | null | undefined): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function assertWindowCoherence(
  field: "history_window" | "last_known_window",
  window: {
    snapshots_considered: number;
    earliest_captured_at?: string | null;
    latest_captured_at?: string | null;
  },
  evidenceCount: number,
  allowInconsistentOverrides: boolean,
): void {
  if (allowInconsistentOverrides) return;

  const {
    snapshots_considered: snapshots,
    earliest_captured_at: earliest,
    latest_captured_at: latest,
  } = window;
  if (!Number.isInteger(snapshots) || snapshots < 0) {
    throw new Error(
      `Inconsistent topology evidence fixture override for ${field}.snapshots_considered: expected a non-negative integer`,
    );
  }
  if (snapshots === 0) {
    if (evidenceCount > 0) {
      throw new Error(
        `Inconsistent topology evidence fixture override for ${field}: evidence arrays require snapshots_considered > 0`,
      );
    }
    if (earliest !== null || latest !== null) {
      throw new Error(
        `Inconsistent topology evidence fixture override for ${field}: a zero window requires null earliest_captured_at and latest_captured_at`,
      );
    }
    return;
  }

  if (!isValidTimestamp(earliest) || !isValidTimestamp(latest)) {
    throw new Error(
      `Inconsistent topology evidence fixture override for ${field}: a positive window requires valid earliest_captured_at and latest_captured_at timestamps`,
    );
  }
  if (Date.parse(earliest) > Date.parse(latest)) {
    throw new Error(
      `Inconsistent topology evidence fixture override for ${field}: earliest_captured_at cannot be later than latest_captured_at`,
    );
  }
}

function assertCountOverrides(
  explicit: Partial<TopologyEvidenceGraphCounts> | undefined,
  derived: TopologyEvidenceGraphCounts,
  allowInconsistentOverrides: boolean,
): void {
  assertConsistent(
    "counts.latest_snapshot_neighbor_edges",
    explicit?.latest_snapshot_neighbor_edges,
    derived.latest_snapshot_neighbor_edges,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.latest_snapshot_route_edges",
    explicit?.latest_snapshot_route_edges,
    derived.latest_snapshot_route_edges,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.historical_neighbor_edges",
    explicit?.historical_neighbor_edges,
    derived.historical_neighbor_edges,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.historical_route_edges",
    explicit?.historical_route_edges,
    derived.historical_route_edges,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.recent_missing_link_count_total",
    explicit?.recent_missing_link_count_total,
    derived.recent_missing_link_count_total,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.last_known_link_count",
    explicit?.last_known_link_count,
    derived.last_known_link_count,
    allowInconsistentOverrides,
  );
  if (
    !allowInconsistentOverrides &&
    explicit?.passive_hint_count_available !== undefined &&
    explicit.passive_hint_count_available < derived.passive_hint_count_total
  ) {
    throw new Error(
      "Inconsistent topology evidence fixture override for counts.passive_hint_count_available: it cannot be lower than the returned passive-hint array length",
    );
  }
  assertConsistent(
    "counts.passive_hint_count_total",
    explicit?.passive_hint_count_total,
    derived.passive_hint_count_total,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.passive_hint_count_drawn",
    explicit?.passive_hint_count_drawn,
    derived.passive_hint_count_drawn,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.hidden_for_readability",
    explicit?.hidden_for_readability,
    derived.hidden_for_readability,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.known_inventory_devices",
    explicit?.known_inventory_devices,
    derived.known_inventory_devices,
    allowInconsistentOverrides,
  );
  assertConsistent(
    "counts.observed_topology_nodes",
    explicit?.observed_topology_nodes,
    derived.observed_topology_nodes,
    allowInconsistentOverrides,
  );
}

/**
 * Canonical exact evidence-graph DTO fixture.
 *
 * Structural counts are derived from the supplied evidence so the fixture
 * cannot silently describe a different graph than its arrays contain.
 */
export function makeTopologyEvidenceGraphDetail(
  overrides: FixtureOverrides = {},
  options: FixtureOptions = {},
): TopologyEvidenceGraphDetail {
  const allowInconsistentOverrides = options.allowInconsistentOverrides === true;
  const networkId = overrides.network_id ?? "home";
  const nodes = overrides.nodes ?? [];
  const links = overrides.links ?? [];
  const historicalNeighbors = overrides.historical_neighbors ?? [];
  const historicalRoutes = overrides.historical_routes ?? [];
  const lastKnownLinks = overrides.last_known_links ?? [];
  const passiveHints = overrides.passive_hints ?? [];
  const investigations = overrides.investigations ?? [];
  const inventory =
    overrides.inventory === undefined
      ? { device_count: 0, router_count: 0, end_device_count: 0 }
      : overrides.inventory;

  const derivedLayoutAvailable = nodes.length > 0 || links.length > 0;
  assertConsistent(
    "layout_available",
    overrides.layout_available,
    derivedLayoutAvailable,
    allowInconsistentOverrides,
  );
  const layoutAvailable = overrides.layout_available ?? derivedLayoutAvailable;
  const derivedLatestLayoutLimited = !layoutAvailable;
  assertConsistent(
    "latest_layout_limited",
    overrides.latest_layout_limited,
    !derivedLayoutAvailable,
    allowInconsistentOverrides,
  );
  const latestLayoutLimited =
    overrides.latest_layout_limited ?? derivedLatestLayoutLimited;

  if (overrides.latest_snapshot === null && !allowInconsistentOverrides) {
    if (nodes.length > 0 || links.length > 0 || layoutAvailable || !latestLayoutLimited) {
      throw new Error(
        "Inconsistent topology evidence fixture override for latest_snapshot: null requires empty nodes and links, layout_available false, and latest_layout_limited true",
      );
    }
  }

  const derivedCounts: TopologyEvidenceGraphCounts = {
    latest_snapshot_neighbor_edges: latestNeighborPairCount(links),
    latest_snapshot_route_edges: links.filter(
      (link) => isUsableLink(link) && link.route_count != null && link.route_count > 0,
    ).length,
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
  };
  assertCountOverrides(overrides.counts, derivedCounts, allowInconsistentOverrides);
  const counts: TopologyEvidenceGraphCounts = {
    ...derivedCounts,
    ...overrides.counts,
  };

  let latestSnapshot: TopologySnapshotSummary | null;
  if (overrides.latest_snapshot === null) {
    latestSnapshot = null;
  } else {
    const snapshotOverride = overrides.latest_snapshot ?? {};
    const derivedRouterCount = snapshotNodeCount(nodes, "router");
    const derivedEndDeviceCount = snapshotNodeCount(nodes, "enddevice");
    assertConsistent(
      "latest_snapshot.network_id",
      snapshotOverride.network_id,
      networkId,
      allowInconsistentOverrides,
    );
    assertConsistent(
      "latest_snapshot.router_count",
      snapshotOverride.router_count,
      derivedRouterCount,
      allowInconsistentOverrides,
    );
    assertConsistent(
      "latest_snapshot.end_device_count",
      snapshotOverride.end_device_count,
      derivedEndDeviceCount,
      allowInconsistentOverrides,
    );
    assertConsistent(
      "latest_snapshot.link_count",
      snapshotOverride.link_count,
      links.length,
      allowInconsistentOverrides,
    );
    latestSnapshot = {
      snapshot_id: "snap-fixture",
      captured_at: "2026-07-06T00:30:00+00:00",
      requested_by: "startup_scan",
      status: "complete",
      error: null,
      ...snapshotOverride,
      network_id:
        allowInconsistentOverrides && snapshotOverride.network_id !== undefined
          ? snapshotOverride.network_id
          : networkId,
      router_count:
        allowInconsistentOverrides && snapshotOverride.router_count !== undefined
          ? snapshotOverride.router_count
          : derivedRouterCount,
      end_device_count:
        allowInconsistentOverrides && snapshotOverride.end_device_count !== undefined
          ? snapshotOverride.end_device_count
          : derivedEndDeviceCount,
      link_count:
        allowInconsistentOverrides && snapshotOverride.link_count !== undefined
          ? snapshotOverride.link_count
          : links.length,
    };
  }

  const historyWindow = overrides.history_window ?? {
    days: 7,
    max_snapshots: 3,
    snapshots_considered: 0,
    earliest_captured_at: null,
    latest_captured_at: null,
  };
  const lastKnownWindow = overrides.last_known_window ?? {
    snapshots_considered: 0,
    earliest_captured_at: null,
    latest_captured_at: null,
  };
  assertWindowCoherence(
    "history_window",
    historyWindow,
    historicalNeighbors.length + historicalRoutes.length,
    allowInconsistentOverrides,
  );
  assertWindowCoherence(
    "last_known_window",
    lastKnownWindow,
    lastKnownLinks.length,
    allowInconsistentOverrides,
  );
  if (
    !allowInconsistentOverrides &&
    historyWindow.snapshots_considered > historyWindow.max_snapshots
  ) {
    throw new Error(
      "Inconsistent topology evidence fixture override for history_window: snapshots_considered cannot exceed max_snapshots",
    );
  }
  if (!allowInconsistentOverrides && latestLayoutLimited) {
    if (
      lastKnownWindow.snapshots_considered !== 0 ||
      lastKnownLinks.length > 0 ||
      lastKnownWindow.earliest_captured_at !== null ||
      lastKnownWindow.latest_captured_at !== null
    ) {
      throw new Error(
        "Inconsistent topology evidence fixture override for last_known_window: Core returns a zeroed last-known result when the latest layout is limited",
      );
    }
  }
  const investigationCounts = overrides.investigation_counts ?? {
    available: investigations.length,
    returned: investigations.length,
  };
  assertConsistent(
    "investigation_counts.returned",
    investigationCounts.returned,
    investigations.length,
    allowInconsistentOverrides,
  );
  if (
    !allowInconsistentOverrides &&
    investigationCounts.available < investigationCounts.returned
  ) {
    throw new Error(
      "Inconsistent topology evidence fixture override for investigation_counts.available: it cannot be lower than returned",
    );
  }

  return {
    network_id: networkId,
    network_name: overrides.network_name ?? "Home",
    latest_snapshot: latestSnapshot,
    nodes,
    links,
    inventory,
    layout_available: layoutAvailable,
    data_source: overrides.data_source ?? "latest_snapshot_plus_history",
    latest_layout_limited: latestLayoutLimited,
    history_window: historyWindow,
    historical_neighbors: historicalNeighbors,
    historical_routes: historicalRoutes,
    last_known_links: lastKnownLinks,
    last_known_window: lastKnownWindow,
    passive_hints: passiveHints,
    passive_hint_window: overrides.passive_hint_window ?? {
      days: 7,
      event_window_minutes: 5,
      min_repeated_windows: 2,
    },
    investigations,
    investigation_counts: investigationCounts,
    device_stats: overrides.device_stats ?? {},
    device_stats_window: overrides.device_stats_window ?? {
      days: 7,
      max_snapshots: 10,
      snapshots_considered: 0,
    },
    limitations: overrides.limitations ?? [],
    topology_facts: overrides.topology_facts ?? {
      stale_threshold_hours: null,
      network_facts: [],
      coverage: [],
    },
    counts,
  };
}
