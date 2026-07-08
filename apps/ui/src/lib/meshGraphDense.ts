import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshNodeFlag } from "@/lib/meshEvidence";

/**
 * Progressive focused view: readability policy for the mesh graph.
 *
 * There is no hard dense/non-dense split. One connection-control model works
 * for every graph size; the "Best neighbour links" subset adapts to the
 * graph via a per-node link budget, so small graphs naturally draw all of
 * their enabled evidence and large graphs (the reference `home` network has
 * ~106 devices and ~843 undirected neighbour pairs) naturally start focused.
 * Focusing only reduces what is *rendered* — it never removes evidence from
 * the model, never changes edge semantics, and the UI must always state how
 * many links are available vs drawn in the current view.
 */

/**
 * The adaptive link budget targets roughly this many drawn neighbour links
 * per observed node. Tune here if real networks look too dense or too sparse.
 */
export const TARGET_VISIBLE_LINKS_PER_NODE = 1.5;
/** Per-device neighbour-link bounds for the adaptive budget. */
export const MIN_NEIGHBOUR_LINKS_PER_DEVICE = 1;
export const MAX_NEIGHBOUR_LINKS_PER_DEVICE = 4;

/**
 * User-facing connection-type controls.
 * "Selected device links" is always on and therefore not represented here:
 * selecting a device always reveals its full evidence neighbourhood.
 */
export interface ConnectionControls {
  /** Route-table / next-hop evidence from the latest snapshot. */
  routeHints: boolean;
  /** Readable subset of strongest observed neighbour links. */
  bestNeighbourLinks: boolean;
  /** Every observed neighbour link from the latest snapshot. */
  allNeighbourLinks: boolean;
  /** Stale / low-confidence evidence already present in the model. */
  oldUncertainLinks: boolean;
  /**
   * "Recent missing links": historical neighbour/route evidence observed in
   * recent previous topology snapshots but missing from the latest snapshot.
   * Off by default, and even when on only a focused, capped subset renders
   * — never a forever-history dump.
   */
  recentMissingLinks: boolean;
  /**
   * "Last known links": the most recent stored link evidence for devices
   * with no links at all in the latest snapshot (typically sleepy battery
   * devices aged out of router neighbour tables). On by default — these
   * exist only for otherwise-linkless devices and are capped backend-side,
   * so they can never hairball. Clearly styled as not currently reported.
   */
  lastKnownLinks: boolean;
  /**
   * "Suggested investigation links": passive-derived hints from the backend
   * rule engine. Not topology evidence and never proof of live routing.
   * Off by default, and even when on only a focused, capped subset renders.
   */
  suggestedInvestigationLinks: boolean;
}

export const DEFAULT_CONNECTION_CONTROLS: ConnectionControls = {
  routeHints: true,
  bestNeighbourLinks: true,
  allNeighbourLinks: false,
  oldUncertainLinks: false,
  recentMissingLinks: false,
  lastKnownLinks: true,
  suggestedInvestigationLinks: false,
};

/* ------------------------------------------------------------------------ */
/* Per-network persistence of connection-control choices                     */
/* ------------------------------------------------------------------------ */

export function connectionControlsStorageKey(networkId: string): string {
  return `zigbeelens.meshGraph.connectionControls.v1.${networkId}`;
}

/**
 * Restore the user's saved connection choices for a network. Only known
 * boolean keys are read; unknown future keys are ignored and corrupt or
 * missing storage falls back to the defaults.
 */
export function loadConnectionControls(networkId: string): ConnectionControls {
  try {
    const raw = localStorage.getItem(connectionControlsStorageKey(networkId));
    if (!raw) return { ...DEFAULT_CONNECTION_CONTROLS };
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { ...DEFAULT_CONNECTION_CONTROLS };
    }
    const stored = parsed as Record<string, unknown>;
    const controls = { ...DEFAULT_CONNECTION_CONTROLS };
    for (const key of Object.keys(DEFAULT_CONNECTION_CONTROLS) as (keyof ConnectionControls)[]) {
      if (typeof stored[key] === "boolean") controls[key] = stored[key];
    }
    return controls;
  } catch {
    return { ...DEFAULT_CONNECTION_CONTROLS };
  }
}

export function saveConnectionControls(networkId: string, controls: ConnectionControls): void {
  try {
    localStorage.setItem(connectionControlsStorageKey(networkId), JSON.stringify(controls));
  } catch {
    // Storage full/unavailable: choices simply don't persist.
  }
}

export function clearConnectionControls(networkId: string): void {
  try {
    localStorage.removeItem(connectionControlsStorageKey(networkId));
  } catch {
    // Nothing to clear.
  }
}

/**
 * Caps for recent missing links. Historical evidence is gap-filling
 * context; these caps keep it from becoming a hairball even when the
 * control is on. Edges over the cap stay in the model and remain reachable
 * by selecting an endpoint device.
 */
export const MAX_RECENT_MISSING_LINKS_TOTAL = 100;
export const MAX_RECENT_MISSING_LINKS_PER_NODE = 3;

/**
 * Caps for passive-derived investigation hints. Hints are already capped
 * backend-side; these rendering caps additionally keep the drawn subset
 * focused so enabling the control never creates a new hairball. Hints over
 * the cap stay in the model and remain reachable by selecting an endpoint.
 */
export const MAX_PASSIVE_HINTS_TOTAL = 100;
export const MAX_PASSIVE_HINTS_PER_NODE = 3;

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

/** Direction-independent key for a device pair. */
function pairKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

/**
 * Device pairs covered by a latest-snapshot route edge. Used to avoid
 * drawing a neighbour line in parallel with a route hint for the same pair:
 * the route edge is the stronger evidence, and the neighbour evidence stays
 * in the model and remains reachable by selecting an endpoint device.
 */
export function collectRouteCoveredPairs(edges: MeshEvidenceEdge[]): Set<string> {
  const pairs = new Set<string>();
  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_route") continue;
    pairs.add(pairKey(edge.source, edge.target));
  }
  return pairs;
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
 *
 * Pairs in `excludePairKeys` (typically pairs already drawn as route hints)
 * are skipped so the per-device allowance is spent on pairs that would
 * otherwise show no connection.
 */
export function selectBestNeighbourLinks(
  edges: MeshEvidenceEdge[],
  linksPerDevice: number,
  excludePairKeys?: Set<string>,
): Set<string> {
  const byDevice = new Map<string, MeshEvidenceEdge[]>();
  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
    if (excludePairKeys?.has(pairKey(edge.source, edge.target))) continue;
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

export interface AdaptiveBestNeighbourSelection {
  edgeIds: Set<string>;
  /** The per-device neighbour count the budget settled on. */
  linksPerDevice: number;
}

/**
 * Adaptive "best neighbour links" subset: instead of a fixed per-device
 * count, choose the largest per-device N (between
 * {@link MIN_NEIGHBOUR_LINKS_PER_DEVICE} and
 * {@link MAX_NEIGHBOUR_LINKS_PER_DEVICE}) whose selection stays within a
 * budget of {@link TARGET_VISIBLE_LINKS_PER_NODE} drawn links per node.
 *
 * Small graphs therefore keep all (or nearly all) of their neighbour
 * evidence naturally, while large graphs settle on a focused subset. If even
 * N = 1 exceeds the budget, N = 1 is still used — every device keeps its
 * strongest link. Selection stays deterministic: it reuses
 * {@link selectBestNeighbourLinks} ordering (recorded LQI first — missing
 * LQI is unknown, never zero — then edge id).
 */
export function selectAdaptiveBestNeighbourLinks(
  edges: MeshEvidenceEdge[],
  nodeCount: number,
  excludePairKeys?: Set<string>,
): AdaptiveBestNeighbourSelection {
  const budget = Math.ceil(Math.max(nodeCount, 1) * TARGET_VISIBLE_LINKS_PER_NODE);
  let fallback: AdaptiveBestNeighbourSelection | null = null;
  for (let n = MAX_NEIGHBOUR_LINKS_PER_DEVICE; n >= MIN_NEIGHBOUR_LINKS_PER_DEVICE; n -= 1) {
    const edgeIds = selectBestNeighbourLinks(edges, n, excludePairKeys);
    if (edgeIds.size <= budget) return { edgeIds, linksPerDevice: n };
    fallback = { edgeIds, linksPerDevice: n };
  }
  // Even one link per device exceeds the budget: keep N = 1 anyway so no
  // device is stranded without its strongest observed link.
  return fallback ?? { edgeIds: new Set(), linksPerDevice: MIN_NEIGHBOUR_LINKS_PER_DEVICE };
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
 * The focused subset of recent missing (historical) edges rendered when
 * "Recent missing links" is on.
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

const CONFIDENCE_RANK = { high: 2, medium: 1, low: 0 } as const;

export interface PassiveHintSelectionInput {
  /** Devices already flagged by ZigbeeLens (existing fields, no new inference). */
  issueDeviceIds: Set<string>;
  /** The currently selected device, whose hints are prioritised. */
  selectedNodeId: string | null;
}

/**
 * The focused subset of passive-derived hints rendered when "Suggested
 * investigation links" is on.
 *
 * Deterministic priority: selected-device hints first, then hints involving
 * devices with existing issue signals, then higher confidence, then more
 * recent, then edge id. Capped per node and in total; hints over the cap
 * stay in the model and remain reachable by selecting an endpoint device
 * (selection always reveals the full neighbourhood via
 * {@link selectVisibleConnectionEdges}).
 */
export function selectPassiveHintEdges(
  edges: MeshEvidenceEdge[],
  input: PassiveHintSelectionInput,
  totalCap: number = MAX_PASSIVE_HINTS_TOTAL,
  perNodeCap: number = MAX_PASSIVE_HINTS_PER_NODE,
): Set<string> {
  const candidates = edges.filter(
    (edge) => edge.evidence_class === "passive_derived_association",
  );

  const touchesSelected = (edge: MeshEvidenceEdge): boolean =>
    input.selectedNodeId !== null &&
    (edge.source === input.selectedNodeId || edge.target === input.selectedNodeId);
  const touchesIssue = (edge: MeshEvidenceEdge): boolean =>
    edge.issue_related === true ||
    input.issueDeviceIds.has(edge.source) ||
    input.issueDeviceIds.has(edge.target);

  const ordered = [...candidates].sort((a, b) => {
    const selected = Number(touchesSelected(b)) - Number(touchesSelected(a));
    if (selected !== 0) return selected;
    const issue = Number(touchesIssue(b)) - Number(touchesIssue(a));
    if (issue !== 0) return issue;
    const confidence = CONFIDENCE_RANK[b.confidence] - CONFIDENCE_RANK[a.confidence];
    if (confidence !== 0) return confidence;
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
  /** Edge ids picked by {@link selectPassiveHintEdges}. */
  passiveHintEdgeIds?: Set<string>;
  selectedNodeId: string | null;
  selectedEdge?: MeshEvidenceEdge | null;
}

/**
 * The evidence edges rendered for a given set of connection controls.
 * Purely a *render* subset: undrawn edges stay in the model and drawers,
 * and every undrawn edge remains reachable by selecting one of its endpoint
 * devices or enabling "All neighbour links".
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

  // When route hints are drawn, a pair covered by a route edge does not also
  // draw its neighbour line — one line per pair, route evidence first.
  // "All neighbour links" deliberately draws everything, and selection still
  // reveals the full neighbourhood, so the neighbour evidence stays reachable.
  const routeCoveredPairs =
    controls.routeHints && !controls.allNeighbourLinks
      ? collectRouteCoveredPairs(edges)
      : new Set<string>();

  return edges.filter((edge) => {
    // Selected device links — always on: selection reveals the full
    // evidence neighbourhood regardless of class.
    if (focusNodes.has(edge.source) || focusNodes.has(edge.target)) return true;

    // Devices with issues are always evident (highlighted nodes), and edges
    // already explicitly marked issue-related are always drawn — but never
    // every evidence edge touching an issue device, which flooded dense
    // graphs with lines.
    if (edge.issue_related) return true;

    switch (edge.evidence_class) {
      case "latest_snapshot_route":
        return controls.routeHints;
      case "latest_snapshot_neighbor":
        if (controls.allNeighbourLinks) return true;
        if (routeCoveredPairs.has(pairKey(edge.source, edge.target))) return false;
        return controls.bestNeighbourLinks && context.bestNeighbourEdgeIds.has(edge.id);
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
      // Last known links only exist for devices with no links in the latest
      // snapshot and are capped backend-side, so drawing them all when the
      // control is on cannot hairball.
      case "last_known_link":
        return controls.lastKnownLinks;
      // Passive-derived hints render only the focused/capped subset chosen
      // by selectPassiveHintEdges — never every hint at once. Hints over
      // the cap stay reachable via device selection above.
      case "passive_derived_association":
        return (
          controls.suggestedInvestigationLinks &&
          (context.passiveHintEdgeIds?.has(edge.id) ?? false)
        );
    }
  });
}
