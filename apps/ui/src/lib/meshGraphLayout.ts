import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";

/** Node card dimensions; also given to React Flow as static dimensions. */
export const MESH_NODE_WIDTH = 190;
export const MESH_NODE_HEIGHT = 82;

const ROLE_RANK: Record<MeshRole, number> = {
  coordinator: 0,
  router: 1,
  end_device: 2,
  unknown: 2,
};

export interface StructuralLayoutEdge {
  id: string;
  sources: string[];
  targets: string[];
}

/**
 * Build the simplified structural edge set used for graph-shape analysis
 * (e.g. dense-mode detection) — never for rendering.
 *
 * The structural graph answers "how connected is this mesh?", not "what
 * exact evidence should be drawn?", so:
 * - every device pair contributes at most one edge, regardless of direction
 *   or how many parallel evidence classes connect it;
 * - edges are oriented coordinator → router → end device;
 * - edges referencing a node that is not in the device list are skipped
 *   (placeholder devices for such endpoints are created upstream in the
 *   evidence mapper; this is a last line of defence).
 */
export function buildStructuralLayoutEdges(
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
): StructuralLayoutEdge[] {
  const roleById = new Map(devices.map((d) => [d.ieee_address, d.role]));
  const seenPairs = new Set<string>();
  const layoutEdges: StructuralLayoutEdge[] = [];

  for (const edge of edges) {
    if (edge.source === edge.target) continue;
    if (!roleById.has(edge.source) || !roleById.has(edge.target)) continue;
    const pairKey = [edge.source, edge.target].sort().join("|");
    if (seenPairs.has(pairKey)) continue;
    seenPairs.add(pairKey);

    const sourceRank = ROLE_RANK[roleById.get(edge.source) ?? "end_device"];
    const targetRank = ROLE_RANK[roleById.get(edge.target) ?? "end_device"];
    const [from, to] =
      sourceRank <= targetRank ? [edge.source, edge.target] : [edge.target, edge.source];
    layoutEdges.push({ id: `layout-${pairKey}`, sources: [from], targets: [to] });
  }

  return layoutEdges;
}
