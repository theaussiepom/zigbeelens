import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type EdgeMarker,
  type Node,
  type NodeHandle,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type {
  MeshEvidenceDevice,
  MeshEvidenceEdge,
  MeshRole,
} from "@/lib/meshEvidence";
import { evidenceClassLabel } from "@/lib/meshEvidence";
import { evidenceEdgeStyle } from "@/components/meshGraph/evidenceStyles";
import { MeshDeviceNode } from "@/components/meshGraph/MeshDeviceNode";
import {
  MESH_NODE_HEIGHT,
  MESH_NODE_WIDTH,
  layoutMeshGraph,
  type MeshNodePosition,
} from "@/lib/meshGraphLayout";

const nodeTypes = { meshDevice: MeshDeviceNode };

/**
 * Static handle geometry so edges can render before (or without) DOM
 * measurement — required for deterministic first paint and jsdom tests.
 */
const STATIC_HANDLES: NodeHandle[] = [
  {
    type: "target",
    position: Position.Top,
    x: MESH_NODE_WIDTH / 2,
    y: 0,
    width: 6,
    height: 6,
  },
  {
    type: "source",
    position: Position.Bottom,
    x: MESH_NODE_WIDTH / 2,
    y: MESH_NODE_HEIGHT,
    width: 6,
    height: 6,
  },
];

const ROLE_RANK: Record<MeshRole, number> = {
  coordinator: 0,
  router: 1,
  end_device: 2,
  unknown: 2,
};

function edgeAriaLabel(
  edge: MeshEvidenceEdge,
  nameOf: (ieee: string) => string,
): string {
  const relation = edge.directional
    ? `from ${nameOf(edge.source)} to ${nameOf(edge.target)}`
    : `between ${nameOf(edge.source)} and ${nameOf(edge.target)}`;
  return `${evidenceClassLabel(edge.evidence_class)} ${relation}`;
}

/** Edge shape per class keeps parallel evidence edges visually separable. */
function edgeType(edge: MeshEvidenceEdge): string {
  switch (edge.evidence_class) {
    case "latest_snapshot_route":
    case "historical_route":
      return "smoothstep";
    case "passive_derived_association":
    case "stale_low_confidence":
      return "straight";
    default:
      return "default";
  }
}

function buildFlowEdge(
  edge: MeshEvidenceEdge,
  roleOf: (ieee: string) => MeshRole,
  nameOf: (ieee: string) => string,
): Edge {
  const style = evidenceEdgeStyle(edge.evidence_class);
  // Render edges top-down (higher role first) so the layered layout stays
  // clean; if the evidence direction is the reverse, the arrow moves to the
  // path start so it still points at the evidence target.
  const flip = ROLE_RANK[roleOf(edge.source)] > ROLE_RANK[roleOf(edge.target)];
  const renderSource = flip ? edge.target : edge.source;
  const renderTarget = flip ? edge.source : edge.target;

  const marker: EdgeMarker | undefined = edge.directional
    ? { type: MarkerType.ArrowClosed, color: style.stroke, width: 16, height: 16 }
    : undefined;

  return {
    id: edge.id,
    source: renderSource,
    target: renderTarget,
    type: edgeType(edge),
    className: `mesh-edge mesh-edge--${edge.evidence_class}`,
    ariaLabel: edgeAriaLabel(edge, nameOf),
    interactionWidth: 24,
    style: {
      stroke: style.stroke,
      strokeWidth: style.strokeWidth,
      strokeDasharray: style.strokeDasharray,
      strokeLinecap: style.strokeLinecap,
      opacity: style.opacity,
    },
    markerEnd: flip ? undefined : marker,
    markerStart: flip ? marker : undefined,
    data: { evidence: edge },
  };
}

/**
 * Mesh evidence graph renderer.
 *
 * Layout is computed once with ELK from the full evidence set so positions
 * are deterministic and stable while filters toggle edge visibility.
 */
export function MeshEvidenceGraph({
  devices,
  visibleEdges,
  allEdges,
  selectedNodeId,
  onSelectEdge,
  onSelectNode,
}: {
  devices: MeshEvidenceDevice[];
  visibleEdges: MeshEvidenceEdge[];
  allEdges: MeshEvidenceEdge[];
  selectedNodeId: string | null;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
}) {
  const [positions, setPositions] = useState<Map<string, MeshNodePosition> | null>(null);

  useEffect(() => {
    let cancelled = false;
    layoutMeshGraph(devices, allEdges).then((result) => {
      if (!cancelled) setPositions(result);
    });
    return () => {
      cancelled = true;
    };
  }, [devices, allEdges]);

  const roleById = useMemo(
    () => new Map(devices.map((d) => [d.ieee_address, d.role])),
    [devices],
  );
  const nameById = useMemo(
    () => new Map(devices.map((d) => [d.ieee_address, d.friendly_name])),
    [devices],
  );

  const nodes: Node[] = useMemo(() => {
    if (!positions) return [];
    return devices.map((device) => ({
      id: device.ieee_address,
      type: "meshDevice",
      position: positions.get(device.ieee_address) ?? { x: 0, y: 0 },
      width: MESH_NODE_WIDTH,
      height: MESH_NODE_HEIGHT,
      handles: STATIC_HANDLES,
      selected: device.ieee_address === selectedNodeId,
      data: { device },
    }));
  }, [devices, positions, selectedNodeId]);

  const edges: Edge[] = useMemo(
    () =>
      visibleEdges.map((edge) =>
        buildFlowEdge(
          edge,
          (ieee) => roleById.get(ieee) ?? "end_device",
          (ieee) => nameById.get(ieee) ?? ieee,
        ),
      ),
    [visibleEdges, roleById, nameById],
  );

  if (!positions) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zl-muted">
        <span className="animate-pulse">Computing layout…</span>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      minZoom={0.2}
      nodesConnectable={false}
      edgesFocusable
      proOptions={{ hideAttribution: false }}
      onEdgeClick={(_, edge) => {
        const evidence = (edge.data as { evidence?: MeshEvidenceEdge } | undefined)?.evidence;
        if (evidence) onSelectEdge(evidence);
      }}
      onNodeClick={(_, node) => {
        const device = (node.data as { device?: MeshEvidenceDevice } | undefined)?.device;
        if (device) onSelectNode(device);
      }}
      className="!bg-zl-bg"
    >
      <Background gap={24} color="#1a2330" />
      <Controls showInteractive={false} className="!border-zl-border !bg-zl-surface" />
    </ReactFlow>
  );
}
