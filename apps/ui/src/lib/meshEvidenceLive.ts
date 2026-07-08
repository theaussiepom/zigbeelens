import type { DeviceSummary, LensBucket } from "@zigbeelens/shared";
import type {
  HistoricalEdgeAggregate,
  PassiveHintAggregate,
  TopologyEvidenceGraphDetail,
  TopologyLinkRow,
  TopologyNetworkDetail,
  TopologyNodeRow,
} from "@/lib/api";
import type {
  MeshEvidenceDevice,
  MeshEvidenceEdge,
  MeshHealthBucket,
  MeshNodeFlag,
  MeshRole,
} from "@/lib/meshEvidence";
import { relativeTime } from "@/lib/format";

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

function bucketFromLens(bucket: LensBucket | undefined): MeshHealthBucket {
  switch (bucket) {
    case "healthy":
    case "needs_attention":
    case "unavailable":
    case "diagnostics_limited":
    case "recently_unstable":
    case "informational":
      return bucket;
    default:
      return "unknown";
  }
}

function flagsForDevice(summary: DeviceSummary, role: MeshRole): MeshNodeFlag[] {
  const flags: MeshNodeFlag[] = [];
  if (summary.lens_bucket === "unavailable" || summary.availability === "offline") {
    flags.push("unavailable");
  }
  if (summary.lens_bucket === "needs_attention") flags.push("needs_attention");
  if (summary.lens_bucket === "diagnostics_limited") flags.push("diagnostics_limited");
  if (summary.interview_state === "failed") flags.push("interview_failure");
  if (summary.health.primary === "weak_link") flags.push("weak_link_candidate");
  if (summary.health.primary === "router_risk") flags.push("router_risk_candidate");
  if (summary.power_source === "Battery" && role === "end_device") flags.push("battery_sleepy");
  return flags;
}

function topologySummary(node: TopologyNodeRow | undefined, neighborCount: number): string {
  if (!node && neighborCount === 0) {
    return "Not observed in the latest topology snapshot.";
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

function interpretationFor(
  summary: DeviceSummary | undefined,
  node: TopologyNodeRow | undefined,
  inTopology: boolean,
  role: MeshRole,
): string {
  if (!summary) {
    if (!node) {
      return "The latest topology snapshot referenced this endpoint in a link, but ZigbeeLens does not currently have matching inventory or device details. Snapshot data can briefly include renamed or removed devices; this is context, not an incident.";
    }
    return "This node appeared in the topology snapshot but is not in the current device inventory. Snapshot data can briefly include renamed or removed devices; this is context, not an incident.";
  }
  if (!inTopology) {
    const sleepy = summary.power_source === "Battery" && role === "end_device";
    return sleepy ? SLEEPY_NO_LINK_COPY : NO_LINK_COPY;
  }
  if (summary.lens_bucket && summary.lens_bucket !== "healthy") {
    return `${summary.lens_bucket_reason || "ZigbeeLens has flagged this device for attention based on passive observations."} Topology evidence is point-in-time context and does not change this assessment on its own.`;
  }
  return "This device appears in the latest topology snapshot and its passive health signals look normal.";
}

/**
 * Node-drawer summary of recent missing links touching one device.
 * Only produced when historical data was actually evaluated.
 */
function historicalSummaryFor(
  historicalEdges: MeshEvidenceEdge[],
  ieee: string,
  latestLayoutLimited: boolean,
): string {
  const touching = historicalEdges.filter(
    (edge) => edge.source === ieee || edge.target === ieee,
  );
  if (touching.length === 0) {
    return "No recent missing topology links in the selected history window.";
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
      "Historical evidence is available, but the latest snapshot layout is limited, so absence from the latest graph is not meaningful by itself.",
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
  node: TopologyNodeRow | undefined,
  neighborCount: number,
): MeshEvidenceDevice {
  const role = summary ? roleFromType(summary.device_type) : roleFromType(node?.node_type);
  const inTopology = node !== undefined || neighborCount > 0;
  return {
    ieee_address: ieee,
    network_id: networkId,
    friendly_name: summary?.friendly_name || node?.friendly_name || ieee,
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
    last_seen_at: summary?.last_seen ?? null,
    health_bucket: summary ? bucketFromLens(summary.lens_bucket) : "unknown",
    flags: summary ? flagsForDevice(summary, role) : [],
    inventory_status: summary
      ? "In Zigbee2MQTT device inventory"
      : node
        ? "Observed in topology snapshot only — not in the current device inventory"
        : "Referenced by topology links only — unknown to inventory and node list",
    topology_evidence_summary: topologySummary(node, neighborCount),
    passive_observation_summary: summary
      ? summary.lens_bucket_reason || "No passive observation summary is available for this device."
      : "No passive observations — this node is not in the device inventory.",
    open_issue: summary?.incident_affected
      ? {
          title: "Linked to an active incident",
          summary: "This device is referenced by an open incident. See the Incidents page for the evidence trail.",
        }
      : null,
    interpretation: interpretationFor(summary, node, inTopology, role),
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
 * Live detail for the evidence graph: the latest-snapshot payload, plus the
 * backend-aggregated historical evidence when the evidence-graph endpoint
 * supplied it.
 */
export type LiveTopologyDetail = TopologyNetworkDetail &
  Partial<
    Pick<
      TopologyEvidenceGraphDetail,
      | "historical_neighbors"
      | "historical_routes"
      | "history_window"
      | "limitations"
      | "passive_hints"
      | "passive_hint_window"
    >
  >;

/**
 * Build the live evidence set from the latest snapshot plus inventory.
 * Neighbour entries reported in both directions collapse into one
 * non-directional edge; route-table entries produce directional route edges.
 * Backend-aggregated historical (recent missing) evidence maps to
 * historical_neighbor / historical_route edges.
 */
export function buildLiveMeshEvidence(
  detail: LiveTopologyDetail,
  inventoryDevices: DeviceSummary[],
): LiveMeshEvidence {
  const networkId = detail.network_id;
  const capturedAt = detail.latest_snapshot?.captured_at ?? null;
  const nodes = detail.nodes ?? [];
  const links = detail.links ?? [];

  const nodeByIeee = new Map<string, TopologyNodeRow>();
  for (const node of nodes) nodeByIeee.set(normalizeIeee(node.ieee_address), node);

  const summaryByIeee = new Map<string, DeviceSummary>();
  for (const device of inventoryDevices) {
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
  const devices: MeshEvidenceDevice[] = [];
  for (const ieee of allIeee) {
    const device = buildDevice(
      ieee,
      networkId,
      summaryByIeee.get(ieee),
      nodeByIeee.get(ieee),
      neighborCounts.get(ieee) ?? 0,
    );
    if (historicalEvaluated) {
      device.historical_topology_summary = historicalSummaryFor(
        historicalEdges,
        ieee,
        latestLayoutLimited,
      );
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
