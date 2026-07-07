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
  /**
   * "Devices with issues": highlights devices ZigbeeLens has already
   * flagged. Primarily node highlighting — it must never expand to every
   * evidence edge touching issue devices (that flooded dense graphs);
   * only edges already marked issue-related become visible.
   */
  devicesWithIssues: boolean;
  /** Every observed neighbour link from the latest snapshot. */
  allNeighbourLinks: boolean;
  /** Stale / low-confidence evidence already present in the model. */
  oldUncertainLinks: boolean;
  /**
   * "Recent missing links": historical neighbour/route evidence observed in
   * recent previous topology snapshots but missing from the latest snapshot.
   * Off by default, and even when on only a focused, capped subset renders
   * in dense graphs — never a forever-history dump.
   */
  recentMissingLinks: boolean;
}

export const DENSE_DEFAULT_CONNECTION_CONTROLS: ConnectionControls = {
  routeHints: true,
  bestNeighbourLinks: true,
  devicesWithIssues: false,
  allNeighbourLinks: false,
  oldUncertainLinks: false,
  recentMissingLinks: false,
};

/**
 * Caps for recent missing links in dense graphs. Historical evidence is
 * gap-filling context; these caps keep it from becoming a hairball even
 * when the control is on. Edges over the cap stay in the model and remain
 * reachable by selecting an endpoint device.
 */
export const MAX_RECENT_MISSING_LINKS_TOTAL = 100;
export const MAX_RECENT_MISSING_LINKS_PER_NODE = 3;

/**
 * Existing issue/health signals that mark a device as "with issues" for the
 * "Devices with issues" control. This only reads fields ZigbeeLens already
 * computed — it never derives new issue inference. Deliberately excluded:
 * `battery_sleepy` (normal behaviour) and `diagnostics_limited` (a data
 * limitation, not an issue — and so common on real networks that including
 * it would defeat dense-mode readability).
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

function isRecentMissingEdge(edge: MeshEvidenceEdge): boolean {
  return (
    edge.evidence_class === "historical_neighbor" || edge.evidence_class === "historical_route"
  );
}

export interface RecentMissingSelectionInput {
  /** Devices already flagged by ZigbeeLens (existing fields, no new inference). */
  issueDeviceIds: Set<string>;
  /** Devices with at least one latest-snapshot neighbour edge. */
  devicesWithLatestNeighbourEvidence: Set<string>;
  /** Whether the latest snapshot layout is limited/unavailable. */
  latestLayoutLimited: boolean;
}

/**
 * The focused subset of recent missing (historical) edges rendered in dense
 * graphs when "Recent missing links" is on.
 *
 * Relevance rules — an edge qualifies for priority when at least one holds:
 * - an endpoint has a current real issue flag ZigbeeLens already computed;
 * - an endpoint has no latest-snapshot neighbour evidence (the edge fills a
 *   gap the latest snapshot cannot explain);
 * - the latest layout is limited, so historical context is all there is.
 *
 * Remaining capacity is filled with a deterministic representative subset
 * (most recently observed first). Everything is capped per node and in
 * total; edges over the cap stay in the model and remain reachable by
 * selecting an endpoint. Selected-device edges are always revealed by
 * {@link selectVisibleConnectionEdges} regardless of these caps.
 */
export function selectRecentMissingEdges(
  edges: MeshEvidenceEdge[],
  input: RecentMissingSelectionInput,
  totalCap: number = MAX_RECENT_MISSING_LINKS_TOTAL,
  perNodeCap: number = MAX_RECENT_MISSING_LINKS_PER_NODE,
): Set<string> {
  const candidates = edges.filter(isRecentMissingEdge);

  const isRelevant = (edge: MeshEvidenceEdge): boolean => {
    if (input.latestLayoutLimited) return true;
    if (input.issueDeviceIds.has(edge.source) || input.issueDeviceIds.has(edge.target)) {
      return true;
    }
    return (
      !input.devicesWithLatestNeighbourEvidence.has(edge.source) ||
      !input.devicesWithLatestNeighbourEvidence.has(edge.target)
    );
  };

  // Deterministic order: relevant edges first, then most recently observed,
  // then id as the tiebreaker.
  const ordered = [...candidates].sort((a, b) => {
    const relevance = Number(isRelevant(b)) - Number(isRelevant(a));
    if (relevance !== 0) return relevance;
    const aSeen = a.last_seen_at ?? "";
    const bSeen = b.last_seen_at ?? "";
    if (aSeen !== bSeen) return bSeen.localeCompare(aSeen);
    return a.id.localeCompare(b.id);
  });

  const chosen = new Set<string>();
  const perNode = new Map<string, number>();
  for (const edge of ordered) {
    if (chosen.size >= totalCap) break;
    const sourceCount = perNode.get(edge.source) ?? 0;
    const targetCount = perNode.get(edge.target) ?? 0;
    if (sourceCount >= perNodeCap || targetCount >= perNodeCap) continue;
    chosen.add(edge.id);
    perNode.set(edge.source, sourceCount + 1);
    perNode.set(edge.target, targetCount + 1);
  }
  return chosen;
}

export interface ConnectionEdgeContext {
  /** Edge ids picked by {@link selectBestNeighbourLinks}. */
  bestNeighbourEdgeIds: Set<string>;
  /** Edge ids picked by {@link selectRecentMissingEdges}. */
  recentMissingEdgeIds?: Set<string>;
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

    // "Devices with issues" highlights nodes. The only edges it reveals are
    // ones already explicitly marked issue-related — never every evidence
    // edge touching an issue device, which flooded dense graphs with lines.
    if (controls.devicesWithIssues && edge.issue_related) return true;

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
      // Recent missing links render only the focused/capped subset chosen
      // by selectRecentMissingEdges — never every historical edge. Edges
      // over the cap stay reachable via device selection above.
      case "historical_neighbor":
      case "historical_route":
        return (
          controls.recentMissingLinks &&
          (context.recentMissingEdgeIds?.has(edge.id) ?? false)
        );
      // Passive-derived associations have no dense-mode control yet
      // ("Suggested investigation links" is future work); they stay
      // reachable via selection or issue links above.
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
