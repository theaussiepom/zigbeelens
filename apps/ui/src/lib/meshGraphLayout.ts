import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";

/** Node card dimensions; also given to React Flow as static dimensions. */
export const MESH_NODE_WIDTH = 190;
export const MESH_NODE_HEIGHT = 82;

export interface MeshNodePosition {
  x: number;
  y: number;
}

export type MeshLayoutStrategy = "layered" | "mrtree";

export interface MeshLayoutResult {
  positions: Map<string, MeshNodePosition>;
  /** Which ELK algorithm produced the positions (debug/diagnostics). */
  strategy: MeshLayoutStrategy;
  /** Structural (deduplicated) edge count actually fed to ELK. */
  structuralEdgeCount: number;
}

export interface MeshLayoutOptions {
  /**
   * Above this many structural edges the layered algorithm becomes too slow
   * for the browser (minutes on real dense meshes), so mrtree is used instead.
   */
  denseEdgeThreshold?: number;
  /** Per-attempt timeout; a hung layout rejects instead of spinning forever. */
  timeoutMs?: number;
  /** Reuse structural edges the caller already computed (e.g. for signatures). */
  structuralEdges?: StructuralLayoutEdge[];
}

export const DENSE_GRAPH_EDGE_THRESHOLD = 400;
export const LAYOUT_TIMEOUT_MS = 20_000;

/** Which ELK algorithm will be attempted first for a given structural size. */
export function chooseLayoutStrategy(
  structuralEdgeCount: number,
  denseEdgeThreshold: number = DENSE_GRAPH_EDGE_THRESHOLD,
): MeshLayoutStrategy {
  return structuralEdgeCount > denseEdgeThreshold ? "mrtree" : "layered";
}

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
 * Build the simplified structural edge set used only for positioning.
 *
 * The layout graph answers "where should nodes sit?", not "what exact
 * evidence should be drawn?", so:
 * - every device pair contributes at most one edge, regardless of direction
 *   or how many parallel evidence classes connect it;
 * - edges are oriented coordinator → router → end device so the layered
 *   algorithm produces a coordinator-centred, top-down hierarchy;
 * - edges referencing a node that is not in the device list are skipped —
 *   ELK rejects the whole graph ("Referenced shape does not exist")
 *   otherwise. Placeholder devices for such endpoints are created upstream
 *   in the evidence mapper; this is a last line of defence.
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

/**
 * Stable identity of the *positional* graph.
 *
 * Layout must be recomputed only when this signature changes. It contains
 * the seed (network / data-source / snapshot identity from the caller), the
 * node id set, the structural edge id set and the layout algorithm — and
 * deliberately excludes anything volatile: fetch timestamps, filter toggles,
 * selection, hover and drawer state, and render-edge visibility.
 */
export function buildGraphSignature(
  seed: string,
  devices: MeshEvidenceDevice[],
  structuralEdges: StructuralLayoutEdge[],
  strategy: MeshLayoutStrategy,
): string {
  const nodeIds = devices
    .map((d) => d.ieee_address)
    .sort()
    .join(",");
  const edgeIds = structuralEdges
    .map((e) => e.id)
    .sort()
    .join(",");
  return `${seed}::${strategy}::${nodeIds}::${edgeIds}`;
}

function layoutOptionsFor(strategy: MeshLayoutStrategy): Record<string, string> {
  if (strategy === "mrtree") {
    return {
      "elk.algorithm": "mrtree",
      "elk.direction": "DOWN",
      "elk.spacing.nodeNode": "48",
    };
  }
  return {
    "elk.algorithm": "layered",
    "elk.direction": "DOWN",
    "elk.layered.spacing.nodeNodeBetweenLayers": "110",
    "elk.spacing.nodeNode": "48",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
    "elk.layered.crossingMinimization.forceNodeModelOrder": "true",
  };
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`Mesh graph layout (${label}) timed out after ${timeoutMs}ms`)),
      timeoutMs,
    );
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/**
 * Deterministic layout via ELK.js.
 *
 * The layout is computed from the full (unfiltered) evidence set so node
 * positions stay stable when evidence filters change. Dense graphs use the
 * much faster mrtree algorithm; if the primary algorithm fails or times out,
 * mrtree is tried as a fallback before rejecting.
 */
export async function layoutMeshGraph(
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
  options: MeshLayoutOptions = {},
): Promise<MeshLayoutResult> {
  const denseEdgeThreshold = options.denseEdgeThreshold ?? DENSE_GRAPH_EDGE_THRESHOLD;
  const timeoutMs = options.timeoutMs ?? LAYOUT_TIMEOUT_MS;

  const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
  const elk = new ELK();

  const layoutEdges = options.structuralEdges ?? buildStructuralLayoutEdges(devices, edges);
  const children = devices.map((device) => ({
    id: device.ieee_address,
    width: MESH_NODE_WIDTH,
    height: MESH_NODE_HEIGHT,
  }));

  const primary = chooseLayoutStrategy(layoutEdges.length, denseEdgeThreshold);
  const strategies: MeshLayoutStrategy[] =
    primary === "layered" ? ["layered", "mrtree"] : ["mrtree"];

  let lastError: unknown = null;
  for (const strategy of strategies) {
    const graph = {
      id: "mesh-evidence-graph",
      layoutOptions: layoutOptionsFor(strategy),
      children,
      edges: layoutEdges,
    };
    try {
      const result = await withTimeout(elk.layout(graph), timeoutMs, strategy);
      const positions = new Map<string, MeshNodePosition>();
      for (const child of result.children ?? []) {
        positions.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
      }
      return { positions, strategy, structuralEdgeCount: layoutEdges.length };
    } catch (error) {
      lastError = error;
      console.warn(
        `[mesh-graph] ${strategy} layout failed (${children.length} nodes, ${layoutEdges.length} structural edges)`,
        error,
      );
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}
