import type { MeshEvidenceEdge } from "@/lib/meshEvidence";

/**
 * Dense graph mode: readability policy for large meshes.
 *
 * On a real dense network (the reference `home` network has ~106 devices and
 * ~843 undirected neighbour pairs) drawing every evidence edge produces an
 * unreadable hairball. Dense mode reduces what is *rendered* by default —
 * it never removes evidence from the model, never changes edge semantics,
 * and the UI must always state how many links are available vs shown vs
 * hidden for readability.
 */

/** Dense mode triggers when total evidence edges exceed this. */
export const DENSE_EVIDENCE_EDGE_THRESHOLD = 250;
/** ...or when deduplicated structural layout edges exceed this. */
export const DENSE_STRUCTURAL_EDGE_THRESHOLD = 400;
/** ...or when both node and edge counts are high. */
export const DENSE_NODE_THRESHOLD = 80;
export const DENSE_NODE_EDGE_THRESHOLD = 300;

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
 * The focused evidence subset rendered by default in dense mode:
 *
 * - route evidence (always prioritised — it is rarer and higher-value);
 * - issue-related edges (only where issue relevance already exists on the
 *   edge; never derived here);
 * - the full evidence neighbourhood of the selected node;
 * - the neighbourhoods of a selected edge's endpoints.
 *
 * Everything else stays in the model and drawers; it is hidden from the
 * canvas for readability only, and remains reachable by selecting an
 * endpoint node or enabling "Show all evidence".
 */
export function selectVisibleEdgesForDenseMode(
  edges: MeshEvidenceEdge[],
  selectedNodeId: string | null,
  selectedEdge: MeshEvidenceEdge | null = null,
): MeshEvidenceEdge[] {
  const focusNodes = new Set<string>();
  if (selectedNodeId) focusNodes.add(selectedNodeId);
  if (selectedEdge) {
    focusNodes.add(selectedEdge.source);
    focusNodes.add(selectedEdge.target);
  }

  return edges.filter((edge) => {
    if (
      edge.evidence_class === "latest_snapshot_route" ||
      edge.evidence_class === "historical_route"
    ) {
      return true;
    }
    if (edge.issue_related) return true;
    return focusNodes.has(edge.source) || focusNodes.has(edge.target);
  });
}

/** Evidence edges hidden from the canvas for readability (never removed). */
export function countHiddenEvidenceEdges(
  filterVisible: MeshEvidenceEdge[],
  renderVisible: MeshEvidenceEdge[],
): number {
  return Math.max(0, filterVisible.length - renderVisible.length);
}
