import type { DeviceSummary, LensBucket } from "@zigbeelens/shared";
import type { TopologyNetworkDetail, TopologyLinkRow, TopologyNodeRow } from "@/lib/api";
import type {
  MeshEvidenceDevice,
  MeshEvidenceEdge,
  MeshHealthBucket,
  MeshNodeFlag,
  MeshRole,
} from "@/lib/meshEvidence";

/**
 * Map real latest-snapshot topology data + device inventory into the mesh
 * evidence model.
 *
 * This mapper only ever produces `latest_snapshot_neighbor` and
 * `latest_snapshot_route` evidence. Historical, passive-derived and
 * stale/low-confidence classes require inference that does not exist yet and
 * must never be fabricated from a single snapshot or from inventory data.
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
  const parts = ["Observed in the latest topology snapshot"];
  if (neighborCount > 0) {
    parts.push(`with ${neighborCount} neighbour ${neighborCount === 1 ? "entry" : "entries"}`);
  }
  if (node?.lqi != null) parts.push(`(LQI ${node.lqi})`);
  return `${parts.join(" ")}.`;
}

function interpretationFor(
  summary: DeviceSummary | undefined,
  inTopology: boolean,
  role: MeshRole,
): string {
  if (!summary) {
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
      : "Observed in topology snapshot only — not in the current device inventory",
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
    interpretation: interpretationFor(summary, inTopology, role),
  };
}

interface NeighborAccumulator {
  link: TopologyLinkRow;
  bothDirections: boolean;
}

/**
 * Build the live evidence set from the latest snapshot plus inventory.
 * Neighbour entries reported in both directions collapse into one
 * non-directional edge; route-table entries produce directional route edges.
 */
export function buildLiveMeshEvidence(
  detail: TopologyNetworkDetail,
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
      "Only the latest snapshot is considered in this view; historical link tracking is a future feature.",
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

  // Devices: full inventory plus any topology-only nodes, distinction kept.
  const allIeee = new Set<string>([...summaryByIeee.keys(), ...nodeByIeee.keys()]);
  const devices: MeshEvidenceDevice[] = [];
  for (const ieee of allIeee) {
    devices.push(
      buildDevice(
        ieee,
        networkId,
        summaryByIeee.get(ieee),
        nodeByIeee.get(ieee),
        neighborCounts.get(ieee) ?? 0,
      ),
    );
  }
  devices.sort((a, b) => a.friendly_name.localeCompare(b.friendly_name));

  return { devices, edges };
}
