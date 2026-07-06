import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";

/** Node card dimensions; also given to React Flow as static dimensions. */
export const MESH_NODE_WIDTH = 190;
export const MESH_NODE_HEIGHT = 82;

export interface MeshNodePosition {
  x: number;
  y: number;
}

const ROLE_RANK: Record<MeshRole, number> = {
  coordinator: 0,
  router: 1,
  end_device: 2,
};

/**
 * Deterministic layered layout via ELK.js.
 *
 * The layout is computed from the full (unfiltered) evidence set so node
 * positions stay stable when evidence filters change. Layout edges are
 * oriented coordinator → router → end device so the layered algorithm
 * produces a coordinator-centred, top-down hierarchy regardless of which
 * direction the underlying evidence claims point.
 */
export async function layoutMeshGraph(
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
): Promise<Map<string, MeshNodePosition>> {
  const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
  const elk = new ELK();

  const roleById = new Map(devices.map((d) => [d.ieee_address, d.role]));

  // Deduplicate node pairs so parallel evidence edges do not distort spacing.
  const seenPairs = new Set<string>();
  const layoutEdges: Array<{ id: string; sources: string[]; targets: string[] }> = [];
  for (const edge of edges) {
    const sourceRank = ROLE_RANK[roleById.get(edge.source) ?? "end_device"];
    const targetRank = ROLE_RANK[roleById.get(edge.target) ?? "end_device"];
    const [from, to] = sourceRank <= targetRank ? [edge.source, edge.target] : [edge.target, edge.source];
    const key = `${from}->${to}`;
    if (seenPairs.has(key)) continue;
    seenPairs.add(key);
    layoutEdges.push({ id: `layout-${key}`, sources: [from], targets: [to] });
  }

  const graph = {
    id: "mesh-evidence-graph",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.layered.spacing.nodeNodeBetweenLayers": "110",
      "elk.spacing.nodeNode": "48",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.crossingMinimization.forceNodeModelOrder": "true",
    },
    children: devices.map((device) => ({
      id: device.ieee_address,
      width: MESH_NODE_WIDTH,
      height: MESH_NODE_HEIGHT,
    })),
    edges: layoutEdges,
  };

  const result = await elk.layout(graph);
  const positions = new Map<string, MeshNodePosition>();
  for (const child of result.children ?? []) {
    positions.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
  }
  return positions;
}
