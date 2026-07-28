import { ApiError } from "@/lib/api";
import type {
  AvailabilityCoverageStatus,
  DeviceSnapshotCompareCounts,
  DeviceSnapshotComparison,
  DeviceSnapshotHistoryAvailableRow,
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryLimitedRow,
  DeviceSnapshotHistoryRow,
  DeviceSnapshotPresenceComparison,
} from "@/types/devices";
import type {
  TopologyDeviceFactsDto,
} from "@/types/decisions";
import type {
  DeviceSnapshotComparisonFact,
  DeviceSnapshotLatestFact,
} from "@zigbeelens/shared";

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
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, [
      "latest_count",
      "selected_count",
      "latest_only_count",
      "selected_only_count",
      "changed_count",
    ])
  ) {
    protocolFailure();
  }
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
  if (
    latest_only_count > latest_count ||
    selected_only_count > selected_count ||
    latest_count - latest_only_count !==
      selected_count - selected_only_count ||
    changed_count > latest_count - latest_only_count
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

function parsePresenceComparison(
  value: unknown,
): DeviceSnapshotPresenceComparison {
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, ["latest", "selected", "changed"])
  ) {
    protocolFailure();
  }
  const latest = value.latest;
  const selected = value.selected;
  const changed = value.changed;
  if (
    typeof latest !== "boolean" ||
    typeof selected !== "boolean" ||
    typeof changed !== "boolean" ||
    changed !== (latest !== selected)
  ) {
    protocolFailure();
  }
  return { latest, selected, changed };
}

function parseComparison(value: unknown): DeviceSnapshotComparison {
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, [
      "status",
      "reasons",
      "suggested_checks",
      "device_presence",
      "link_counts",
      "route_hint_counts",
    ])
  ) {
    protocolFailure();
  }
  const status = value.status;
  if (
    typeof status !== "string" ||
    !(COMPARISON_STATUSES as readonly string[]).includes(status)
  ) {
    protocolFailure();
  }
  const device_presence = parsePresenceComparison(value.device_presence);
  const link_counts = parseCompareCounts(value.link_counts);
  const route_hint_counts = parseCompareCounts(value.route_hint_counts);
  const differenceCount =
    Number(device_presence.changed) +
    link_counts.latest_only_count +
    link_counts.selected_only_count +
    link_counts.changed_count +
    route_hint_counts.latest_only_count +
    route_hint_counts.selected_only_count +
    route_hint_counts.changed_count;
  if ((differenceCount === 0) !== (status === "no_notable_change")) {
    protocolFailure();
  }
  return {
    status: status as DeviceSnapshotComparison["status"],
    reasons: stringArray(value.reasons),
    suggested_checks: stringArray(value.suggested_checks),
    device_presence,
    link_counts,
    route_hint_counts,
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
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, [
      "snapshot_id",
      "captured_at",
      "is_latest",
      "layout_state",
      "is_usable",
      "device_present_in_snapshot",
      "links_for_device_count",
      "route_hints_for_device_count",
      "availability_coverage_status",
      "availability_state_near_snapshot",
      "comparison_to_latest",
    ])
  ) {
    protocolFailure();
  }
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

function parseLatestFact(value: unknown): DeviceSnapshotLatestFact {
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, ["code", "params"])
  ) {
    protocolFailure();
  }
  const code = requireString(value.code);
  if (!isPlainObject(value.params)) protocolFailure();
  const params = value.params;
  const device_ieee = requireString(params.device_ieee);

  if (
    code === "device_seen_in_latest_snapshot" ||
    code === "device_absent_from_latest_snapshot"
  ) {
    if (!hasExactKeys(params, ["device_ieee", "snapshot_id"])) {
      protocolFailure();
    }
    return {
      code,
      params: {
        device_ieee,
        snapshot_id: requireString(params.snapshot_id),
      },
    };
  }
  if (code === "device_has_latest_links") {
    if (
      !hasExactKeys(params, ["device_ieee", "link_count"]) ||
      !nonNegativeInt(params.link_count)
    ) {
      protocolFailure();
    }
    return {
      code,
      params: {
        device_ieee,
        link_count: params.link_count,
      },
    };
  }
  if (code === "device_no_latest_links") {
    if (!hasExactKeys(params, ["device_ieee"])) protocolFailure();
    return { code, params: { device_ieee } };
  }
  return protocolFailure();
}

function parseLatestFacts(value: unknown): DeviceSnapshotLatestFact[] {
  if (!Array.isArray(value)) protocolFailure();
  return value.map(parseLatestFact);
}

function hasExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  return (
    Object.keys(value).sort().join("\u0000") ===
    [...keys].sort().join("\u0000")
  );
}

function parseComparisonFact(value: unknown): DeviceSnapshotComparisonFact {
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, ["code", "params"])
  ) {
    protocolFailure();
  }
  const code = requireString(value.code);
  if (!isPlainObject(value.params)) protocolFailure();
  const params = value.params;
  const device_ieee = requireString(params.device_ieee);
  const snapshot_id = requireString(params.snapshot_id);

  if (code === "device_has_selected_snapshot_links") {
    if (
      !hasExactKeys(params, ["device_ieee", "snapshot_id", "link_count"]) ||
      !nonNegativeInt(params.link_count)
    ) {
      protocolFailure();
    }
    return {
      code,
      params: {
        device_ieee,
        snapshot_id,
        link_count: params.link_count,
      },
    };
  }

  if (code === "device_latest_vs_selected_changed") {
    if (
      !hasExactKeys(params, [
        "device_ieee",
        "comparison_status",
        "snapshot_id",
        "latest_device_present_in_snapshot",
        "selected_device_present_in_snapshot",
        "device_presence_changed",
      ]) ||
      (params.comparison_status !== "changed" &&
        params.comparison_status !== "watch" &&
        params.comparison_status !== "worth_reviewing") ||
      typeof params.latest_device_present_in_snapshot !== "boolean" ||
      typeof params.selected_device_present_in_snapshot !== "boolean" ||
      typeof params.device_presence_changed !== "boolean"
    ) {
      protocolFailure();
    }
    return {
      code,
      params: {
        device_ieee,
        comparison_status: params.comparison_status,
        snapshot_id,
        latest_device_present_in_snapshot:
          params.latest_device_present_in_snapshot,
        selected_device_present_in_snapshot:
          params.selected_device_present_in_snapshot,
        device_presence_changed: params.device_presence_changed,
      },
    };
  }

  if (code === "availability_coverage_affects_snapshot_comparison") {
    if (
      !hasExactKeys(params, [
        "device_ieee",
        "availability_coverage_status",
        "snapshot_id",
      ]) ||
      (params.availability_coverage_status !== "off" &&
        params.availability_coverage_status !== "building" &&
        params.availability_coverage_status !== "unknown")
    ) {
      protocolFailure();
    }
    return {
      code,
      params: {
        device_ieee,
        availability_coverage_status:
          params.availability_coverage_status,
        snapshot_id,
      },
    };
  }

  return protocolFailure();
}

function parseComparisonFacts(
  value: unknown,
): DeviceSnapshotComparisonFact[] {
  if (!Array.isArray(value)) protocolFailure();
  return value.map(parseComparisonFact);
}

function parseTopologyFacts(value: unknown): TopologyDeviceFactsDto {
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, [
      "stale_threshold_hours",
      "device_facts",
      "comparison_facts_by_snapshot_id",
    ])
  ) {
    protocolFailure();
  }
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
  const comparison_facts_by_snapshot_id: Record<
    string,
    DeviceSnapshotComparisonFact[]
  > = {};
  for (const [snapshotId, facts] of Object.entries(
    value.comparison_facts_by_snapshot_id,
  )) {
    if (!snapshotId) protocolFailure();
    comparison_facts_by_snapshot_id[snapshotId] =
      parseComparisonFacts(facts);
  }
  return {
    stale_threshold_hours,
    device_facts: parseLatestFacts(value.device_facts),
    comparison_facts_by_snapshot_id,
  };
}

function validateTopologyFacts(
  topologyFacts: TopologyDeviceFactsDto,
  latestSnapshot: DeviceSnapshotHistoryRow | null,
  snapshots: DeviceSnapshotHistoryRow[],
  deviceIeee: string,
): void {
  if (latestSnapshot === null || latestSnapshot.layout_state === "limited") {
    if (topologyFacts.device_facts.length > 0) protocolFailure();
  } else {
    const presenceFacts = topologyFacts.device_facts.filter(
      (fact) =>
        fact.code === "device_seen_in_latest_snapshot" ||
        fact.code === "device_absent_from_latest_snapshot",
    );
    const linkFacts = topologyFacts.device_facts.filter(
      (fact) =>
        fact.code === "device_has_latest_links" ||
        fact.code === "device_no_latest_links",
    );
    if (presenceFacts.length !== 1 || linkFacts.length !== 1) {
      protocolFailure();
    }
    const expectedPresenceCode = latestSnapshot.device_present_in_snapshot
      ? "device_seen_in_latest_snapshot"
      : "device_absent_from_latest_snapshot";
    const presenceFact = presenceFacts[0];
    if (
      presenceFact?.code !== expectedPresenceCode ||
      presenceFact.params.device_ieee !== deviceIeee ||
      presenceFact.params.snapshot_id !== latestSnapshot.snapshot_id
    ) {
      protocolFailure();
    }
    const expectedLinkCode =
      latestSnapshot.links_for_device_count > 0
        ? "device_has_latest_links"
        : "device_no_latest_links";
    const linkFact = linkFacts[0];
    if (
      linkFact?.code !== expectedLinkCode ||
      linkFact.params.device_ieee !== deviceIeee
    ) {
      protocolFailure();
    }
    if (
      linkFact.code === "device_has_latest_links" &&
      linkFact.params.link_count !== latestSnapshot.links_for_device_count
    ) {
      protocolFailure();
    }
  }

  const changedFactCode = "device_latest_vs_selected_changed";
  const expectedParamKeys = [
    "comparison_status",
    "device_ieee",
    "device_presence_changed",
    "latest_device_present_in_snapshot",
    "selected_device_present_in_snapshot",
    "snapshot_id",
  ];
  const rowsById = new Map(snapshots.map((row) => [row.snapshot_id, row]));

  for (const snapshotId of Object.keys(
    topologyFacts.comparison_facts_by_snapshot_id,
  )) {
    if (!rowsById.has(snapshotId)) protocolFailure();
  }

  for (const row of snapshots) {
    const facts =
      topologyFacts.comparison_facts_by_snapshot_id[row.snapshot_id] ?? [];
    if (
      facts.some(
        (fact) =>
          fact.params.device_ieee !== deviceIeee ||
          fact.params.snapshot_id !== row.snapshot_id,
      )
    ) {
      protocolFailure();
    }
    const changedFacts = facts.filter((fact) => fact.code === changedFactCode);
    const comparison = row.comparison_to_latest;
    const expectsChangedFact =
      comparison !== null && comparison.status !== "no_notable_change";
    if (changedFacts.length !== Number(expectsChangedFact)) protocolFailure();
    const selectedLinkFacts = facts.filter(
      (fact) => fact.code === "device_has_selected_snapshot_links",
    );
    const expectsSelectedLinkFact =
      comparison !== null &&
      row.layout_state === "available" &&
      row.links_for_device_count > 0;
    if (selectedLinkFacts.length !== Number(expectsSelectedLinkFact)) {
      protocolFailure();
    }
    if (
      selectedLinkFacts[0]?.code === "device_has_selected_snapshot_links" &&
      (row.layout_state !== "available" ||
        selectedLinkFacts[0].params.link_count !== row.links_for_device_count)
    ) {
      protocolFailure();
    }
    const coverageFacts = facts.filter(
      (fact) =>
        fact.code ===
        "availability_coverage_affects_snapshot_comparison",
    );
    const expectsCoverageFact =
      comparison !== null &&
      (row.availability_coverage_status === "off" ||
        row.availability_coverage_status === "building" ||
        row.availability_coverage_status === "unknown");
    if (coverageFacts.length !== Number(expectsCoverageFact)) {
      protocolFailure();
    }
    if (
      coverageFacts[0]?.code ===
        "availability_coverage_affects_snapshot_comparison" &&
      coverageFacts[0].params.availability_coverage_status !==
        row.availability_coverage_status
    ) {
      protocolFailure();
    }
    if (!expectsChangedFact || comparison === null) continue;

    const params = changedFacts[0]?.params;
    if (!isPlainObject(params)) protocolFailure();
    if (
      Object.keys(params).sort().join("\u0000") !==
      expectedParamKeys.join("\u0000")
    ) {
      protocolFailure();
    }
    if (
      params.device_ieee !== deviceIeee ||
      params.comparison_status !== comparison.status ||
      params.snapshot_id !== row.snapshot_id ||
      params.latest_device_present_in_snapshot !==
        comparison.device_presence.latest ||
      params.selected_device_present_in_snapshot !==
        comparison.device_presence.selected ||
      params.device_presence_changed !== comparison.device_presence.changed
    ) {
      protocolFailure();
    }
  }
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
  if (
    !isPlainObject(value) ||
    !hasExactKeys(value, [
      "network_id",
      "device_ieee",
      "friendly_name",
      "has_current_issue",
      "availability_tracking",
      "latest_snapshot",
      "snapshots",
      "topology_facts",
    ])
  ) {
    protocolFailure();
  }
  const network_id = requireString(value.network_id);
  const device_ieee = requireString(value.device_ieee);
  const friendly_name = nullableString(value.friendly_name);
  if (typeof value.has_current_issue !== "boolean") protocolFailure();
  const has_current_issue = value.has_current_issue;
  if (
    !isPlainObject(value.availability_tracking) ||
    !hasExactKeys(value.availability_tracking, [
      "enabled",
      "earliest_observation_at",
    ])
  ) {
    protocolFailure();
  }
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
    const comparison = row.comparison_to_latest;
    if (comparison !== null) {
      const presence = comparison.device_presence;
      if (
        latest_snapshot?.layout_state !== "available" ||
        row.layout_state !== "available" ||
        presence.latest !== latest_snapshot.device_present_in_snapshot ||
        presence.selected !== row.device_present_in_snapshot ||
        comparison.link_counts.latest_count !==
          latest_snapshot.links_for_device_count ||
        comparison.link_counts.selected_count !== row.links_for_device_count ||
        comparison.route_hint_counts.latest_count !==
          latest_snapshot.route_hints_for_device_count ||
        comparison.route_hint_counts.selected_count !==
          row.route_hints_for_device_count
      ) {
        protocolFailure();
      }
      const linkDifferences =
        comparison.link_counts.latest_only_count +
        comparison.link_counts.selected_only_count +
        comparison.link_counts.changed_count;
      const routeDifferences =
        comparison.route_hint_counts.latest_only_count +
        comparison.route_hint_counts.selected_only_count +
        comparison.route_hint_counts.changed_count;
      const anyDifference =
        presence.changed || linkDifferences > 0 || routeDifferences > 0;
      if (
        (comparison.status === "worth_reviewing") !==
        (has_current_issue && anyDifference)
      ) {
        protocolFailure();
      }
      if (
        presence.changed &&
        !has_current_issue &&
        linkDifferences === 0 &&
        routeDifferences === 0 &&
        comparison.status !== "changed"
      ) {
        protocolFailure();
      }
    }
  }

  const topology_facts = parseTopologyFacts(value.topology_facts);
  validateTopologyFacts(
    topology_facts,
    latest_snapshot,
    snapshots,
    device_ieee,
  );

  return {
    network_id,
    device_ieee,
    friendly_name,
    has_current_issue,
    availability_tracking,
    latest_snapshot,
    snapshots,
    topology_facts,
  };
}
