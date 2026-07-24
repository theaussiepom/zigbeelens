import type { DeviceSummary } from "@zigbeelens/shared";
import type {
  DeviceDiagnosticStats,
  DeviceStatsWindow,
  HistoricalEdgeAggregate,
  LastKnownLinkAggregate,
  PassiveHintAggregate,
  TopologyEvidenceGraphDetail,
  TopologyLinkRow,
  TopologyNodeRow,
} from "@/lib/api";
import type {
  MeshDiagnosticStat,
  MeshEvidenceDevice,
  MeshEvidenceEdge,
  MeshHealthBucket,
  MeshNodeFlag,
  MeshRole,
} from "@/lib/meshEvidence";
import { formatTime, relativeTime } from "@/lib/format";

/**
 * Map real topology data + device inventory into the mesh evidence model.
 *
 * This mapper produces `latest_snapshot_neighbor` / `latest_snapshot_route`
 * evidence from the latest snapshot, `historical_neighbor` /
 * `historical_route` evidence from backend-aggregated previous complete
 * snapshots, and `passive_derived_association` investigation hints from the
 * backend passive rule engine when present. Passive hints are mapped
 * one-to-one from backend output — they must never be fabricated from
 * snapshots or inventory data. The stale/low-confidence class has no live
 * source yet.
 */

export const LIVE_NEIGHBOR_SAFE_COPY =
  "This link was reported in the latest topology snapshot. It does not prove current live routing.";

export const LIVE_ROUTE_SAFE_COPY =
  "Route-table evidence was reported in the latest scan where the next hop matched this neighbour. " +
  "This suggests route evidence at capture time, not a guaranteed current path.";

export const SLEEPY_NO_LINK_COPY =
  "No topology link is available from the latest snapshot. This can be normal for sleepy battery devices and is not an incident by itself.";

const NO_LINK_COPY =
  "No topology link is available from the latest snapshot. Missing topology data limits mesh context; it is not an incident by itself.";

export interface LiveMeshEvidence {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
}

function normalizeIeee(value: string): string {
  return value.trim().toLowerCase();
}

function roleFromType(deviceType: string | null | undefined): MeshRole {
  switch (deviceType) {
    case "Coordinator":
      return "coordinator";
    case "Router":
      return "router";
    case "EndDevice":
      return "end_device";
    default:
      return "unknown";
  }
}

function bucketFromDecision(status: string | undefined): MeshHealthBucket {
  switch (status) {
    case "no_notable_change":
    case "informational":
      return "healthy";
    case "review_first":
    case "worth_reviewing":
      return "needs_attention";
    case "watch":
    case "changed":
      return "recently_unstable";
    case "improve_data_coverage":
      return "diagnostics_limited";
    case "data_unavailable":
      return "unknown";
    default:
      return "unknown";
  }
}

function flagsForDevice(summary: DeviceSummary, role: MeshRole): MeshNodeFlag[] {
  const flags: MeshNodeFlag[] = [];
  const status = summary.decision?.status;
  if (summary.availability === "offline" || status === "review_first") {
    flags.push("unavailable");
  }
  if (status === "worth_reviewing" || status === "review_first") {
    flags.push("needs_attention");
  }
  if (status === "improve_data_coverage" || status === "data_unavailable") {
    flags.push("diagnostics_limited");
  }
  if (summary.interview_state === "failed") flags.push("interview_failure");
  const headline = summary.decision?.headline_code ?? "";
  if (headline.includes("weak_link")) {
    flags.push("weak_link_candidate");
  }
  if (headline.includes("router_risk")) {
    flags.push("router_risk_candidate");
  }
  if (summary.power_source === "Battery" && role === "end_device") flags.push("battery_sleepy");
  return flags;
}

function topologySummary(
  node: TopologyNodeRow | undefined,
  neighborCount: number,
  sleepy: boolean,
): string {
  if (!node && neighborCount === 0) {
    return sleepy ? SLEEPY_NO_LINK_COPY : NO_LINK_COPY;
  }
  if (!node) {
    return `Referenced by ${neighborCount} topology link ${
      neighborCount === 1 ? "entry" : "entries"
    } in the latest snapshot, but no node details were reported.`;
  }
  const parts = ["Observed in the latest topology snapshot"];
  if (neighborCount > 0) {
    parts.push(`with ${neighborCount} neighbour ${neighborCount === 1 ? "entry" : "entries"}`);
  }
  if (node?.lqi != null) parts.push(`(LQI ${node.lqi})`);
  return `${parts.join(" ")}.`;
}

/** Inputs available when building one device's diagnostic stats. */
interface DiagnosticStatInputs {
  summary: DeviceSummary | undefined;
  /** Link entries touching this device in the latest snapshot. */
  neighborCount: number;
  /** Whether the latest snapshot produced a usable layout at all. */
  layoutAvailable: boolean;
  /** Strongest LQI recorded on this device's latest-snapshot links. */
  strongestLiveLqi: number | null;
  /** Recent missing links touching this device (history window). */
  recentMissingCount: number | null;
  /** Backend per-device stats, if the device has any recorded data. */
  backendStats: DeviceDiagnosticStats | undefined;
  backendWindow: DeviceStatsWindow | undefined;
  /** Resolve an IEEE address to a friendly name for display. */
  nameFor: (ieee: string) => string;
}

/**
 * Repeatable diagnostic stats for the node drawer. Each row is a recorded
 * value — nothing inferred, nothing shown for values that were never
 * recorded (unknown never renders as zero).
 *
 * Core omits devices with no recorded links/availability from `device_stats`
 * entirely; that absence is unknown, not a fabricated zero record.
 */
export function diagnosticStatsFor(inputs: DiagnosticStatInputs): MeshDiagnosticStat[] {
  const {
    summary,
    neighborCount,
    layoutAvailable,
    strongestLiveLqi,
    recentMissingCount,
    backendStats,
    backendWindow,
    nameFor,
  } = inputs;
  const stats: MeshDiagnosticStat[] = [];

  if (summary?.last_seen) {
    stats.push({
      label: "Last seen",
      value: relativeTime(summary.last_seen),
      detail: formatTime(summary.last_seen),
    });
  }
  if (summary?.last_payload_at) {
    stats.push({
      label: "Last message payload",
      value: relativeTime(summary.last_payload_at),
      detail: formatTime(summary.last_payload_at),
    });
  }
  if (summary?.battery != null) {
    stats.push({ label: "Battery level", value: `${summary.battery}%` });
  }
  if (summary?.linkquality != null) {
    stats.push({ label: "Reported link quality", value: `LQI ${summary.linkquality}` });
  }

  if (layoutAvailable) {
    stats.push({
      label: "Links in latest snapshot",
      value: String(neighborCount),
    });
  }
  if (strongestLiveLqi != null) {
    stats.push({ label: "Strongest link (latest snapshot)", value: `LQI ${strongestLiveLqi}` });
  }
  if (recentMissingCount != null && recentMissingCount > 0) {
    stats.push({
      label: "Recent missing links (7 days)",
      value: String(recentMissingCount),
    });
  }

  // Require an explicit per-device stats entry. Window metadata alone does not
  // mean snapshots_with_links was measured as zero for this IEEE.
  if (backendWindow && backendWindow.snapshots_considered > 0 && backendStats) {
    stats.push({
      label: `Snapshots with links (last ${backendWindow.days} days)`,
      value: `${backendStats.snapshots_with_links} of ${backendWindow.snapshots_considered}`,
    });
  }
  if (backendStats?.last_router_link_at) {
    stats.push({
      label: "Last router link observed",
      value: relativeTime(backendStats.last_router_link_at),
      detail: backendStats.last_router_link_partner
        ? `to ${nameFor(backendStats.last_router_link_partner)} · ${formatTime(backendStats.last_router_link_at)}`
        : formatTime(backendStats.last_router_link_at),
    });
  }

  // Offline transition counts are only meaningful when availability is
  // actually tracked for this device; otherwise a zero would present
  // "not measured" as "measured stable".
  const availabilityTracked = summary
    ? summary.availability === "online" || summary.availability === "offline"
    : false;
  if (backendStats && (availabilityTracked || backendStats.offline_events_7d > 0)) {
    stats.push({
      label: "Offline events (24 h)",
      value: String(backendStats.offline_events_24h),
    });
    stats.push({
      label: "Offline events (7 days)",
      value: String(backendStats.offline_events_7d),
      detail: backendStats.last_offline_at
        ? `last ${relativeTime(backendStats.last_offline_at)}`
        : undefined,
    });
  }

  return stats;
}

/**
 * Node details summary of recent missing links touching one device.
 * Returns null when none touch the device — the panel omits the section.
 */
function historicalSummaryFor(
  historicalEdges: MeshEvidenceEdge[],
  ieee: string,
  latestLayoutLimited: boolean,
): string | null {
  const touching = historicalEdges.filter(
    (edge) => edge.source === ieee || edge.target === ieee,
  );
  if (touching.length === 0) {
    return null;
  }
  const lastSeen = touching
    .map((edge) => edge.last_seen_at)
    .filter((v): v is string => Boolean(v))
    .sort()
    .at(-1);
  const parts = [
    `${touching.length} recent missing link${touching.length === 1 ? "" : "s"} in the selected history window.`,
  ];
  if (lastSeen) {
    parts.push(`Last seen in topology evidence ${relativeTime(lastSeen)}.`);
  }
  if (latestLayoutLimited) {
    parts.push(
      "The latest snapshot has limited topology evidence, so absence from the latest graph is not meaningful by itself.",
    );
  }
  return parts.join(" ");
}

/**
 * Node-drawer summary when passive hints touch this device. Returns null when
 * none do — the drawer omits the section rather than showing empty copy.
 */
function passiveHintSummaryFor(
  passiveEdges: MeshEvidenceEdge[],
  ieee: string,
): string | null {
  const touching = passiveEdges.filter((edge) => edge.source === ieee || edge.target === ieee);
  if (touching.length === 0) {
    return null;
  }
  return `${touching.length} passive-derived investigation hint${
    touching.length === 1 ? "" : "s"
  } involve${touching.length === 1 ? "s" : ""} this device. These are not topology links or proof of live routing.`;
}

/** Map one backend last-known link into a mesh evidence edge, one-to-one. */
function buildLastKnownEdge(
  aggregate: LastKnownLinkAggregate,
  networkId: string,
): MeshEvidenceEdge {
  const source = normalizeIeee(aggregate.source_ieee);
  const target = normalizeIeee(aggregate.target_ieee);
  return {
    id: `last-known-${[source, target].sort().join("|")}`,
    network_id: networkId,
    source,
    target,
    evidence_class: "last_known_link",
    confidence: "low",
    directional: false,
    issue_related: false,
    in_latest_snapshot: false,
    captured_at: aggregate.last_reported_at,
    observed_relationship: aggregate.last_relationship ?? null,
    first_seen_at: null,
    last_seen_at: aggregate.last_reported_at,
    observed_count: null,
    snapshot_count: null,
    lqi_latest: aggregate.lqi_latest ?? null,
    lqi_min: null,
    lqi_median: null,
    lqi_max: null,
    route_table_evidence: null,
    next_hop_evidence: null,
    route_observed_count: null,
    last_route_count: null,
    latest_layout_limited: null,
    passive_corroboration: null,
    limitations: aggregate.limitations,
    suggested_investigation: [],
  };
}

/** Map one backend passive hint into a mesh evidence edge, one-to-one. */
function buildPassiveHintEdge(hint: PassiveHintAggregate, networkId: string): MeshEvidenceEdge {
  const source = normalizeIeee(hint.source_ieee);
  const target = normalizeIeee(hint.target_ieee);
  return {
    id: `passive-hint-${[source, target].sort().join("|")}`,
    network_id: networkId,
    source,
    target,
    evidence_class: "passive_derived_association",
    confidence: hint.confidence,
    // Passive hints are never directional: no route or next-hop is implied.
    directional: false,
    issue_related: hint.issue_related,
    in_latest_snapshot: false,
    captured_at: null,
    observed_relationship: null,
    first_seen_at: hint.first_seen_at ?? null,
    last_seen_at: hint.last_seen_at ?? null,
    observed_count: hint.observed_count ?? null,
    snapshot_count: null,
    lqi_latest: null,
    lqi_min: null,
    lqi_median: null,
    lqi_max: null,
    route_table_evidence: null,
    next_hop_evidence: null,
    route_observed_count: null,
    last_route_count: null,
    latest_layout_limited: null,
    passive_corroboration: null,
    rules_matched: hint.rules_matched,
    supporting_observations: hint.supporting_observations,
    limitations: hint.limitations,
    suggested_investigation: hint.suggested_investigation,
  };
}

function buildDevice(
  ieee: string,
  networkId: string,
  summary: DeviceSummary | undefined,
  inventoryAccepted: boolean,
  node: TopologyNodeRow | undefined,
  neighborCount: number,
  diagnosticStats: MeshDiagnosticStat[],
): MeshEvidenceDevice {
  const role = summary ? roleFromType(summary.device_type) : roleFromType(node?.node_type);
  const sleepy = summary?.power_source === "Battery" && role === "end_device";
  const homeAssistantName = summary?.home_assistant_name?.trim() || null;
  return {
    ieee_address: ieee,
    network_id: networkId,
    friendly_name: homeAssistantName || summary?.friendly_name || node?.friendly_name || ieee,
    role,
    power:
      summary?.power_source === "Battery"
        ? "battery"
        : summary?.power_source === "Mains"
          ? "mains"
          : "unknown",
    availability:
      summary?.availability === "online"
        ? "online"
        : summary?.availability === "offline"
          ? "offline"
          : "unknown",
    manufacturer: summary?.manufacturer ?? null,
    model: summary?.model ?? null,
    in_inventory: summary ? true : inventoryAccepted ? false : null,
    in_latest_snapshot: Boolean(node),
    last_seen_at: summary?.last_seen ?? null,
    health_bucket: summary ? bucketFromDecision(summary.decision?.status) : "unknown",
    flags: summary ? flagsForDevice(summary, role) : [],
    inventory_status: summary
      ? "In Zigbee2MQTT device inventory"
      : !inventoryAccepted
        ? "Device inventory unavailable — inventory status unknown"
        : node
          ? "Observed in topology snapshot only — not in the current device inventory"
          : "Referenced by topology links only — not in the current device inventory or node list",
    topology_evidence_summary: topologySummary(node, neighborCount, sleepy),
    passive_observation_summary: summary?.decision?.headline_code
      ? summary.decision.headline_code.replace(/_/g, " ")
      : "",
    open_issue: summary?.incident_affected
      ? {
          title: "Linked to an active incident",
          summary:
            "This device is referenced by an open incident. See the Incidents page for the evidence trail.",
        }
      : null,
    diagnostic_stats: diagnosticStats,
  };
}

interface NeighborAccumulator {
  link: TopologyLinkRow;
  bothDirections: boolean;
}

/** Map one backend historical aggregate into a mesh evidence edge. */
function buildHistoricalEdge(
  aggregate: HistoricalEdgeAggregate,
  networkId: string,
): MeshEvidenceEdge {
  const source = normalizeIeee(aggregate.source_ieee);
  const target = normalizeIeee(aggregate.target_ieee);
  const isRoute = aggregate.evidence_class === "historical_route";
  const id = isRoute
    ? `hist-route-${source}-${target}`
    : `hist-neighbor-${[source, target].sort().join("|")}`;
  return {
    id,
    network_id: networkId,
    source,
    target,
    evidence_class: aggregate.evidence_class,
    confidence: aggregate.confidence,
    directional: aggregate.directional,
    issue_related: false,
    in_latest_snapshot: false,
    captured_at: aggregate.last_captured_at ?? null,
    observed_relationship: aggregate.last_relationship ?? null,
    first_seen_at: aggregate.first_seen_at ?? null,
    last_seen_at: aggregate.last_seen_at ?? null,
    observed_count: aggregate.observed_count ?? null,
    snapshot_count: aggregate.snapshot_count ?? null,
    lqi_latest: aggregate.lqi_latest ?? null,
    lqi_min: aggregate.lqi_min ?? null,
    lqi_median: aggregate.lqi_median ?? null,
    lqi_max: aggregate.lqi_max ?? null,
    route_table_evidence: isRoute ? true : null,
    next_hop_evidence: isRoute ? true : null,
    route_observed_count: aggregate.route_observed_count ?? null,
    last_route_count: aggregate.last_route_count ?? null,
    latest_layout_limited: aggregate.latest_layout_limited,
    passive_corroboration: null,
    limitations: aggregate.limitations,
    suggested_investigation: [],
  };
}

/**
 * Build the live evidence set from the latest snapshot plus inventory.
 * Neighbour entries reported in both directions collapse into one
 * non-directional edge; route-table entries produce directional route edges.
 * Backend-aggregated historical (recent missing) evidence maps to
 * historical_neighbor / historical_route edges.
 */
export function buildLiveMeshEvidence(
  detail: TopologyEvidenceGraphDetail,
  inventoryDevices: DeviceSummary[] | null,
): LiveMeshEvidence {
  const networkId = detail.network_id;
  const capturedAt = detail.latest_snapshot?.captured_at ?? null;
  const nodes = detail.nodes ?? [];
  const links = detail.links ?? [];

  const nodeByIeee = new Map<string, TopologyNodeRow>();
  for (const node of nodes) nodeByIeee.set(normalizeIeee(node.ieee_address), node);

  const inventoryAccepted = inventoryDevices !== null;
  const summaryByIeee = new Map<string, DeviceSummary>();
  for (const device of inventoryDevices ?? []) {
    summaryByIeee.set(normalizeIeee(device.ieee_address), device);
  }

  const neighborCounts = new Map<string, number>();
  const bumpNeighbor = (ieee: string) =>
    neighborCounts.set(ieee, (neighborCounts.get(ieee) ?? 0) + 1);

  // Collapse per-direction neighbour entries into unordered pairs.
  const neighborPairs = new Map<string, NeighborAccumulator>();
  for (const link of links) {
    const source = normalizeIeee(link.source_ieee);
    const target = normalizeIeee(link.target_ieee);
    if (!source || !target || source === target) continue;
    bumpNeighbor(source);
    bumpNeighbor(target);
    const key = [source, target].sort().join("|");
    const existing = neighborPairs.get(key);
    if (existing) {
      existing.bothDirections = true;
      // Prefer the direction that reported an LQI value.
      if (existing.link.linkquality == null && link.linkquality != null) {
        existing.link = link;
      }
    } else {
      neighborPairs.set(key, { link, bothDirections: false });
    }
  }

  const edges: MeshEvidenceEdge[] = [];

  for (const [key, { link, bothDirections }] of neighborPairs) {
    const source = normalizeIeee(link.source_ieee);
    const target = normalizeIeee(link.target_ieee);
    const limitations = [
      LIVE_NEIGHBOR_SAFE_COPY,
      "Neighbour tables are point-in-time; entries can appear or disappear between snapshots without any fault.",
    ];
    if (bothDirections) {
      limitations.push(
        "Zigbee2MQTT reported this neighbour entry in both directions; values shown come from one direction.",
      );
    }
    edges.push({
      id: `live-neighbor-${key}`,
      network_id: networkId,
      source,
      target,
      evidence_class: "latest_snapshot_neighbor",
      confidence: "high",
      directional: false,
      issue_related: false,
      in_latest_snapshot: true,
      captured_at: capturedAt,
      observed_relationship: link.relationship ?? null,
      first_seen_at: null,
      last_seen_at: capturedAt,
      observed_count: null,
      snapshot_count: null,
      lqi_latest: link.linkquality ?? null,
      lqi_min: null,
      lqi_median: null,
      lqi_max: null,
      route_table_evidence: link.route_count == null ? null : link.route_count > 0,
      next_hop_evidence: link.route_count == null ? null : link.route_count > 0,
      route_observed_count: link.route_count ?? null,
      passive_corroboration: null,
      limitations,
      suggested_investigation: [],
    });
  }

  // Directional route edges only where real route-table entries exist.
  for (const link of links) {
    if (link.route_count == null || link.route_count <= 0) continue;
    const source = normalizeIeee(link.source_ieee);
    const target = normalizeIeee(link.target_ieee);
    if (!source || !target || source === target) continue;
    edges.push({
      id: `live-route-${source}-${target}`,
      network_id: networkId,
      source,
      target,
      evidence_class: "latest_snapshot_route",
      confidence: "medium",
      directional: true,
      issue_related: false,
      in_latest_snapshot: true,
      captured_at: capturedAt,
      observed_relationship: link.relationship ?? null,
      first_seen_at: null,
      last_seen_at: capturedAt,
      observed_count: null,
      snapshot_count: null,
      lqi_latest: null,
      lqi_min: null,
      lqi_median: null,
      lqi_max: null,
      route_table_evidence: true,
      next_hop_evidence: true,
      route_observed_count: link.route_count,
      passive_corroboration: null,
      limitations: [
        LIVE_ROUTE_SAFE_COPY,
        "Zigbee routes change frequently; route-table entries describe the state at snapshot time only.",
      ],
      suggested_investigation: [],
    });
  }

  // Historical (recent missing) evidence — backend-aggregated from recent
  // previous complete snapshots; latest-snapshot relationships are already
  // excluded backend-side, so no live edge is ever duplicated as historical.
  const historicalAggregates = [
    ...(detail.historical_neighbors ?? []),
    ...(detail.historical_routes ?? []),
  ];
  const historicalEdges = historicalAggregates.map((aggregate) =>
    buildHistoricalEdge(aggregate, networkId),
  );
  const historicalEvaluated =
    detail.historical_neighbors !== undefined || detail.historical_routes !== undefined;
  const latestLayoutLimited = historicalEdges.some((edge) => edge.latest_layout_limited);
  edges.push(...historicalEdges);

  // Last known links — most recent stored evidence for devices with no links
  // in the latest snapshot, mapped one-to-one from the backend. Clearly
  // "last known", never presented as currently reported.
  edges.push(
    ...(detail.last_known_links ?? []).map((aggregate) =>
      buildLastKnownEdge(aggregate, networkId),
    ),
  );

  // Passive-derived investigation hints — mapped one-to-one from the
  // backend rule engine. Never fabricated client-side, never directional,
  // never route evidence.
  const passiveEvaluated = detail.passive_hints !== undefined;
  const passiveEdges = (detail.passive_hints ?? []).map((hint) =>
    buildPassiveHintEdge(hint, networkId),
  );
  edges.push(...passiveEdges);

  // Devices: full inventory plus any topology-only nodes, distinction kept.
  // Link endpoints are included too: a snapshot can reference an endpoint in
  // its link table that appears in neither inventory nor the node list, and
  // every edge endpoint must exist as a node or the graph layout fails
  // outright. Such endpoints become clearly labelled topology-only
  // placeholders — they are never presented as inventory devices.
  const allIeee = new Set<string>([...summaryByIeee.keys(), ...nodeByIeee.keys()]);
  for (const edge of edges) {
    allIeee.add(edge.source);
    allIeee.add(edge.target);
  }
  // Strongest recorded LQI per device across latest-snapshot neighbour edges.
  const strongestLiveLqi = new Map<string, number>();
  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_neighbor" || edge.lqi_latest == null) continue;
    for (const endpoint of [edge.source, edge.target]) {
      const current = strongestLiveLqi.get(endpoint);
      if (current == null || edge.lqi_latest > current) {
        strongestLiveLqi.set(endpoint, edge.lqi_latest);
      }
    }
  }

  const layoutAvailable = nodes.length > 0 || links.length > 0;
  const nameFor = (target: string): string => {
    const normalized = normalizeIeee(target);
    const summary = summaryByIeee.get(normalized);
    return (
      summary?.home_assistant_name?.trim() ||
      summary?.friendly_name ||
      nodeByIeee.get(normalized)?.friendly_name ||
      target
    );
  };

  const devices: MeshEvidenceDevice[] = [];
  for (const ieee of allIeee) {
    const summary = summaryByIeee.get(ieee);
    const diagnosticStats = diagnosticStatsFor({
      summary,
      neighborCount: neighborCounts.get(ieee) ?? 0,
      layoutAvailable,
      strongestLiveLqi: strongestLiveLqi.get(ieee) ?? null,
      recentMissingCount: historicalEvaluated
        ? historicalEdges.filter((edge) => edge.source === ieee || edge.target === ieee).length
        : null,
      backendStats: detail.device_stats?.[ieee],
      backendWindow: detail.device_stats_window,
      nameFor,
    });
    const device = buildDevice(
      ieee,
      networkId,
      summary,
      inventoryAccepted,
      nodeByIeee.get(ieee),
      neighborCounts.get(ieee) ?? 0,
      diagnosticStats,
    );
    if (historicalEvaluated) {
      const summary = historicalSummaryFor(historicalEdges, ieee, latestLayoutLimited);
      if (summary) device.historical_topology_summary = summary;
    }
    if (passiveEvaluated) {
      const summary = passiveHintSummaryFor(passiveEdges, ieee);
      if (summary) device.passive_hint_summary = summary;
    }
    devices.push(device);
  }
  devices.sort((a, b) => a.friendly_name.localeCompare(b.friendly_name));

  return { devices, edges };
}
