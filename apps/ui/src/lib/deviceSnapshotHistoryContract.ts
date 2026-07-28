import { ApiError } from "@/lib/api";
import type {
  AvailabilityCoverageStatus,
  DeviceSnapshotCompareCounts,
  DeviceSnapshotComparison,
  DeviceSnapshotHistoryAvailableRow,
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryLimitedRow,
  DeviceSnapshotHistoryRow,
} from "@/types/devices";
import type {
  EvidenceFactDto,
  TopologyDeviceFactsDto,
} from "@/types/decisions";

const COMPARISON_STATUSES = [
  "no_notable_change",
  "changed",
  "watch",
  "worth_reviewing",
] as const;

const COVERAGE_STATUSES = ["off", "building", "tracked", "unknown"] as const;

function protocolFailure(): never {
  throw new ApiError("Core returned a malformed snapshot-history contract.", 0, {
    kind: "protocol",
    detail: "malformed",
  });
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonNegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function requireString(value: unknown): string {
  if (typeof value !== "string" || value.length === 0) protocolFailure();
  return value;
}

function nullableString(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== "string") protocolFailure();
  return value;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    protocolFailure();
  }
  return [...value];
}

function parseCompareCounts(value: unknown): DeviceSnapshotCompareCounts {
  if (!isPlainObject(value)) protocolFailure();
  const latest_count = value.latest_count;
  const selected_count = value.selected_count;
  const latest_only_count = value.latest_only_count;
  const selected_only_count = value.selected_only_count;
  const changed_count = value.changed_count;
  if (
    !nonNegativeInt(latest_count) ||
    !nonNegativeInt(selected_count) ||
    !nonNegativeInt(latest_only_count) ||
    !nonNegativeInt(selected_only_count) ||
    !nonNegativeInt(changed_count)
  ) {
    protocolFailure();
  }
  return {
    latest_count,
    selected_count,
    latest_only_count,
    selected_only_count,
    changed_count,
  };
}

function parseComparison(value: unknown): DeviceSnapshotComparison {
  if (!isPlainObject(value)) protocolFailure();
  const status = value.status;
  if (
    typeof status !== "string" ||
    !(COMPARISON_STATUSES as readonly string[]).includes(status)
  ) {
    protocolFailure();
  }
  return {
    status: status as DeviceSnapshotComparison["status"],
    reasons: stringArray(value.reasons),
    suggested_checks: stringArray(value.suggested_checks),
    link_counts: parseCompareCounts(value.link_counts),
    route_hint_counts: parseCompareCounts(value.route_hint_counts),
  };
}

function parseCoverageStatus(value: unknown): AvailabilityCoverageStatus {
  if (
    typeof value !== "string" ||
    !(COVERAGE_STATUSES as readonly string[]).includes(value)
  ) {
    protocolFailure();
  }
  return value as AvailabilityCoverageStatus;
}

function parseAvailabilityState(
  value: unknown,
): "online" | "offline" | null {
  if (value === null || value === "online" || value === "offline") return value;
  return protocolFailure();
}

function parseRow(value: unknown): DeviceSnapshotHistoryRow {
  if (!isPlainObject(value)) protocolFailure();
  const snapshot_id = requireString(value.snapshot_id);
  const captured_at = nullableString(value.captured_at);
  if (typeof value.is_latest !== "boolean") protocolFailure();
  const is_latest = value.is_latest;
  const availability_coverage_status = parseCoverageStatus(
    value.availability_coverage_status,
  );
  const availability_state_near_snapshot = parseAvailabilityState(
    value.availability_state_near_snapshot,
  );

  if (value.layout_state === "limited") {
    if (
      value.is_usable !== false ||
      value.device_present_in_snapshot !== null ||
      value.links_for_device_count !== null ||
      value.route_hints_for_device_count !== null ||
      value.comparison_to_latest !== null
    ) {
      protocolFailure();
    }
    const row: DeviceSnapshotHistoryLimitedRow = {
      snapshot_id,
      captured_at,
      is_latest,
      layout_state: "limited",
      is_usable: false,
      device_present_in_snapshot: null,
      links_for_device_count: null,
      route_hints_for_device_count: null,
      availability_coverage_status,
      availability_state_near_snapshot,
      comparison_to_latest: null,
    };
    return row;
  }

  if (value.layout_state !== "available" || value.is_usable !== true) {
    protocolFailure();
  }
  if (
    typeof value.device_present_in_snapshot !== "boolean" ||
    !nonNegativeInt(value.links_for_device_count) ||
    !nonNegativeInt(value.route_hints_for_device_count)
  ) {
    protocolFailure();
  }
  if (
    !value.device_present_in_snapshot &&
    (value.links_for_device_count !== 0 ||
      value.route_hints_for_device_count !== 0)
  ) {
    protocolFailure();
  }
  const comparison_to_latest =
    value.comparison_to_latest === null
      ? null
      : parseComparison(value.comparison_to_latest);
  if (is_latest && comparison_to_latest !== null) protocolFailure();
  const row: DeviceSnapshotHistoryAvailableRow = {
    snapshot_id,
    captured_at,
    is_latest,
    layout_state: "available",
    is_usable: true,
    device_present_in_snapshot: value.device_present_in_snapshot,
    links_for_device_count: value.links_for_device_count,
    route_hints_for_device_count: value.route_hints_for_device_count,
    availability_coverage_status,
    availability_state_near_snapshot,
    comparison_to_latest,
  };
  return row;
}

function parseFact(value: unknown): EvidenceFactDto {
  if (!isPlainObject(value)) protocolFailure();
  const code = requireString(value.code);
  if (
    value.params !== undefined &&
    !isPlainObject(value.params)
  ) {
    protocolFailure();
  }
  return {
    code,
    ...(value.params === undefined ? {} : { params: { ...value.params } }),
  };
}

function parseFacts(value: unknown): EvidenceFactDto[] {
  if (!Array.isArray(value)) protocolFailure();
  return value.map(parseFact);
}

function parseTopologyFacts(value: unknown): TopologyDeviceFactsDto {
  if (!isPlainObject(value)) protocolFailure();
  const stale_threshold_hours = value.stale_threshold_hours;
  if (
    stale_threshold_hours !== null &&
    !nonNegativeInt(stale_threshold_hours)
  ) {
    protocolFailure();
  }
  if (!isPlainObject(value.comparison_facts_by_snapshot_id)) {
    protocolFailure();
  }
  const comparison_facts_by_snapshot_id: Record<string, EvidenceFactDto[]> = {};
  for (const [snapshotId, facts] of Object.entries(
    value.comparison_facts_by_snapshot_id,
  )) {
    if (!snapshotId) protocolFailure();
    comparison_facts_by_snapshot_id[snapshotId] = parseFacts(facts);
  }
  return {
    stale_threshold_hours,
    device_facts: parseFacts(value.device_facts),
    comparison_facts_by_snapshot_id,
  };
}

/**
 * Strict runtime boundary for device snapshot history.
 *
 * Layout-limited rows are accepted only with null presence/count/comparison
 * fields. Legacy zero-shaped limited data fails closed as a protocol error.
 */
export function parseDeviceSnapshotHistoryDetail(
  value: unknown,
): DeviceSnapshotHistoryDetail {
  if (!isPlainObject(value)) protocolFailure();
  const network_id = requireString(value.network_id);
  const device_ieee = requireString(value.device_ieee);
  const friendly_name = nullableString(value.friendly_name);
  if (typeof value.has_current_issue !== "boolean") protocolFailure();
  if (!isPlainObject(value.availability_tracking)) protocolFailure();
  if (typeof value.availability_tracking.enabled !== "boolean") {
    protocolFailure();
  }
  const availability_tracking = {
    enabled: value.availability_tracking.enabled,
    earliest_observation_at: nullableString(
      value.availability_tracking.earliest_observation_at,
    ),
  };

  const latest_snapshot =
    value.latest_snapshot === null ? null : parseRow(value.latest_snapshot);
  if (latest_snapshot !== null && !latest_snapshot.is_latest) protocolFailure();
  if (!Array.isArray(value.snapshots)) protocolFailure();
  const snapshots = value.snapshots.map(parseRow);
  if (snapshots.some((row) => row.is_latest)) protocolFailure();
  if (latest_snapshot === null && snapshots.length > 0) protocolFailure();

  const snapshotIds = new Set<string>();
  if (latest_snapshot) snapshotIds.add(latest_snapshot.snapshot_id);
  for (const row of snapshots) {
    if (snapshotIds.has(row.snapshot_id)) protocolFailure();
    snapshotIds.add(row.snapshot_id);
    const comparisonRequired =
      latest_snapshot?.layout_state === "available" &&
      row.layout_state === "available";
    if (comparisonRequired !== (row.comparison_to_latest !== null)) {
      protocolFailure();
    }
  }

  return {
    network_id,
    device_ieee,
    friendly_name,
    has_current_issue: value.has_current_issue,
    availability_tracking,
    latest_snapshot,
    snapshots,
    topology_facts: parseTopologyFacts(value.topology_facts),
  };
}
