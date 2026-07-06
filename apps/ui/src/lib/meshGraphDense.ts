import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshNodeFlag } from "@/lib/meshEvidence";

/**
 * Dense graph mode: readability policy for large meshes.
 *
 * On a real dense network (the reference `home` network has ~106 devices and
 * ~843 undirected neighbour pairs) drawing every evidence edge produces an
 * unreadable hairball. Dense mode reduces what is *rendered* by default via
 * user-facing connection-type controls — it never removes evidence from the
 * model, never changes edge semantics, and the UI must always state how many
 * links are available vs shown vs hidden for readability.
 */

/** Dense mode triggers when total evidence edges exceed this. */
export const DENSE_EVIDENCE_EDGE_THRESHOLD = 250;
/** ...or when deduplicated structural layout edges exceed this. */
export const DENSE_STRUCTURAL_EDGE_THRESHOLD = 400;
/** ...or when both node and edge counts are high. */
export const DENSE_NODE_THRESHOLD = 80;
export const DENSE_NODE_EDGE_THRESHOLD = 300;

/**
 * "Best neighbour links": up to this many strongest observed neighbour links
 * are kept per device in the readable default subset. Tune here if dev
 * screenshots show the default is still too dense (1) or too sparse (3).
 */
export const BEST_NEIGHBOUR_LINKS_PER_DEVICE = 2;

export interface DenseGraphInput {
  nodeCount: number;
  evidenceEdgeCount: number;
  structuralEdgeCount: number;
}

export function isDenseGraph({
  nodeCount,
  evidenceEdgeCount,
  structuralEdgeCount,
}: DenseGraphInput): boolean {
  if (evidenceEdgeCount > DENSE_EVIDENCE_EDGE_THRESHOLD) return true;
  if (structuralEdgeCount > DENSE_STRUCTURAL_EDGE_THRESHOLD) return true;
  return nodeCount > DENSE_NODE_THRESHOLD && evidenceEdgeCount > DENSE_NODE_EDGE_THRESHOLD;
}

/**
 * User-facing connection-type controls for dense mode.
 * "Selected device links" is always on and therefore not represented here:
 * selecting a device always reveals its full evidence neighbourhood.
 */
export interface ConnectionControls {
  /** Route-table / next-hop evidence from the latest snapshot. */
  routeHints: boolean;
  /** Readable subset of strongest observed neighbour links. */
  bestNeighbourLinks: boolean;
  /** Evidence links touching devices ZigbeeLens has already flagged. */
  issueDeviceLinks: boolean;
  /** Every observed neighbour link from the latest snapshot. */
  allNeighbourLinks: boolean;
  /** Stale / low-confidence evidence already present in the model. */
  oldUncertainLinks: boolean;
}

export const DENSE_DEFAULT_CONNECTION_CONTROLS: ConnectionControls = {
  routeHints: true,
  bestNeighbourLinks: true,
  issueDeviceLinks: true,
  allNeighbourLinks: false,
  oldUncertainLinks: false,
};

/**
 * Existing issue/health signals that mark a device as "with issues" for the
 * "Links for devices with issues" control. This only reads fields ZigbeeLens
 * already computed — it never derives new issue inference. Deliberately
 * excluded: `battery_sleepy` (normal behaviour) and `diagnostics_limited`
 * (a data limitation, not an issue — and so common on real networks that
 * including it would defeat dense-mode readability).
 */
const ISSUE_FLAGS: readonly MeshNodeFlag[] = [
  "unavailable",
  "needs_attention",
  "interview_failure",
  "weak_link_candidate",
  "router_risk_candidate",
];

export function deviceHasIssue(device: MeshEvidenceDevice): boolean {
  if (device.open_issue) return true;
  if (device.health_bucket === "needs_attention" || device.health_bucket === "unavailable") {
    return true;
  }
  return device.flags.some((flag) => ISSUE_FLAGS.includes(flag));
}

export function collectIssueDeviceIds(devices: MeshEvidenceDevice[]): Set<string> {
  const ids = new Set<string>();
  for (const device of devices) {
    if (deviceHasIssue(device)) ids.add(device.ieee_address);
  }
  return ids;
}

/**
 * Pick the "best neighbour links" subset: for each device, up to N strongest
 * observed `latest_snapshot_neighbor` links.
 *
 * Ordering per device: links with a recorded LQI first (highest LQI first),
 * then links without a recorded LQI (missing LQI is unknown, never zero — a
 * device whose links all lack LQI still keeps up to N links rather than
 * being stranded). Ties break on edge id for determinism. An edge is kept if
 * it is in the top N of *either* endpoint.
 */
export function selectBestNeighbourLinks(
  edges: MeshEvidenceEdge[],
  linksPerDevice: number = BEST_NEIGHBOUR_LINKS_PER_DEVICE,
): Set<string> {
  const byDevice = new Map<string, MeshEvidenceEdge[]>();
  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
    for (const endpoint of [edge.source, edge.target]) {
      const list = byDevice.get(endpoint);
      if (list) list.push(edge);
      else byDevice.set(endpoint, [edge]);
    }
  }

  const chosen = new Set<string>();
  for (const list of byDevice.values()) {
    const sorted = [...list].sort((a, b) => {
      const aLqi = a.lqi_latest;
      const bLqi = b.lqi_latest;
      if (aLqi != null && bLqi != null) return bLqi - aLqi || a.id.localeCompare(b.id);
      if (aLqi != null) return -1;
      if (bLqi != null) return 1;
      return a.id.localeCompare(b.id);
    });
    for (const edge of sorted.slice(0, linksPerDevice)) chosen.add(edge.id);
  }
  return chosen;
}

export interface ConnectionEdgeContext {
  /** Edge ids picked by {@link selectBestNeighbourLinks}. */
  bestNeighbourEdgeIds: Set<string>;
  /** Devices flagged by existing issue/health fields. */
  issueDeviceIds: Set<string>;
  selectedNodeId: string | null;
  selectedEdge?: MeshEvidenceEdge | null;
}

/**
 * The evidence edges rendered in dense mode for a given set of connection
 * controls. Purely a *render* subset: hidden edges stay in the model and
 * drawers, and every hidden edge remains reachable by selecting one of its
 * endpoint devices or enabling "All neighbour links".
 */
export function selectVisibleConnectionEdges(
  edges: MeshEvidenceEdge[],
  controls: ConnectionControls,
  context: ConnectionEdgeContext,
): MeshEvidenceEdge[] {
  const focusNodes = new Set<string>();
  if (context.selectedNodeId) focusNodes.add(context.selectedNodeId);
  if (context.selectedEdge) {
    focusNodes.add(context.selectedEdge.source);
    focusNodes.add(context.selectedEdge.target);
  }

  return edges.filter((edge) => {
    // Selected device links — always on: selection reveals the full
    // evidence neighbourhood regardless of class.
    if (focusNodes.has(edge.source) || focusNodes.has(edge.target)) return true;

    if (
      controls.issueDeviceLinks &&
      (edge.issue_related ||
        context.issueDeviceIds.has(edge.source) ||
        context.issueDeviceIds.has(edge.target))
    ) {
      return true;
    }

    switch (edge.evidence_class) {
      case "latest_snapshot_route":
        return controls.routeHints;
      case "latest_snapshot_neighbor":
        return (
          controls.allNeighbourLinks ||
          (controls.bestNeighbourLinks && context.bestNeighbourEdgeIds.has(edge.id))
        );
      case "stale_low_confidence":
        return controls.oldUncertainLinks;
      // Historical and passive-derived classes have no dense-mode control
      // yet ("Previously seen links" / "Suggested investigation links" are
      // future work) and never occur in live data; they stay reachable via
      // selection or issue links above.
      case "historical_neighbor":
      case "historical_route":
      case "passive_derived_association":
        return false;
    }
  });
}

/** Evidence edges hidden from the canvas for readability (never removed). */
export function countHiddenConnectionEdges(
  availableEdges: MeshEvidenceEdge[],
  renderedEdges: MeshEvidenceEdge[],
): number {
  return Math.max(0, availableEdges.length - renderedEdges.length);
}
