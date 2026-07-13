/** Topology and mesh evidence-graph API types. */

import type { DeviceDiagnosticStats, DeviceStatsWindow } from "@/types/devices";
import type { TopologyNetworkFactsDto } from "@/types/decisions";

export interface TopologyOverview {
  enabled: boolean;
  manual_capture_enabled: boolean;
  automatic_capture_enabled: boolean;
  capture_in_progress: boolean;
  last_capture_error?: string | null;
  networks: Array<{
    network_id: string;
    network_name: string;
    latest_snapshot?: {
      snapshot_id: string;
      captured_at: string;
      router_count: number;
      link_count: number;
      end_device_count: number;
    } | null;
  }>;
}

export interface TopologySnapshotSummary {
  snapshot_id: string;
  network_id: string;
  captured_at?: string | null;
  requested_by?: string | null;
  status?: string | null;
  router_count?: number | null;
  end_device_count?: number | null;
  link_count?: number | null;
  error?: string | null;
}

export interface TopologyNodeRow {
  ieee_address: string;
  friendly_name?: string | null;
  node_type?: string | null;
  depth?: number | null;
  lqi?: number | null;
}

export interface TopologyLinkRow {
  source_ieee: string;
  target_ieee: string;
  source_type?: string | null;
  target_type?: string | null;
  linkquality?: number | null;
  depth?: number | null;
  relationship?: string | null;
  /**
   * Route-table entries reported on this link by the raw network map.
   * null means routes were not reported (unknown), distinct from zero.
   */
  route_count?: number | null;
}

export interface TopologyInventoryCounts {
  device_count: number;
  router_count: number;
  end_device_count: number;
}

export interface TopologyNetworkDetail {
  network_id: string;
  network_name: string;
  latest_snapshot?: TopologySnapshotSummary | null;
  nodes: TopologyNodeRow[];
  links: TopologyLinkRow[];
  inventory?: TopologyInventoryCounts | null;
  layout_available?: boolean;
}

/**
 * One aggregated previously-seen relationship from the backend history
 * window. Unknown values are null — never zero.
 */
export interface HistoricalEdgeAggregate {
  source_ieee: string;
  target_ieee: string;
  evidence_class: "historical_neighbor" | "historical_route";
  directional: boolean;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  observed_count?: number | null;
  snapshot_count?: number | null;
  lqi_latest?: number | null;
  lqi_min?: number | null;
  lqi_median?: number | null;
  lqi_max?: number | null;
  route_observed_count?: number | null;
  last_route_count?: number | null;
  last_relationship?: string | null;
  last_snapshot_id?: string | null;
  last_captured_at?: string | null;
  not_seen_in_latest_snapshot: boolean;
  latest_layout_limited: boolean;
  confidence: "high" | "medium" | "low";
  limitations: string[];
}

export interface TopologyHistoryWindow {
  days: number;
  max_snapshots: number;
  snapshots_considered: number;
  earliest_captured_at?: string | null;
  latest_captured_at?: string | null;
}

/**
 * The most recent stored link evidence for a device with no links in the
 * latest snapshot (typically a sleepy battery device whose entries aged out
 * of router neighbour tables). Last known evidence, never a currently
 * reported link.
 */
export interface LastKnownLinkAggregate {
  source_ieee: string;
  target_ieee: string;
  evidence_class: "last_known_link";
  directional: false;
  last_reported_at: string;
  last_snapshot_id: string;
  lqi_latest?: number | null;
  last_relationship?: string | null;
  not_seen_in_latest_snapshot: true;
  confidence: "low";
  limitations: string[];
}

export interface LastKnownLinkWindow {
  snapshots_considered: number;
  earliest_captured_at?: string | null;
  latest_captured_at?: string | null;
}

/**
 * One passive-derived investigation hint from the backend. A hint means
 * only "worth investigating together": it is not topology evidence, not a
 * route, and never proof of current connectivity.
 */
export interface PassiveHintAggregate {
  source_ieee: string;
  target_ieee: string;
  evidence_class: "passive_derived_association";
  directional: false;
  confidence: "high" | "medium" | "low";
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  /** Number of correlated instability windows observed. */
  observed_count?: number | null;
  /** Whether an endpoint has an existing ZigbeeLens issue signal. */
  issue_related: boolean;
  rules_matched: string[];
  supporting_observations: string[];
  limitations: string[];
  suggested_investigation: string[];
}

export interface PassiveHintWindow {
  days: number;
  event_window_minutes: number;
  min_repeated_windows: number;
}

/**
 * One ranked problem-first investigation card from the backend. Cards are
 * investigation priorities built from existing evidence only — never
 * root-cause, routing or parentage claims.
 */
export interface InvestigationCard {
  id: string;
  type:
    | "issue_cluster"
    | "recent_missing_cluster"
    | "passive_instability_group"
    | "router_neighbourhood_review"
    | "diagnostics_limited_group";
  priority: "Review first" | "Worth checking" | "Lower priority";
  score: number;
  title: string;
  summary: string;
  why_it_matters: string;
  supporting_evidence: string[];
  limitations: string[];
  suggested_next_steps: string[];
  device_ieees: string[];
  /** Edge ids in the UI edge-id scheme, so the graph can draw them on focus. */
  edge_ids: string[];
  primary_device_ieee?: string | null;
  primary_neighbourhood_ieee?: string | null;
  created_from_evidence_classes: string[];
  latest_supporting_evidence_at?: string | null;
  /** Action-led grouping for decision-backed presentation. */
  action_group:
    | "check_power_reporting"
    | "review_observed_router_area"
    | "investigate_shared_event"
    | "improve_data_coverage"
    | "watch_only";
}

export interface InvestigationCounts {
  /** Cards that qualified before the backend cap. */
  available: number;
  /** Cards returned after the cap. */
  returned: number;
}

export interface TopologyEvidenceGraphCounts {
  latest_snapshot_neighbor_edges: number;
  latest_snapshot_route_edges: number;
  historical_neighbor_edges: number;
  historical_route_edges: number;
  /** Total recent missing links available in the history window. */
  recent_missing_link_count_total: number;
  /** Last known links for devices absent from the latest snapshot's links. */
  last_known_link_count: number;
  /** Passive hints that qualified in the lookback window, before caps. */
  passive_hint_count_available: number;
  /** Passive hints returned after backend caps. */
  passive_hint_count_total: number;
  /** Rendering subsets are chosen client-side; the API reports null. */
  passive_hint_count_drawn: number | null;
  /** Rendering subsets are chosen client-side; the API reports null. */
  hidden_for_readability: number | null;
  known_inventory_devices: number;
  observed_topology_nodes: number;
}

/** Response of GET /api/topology/{network_id}/evidence-graph. */
export interface TopologyEvidenceGraphDetail extends TopologyNetworkDetail {
  data_source: string;
  latest_layout_limited?: boolean;
  history_window: TopologyHistoryWindow;
  historical_neighbors: HistoricalEdgeAggregate[];
  historical_routes: HistoricalEdgeAggregate[];
  last_known_links: LastKnownLinkAggregate[];
  last_known_window: LastKnownLinkWindow;
  passive_hints: PassiveHintAggregate[];
  passive_hint_window: PassiveHintWindow;
  investigations: InvestigationCard[];
  investigation_counts: InvestigationCounts;
  device_stats: Record<string, DeviceDiagnosticStats>;
  device_stats_window: DeviceStatsWindow;
  limitations: string[];
  counts: TopologyEvidenceGraphCounts;
  topology_facts: TopologyNetworkFactsDto;
}

/* ------------------------------------------------------------------------ */
/* Advanced/debug: whole-network snapshot compare                            */
/* ------------------------------------------------------------------------ */

export type SnapshotCompareChangeType =
  | "newly_observed_device"
  | "device_no_topology_evidence"
  | "new_neighbour_link"
  | "missing_neighbour_link"
  | "changed_neighbour_link"
  | "new_route_hint"
  | "missing_route_hint"
  | "changed_route_hint"
  // Device-centric worth-reviewing insights (same clickable shape).
  | "issue_linked_topology_change"
  | "no_latest_neighbour_evidence_after_previous"
  | "large_router_evidence_change";

/** One human-facing change between the compared snapshots. */
export interface SnapshotCompareChange {
  id: string;
  type: SnapshotCompareChangeType;
  title: string;
  summary: string;
  device_ieees: string[];
  edge_key?: string | null;
  /** Recorded evidence before/after; unknown values are null, never zero. */
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  supporting_evidence: string[];
  practical_note: string;
  focus_device_ieees: string[];
  /** Candidate edge ids in the UI edge-id scheme, drawn when present. */
  focus_edge_ids: string[];
}

export interface SnapshotCompareSnapshot {
  snapshot_id: string;
  captured_at?: string | null;
  requested_by?: string | null;
  status?: string | null;
}

export interface SnapshotCompareCounts {
  newly_observed_devices: number;
  devices_no_topology_evidence: number;
  new_neighbour_links: number;
  neighbour_links_not_present_latest: number;
  changed_neighbour_links: number;
  new_route_hints: number;
  route_hints_not_present_latest: number;
  changed_route_hints: number;
  total_changes: number;
}

/**
 * Snapshot churn: changed link evidence as a share of the neighbour and
 * route evidence recorded across both compared snapshots. Describes
 * snapshot-to-snapshot evidence differences only — never risk or health.
 * Values are null when there is no comparison; unknown is never zero.
 */
export interface SnapshotCompareChurn {
  level: "low" | "moderate" | "high" | null;
  changed_evidence_total: number | null;
  available_compare_evidence: number | null;
}

/** Response of GET /api/topology/{network_id}/snapshots/compare (advanced/debug). */
export interface SnapshotCompareDetail {
  network_id: string;
  base_snapshot: SnapshotCompareSnapshot | null;
  compare_snapshot: SnapshotCompareSnapshot | null;
  comparison_window: { usable_snapshots: number };
  has_comparison: boolean;
  summary: string;
  summary_items: string[];
  changes: SnapshotCompareChange[];
  counts: SnapshotCompareCounts;
  churn: SnapshotCompareChurn;
  /** Device-centric insights worth reviewing first; clickable like changes. */
  worth_reviewing: SnapshotCompareChange[];
  limitations: string[];
}
