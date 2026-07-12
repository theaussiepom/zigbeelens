import type { TopologyDeviceFactsDto } from "@/types/decisions";

/** Device-centric API types from Core topology and device endpoints. */

/** Snapshot-comparison status for one device. About the comparison only, never device health. */
export type DeviceSnapshotCompareStatus =
  | "no_notable_change"
  | "changed"
  | "watch"
  | "worth_reviewing";

/**
 * Availability tracking coverage for one snapshot period.
 * "off" = no usable availability history exists; "building" = tracking is
 * enabled now but started after the snapshot; "unknown" = coverage cannot
 * be confirmed. Unknown is never rendered as zero or a fake state.
 */
export type AvailabilityCoverageStatus = "off" | "building" | "tracked" | "unknown";

export interface DeviceSnapshotCompareCounts {
  latest_count: number;
  selected_count: number;
  latest_only_count: number;
  selected_only_count: number;
  changed_count: number;
}

export interface DeviceSnapshotComparison {
  status: DeviceSnapshotCompareStatus;
  reasons: string[];
  suggested_checks: string[];
  link_counts: DeviceSnapshotCompareCounts;
  route_hint_counts: DeviceSnapshotCompareCounts;
}

export interface DeviceSnapshotHistoryRow {
  snapshot_id: string;
  captured_at: string | null;
  is_latest: boolean;
  is_usable: boolean;
  links_for_device_count: number;
  route_hints_for_device_count: number;
  availability_coverage_status: AvailabilityCoverageStatus;
  availability_state_near_snapshot: "online" | "offline" | null;
  /** Null for the latest snapshot (nothing to compare it with). */
  comparison_to_latest: DeviceSnapshotComparison | null;
}

/** Response of GET /api/topology/{network_id}/devices/{ieee}/snapshot-history. */
export interface DeviceSnapshotHistoryDetail {
  network_id: string;
  device_ieee: string;
  friendly_name: string | null;
  has_current_issue: boolean;
  availability_tracking: {
    enabled: boolean;
    earliest_observation_at: string | null;
  };
  latest_snapshot: DeviceSnapshotHistoryRow | null;
  /** Earlier usable snapshots, newest first. */
  snapshots: DeviceSnapshotHistoryRow[];
  topology_facts: TopologyDeviceFactsDto;
}

/**
 * Per-device recorded diagnostic stats from recent snapshots and availability
 * transitions. Devices with no recorded data have no entry at all.
 */
export interface DeviceDiagnosticStats {
  /** Recent complete snapshots in which the device had at least one link. */
  snapshots_with_links: number;
  /** Newest snapshot time where the device linked to a router/coordinator. */
  last_router_link_at?: string | null;
  /** IEEE of that router/coordinator partner. */
  last_router_link_partner?: string | null;
  offline_events_24h: number;
  offline_events_7d: number;
  last_offline_at?: string | null;
}

export interface DeviceStatsWindow {
  days: number;
  max_snapshots: number;
  snapshots_considered: number;
}
