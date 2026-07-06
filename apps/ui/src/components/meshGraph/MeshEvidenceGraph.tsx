import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type EdgeMarker,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { evidenceClassLabel } from "@/lib/meshEvidence";
import { evidenceEdgeStyle } from "@/components/meshGraph/evidenceStyles";
import { MeshDeviceNode } from "@/components/meshGraph/MeshDeviceNode";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";
import {
  borderPositionsForEdge,
  handleIdsForPositions,
  meshNodeStaticHandles,
} from "@/lib/meshGraphEdgeGeometry";
import { deviceHasIssue } from "@/lib/meshGraphDense";
import {
  applySavedPositions,
  computeMeshLayout,
  loadSavedPositions,
  saveNodePosition,
  type MeshLayoutMode,
  type MeshPoint,
  type SavedPositions,
} from "@/lib/meshGraphSmartLayout";

const nodeTypes = { meshDevice: MeshDeviceNode };

/** Shared static handles — see meshNodeStaticHandles. */
const STATIC_HANDLES = meshNodeStaticHandles();

function edgeAriaLabel(
  edge: MeshEvidenceEdge,
  nameOf: (ieee: string) => string,
): string {
  const relation = edge.directional
    ? `from ${nameOf(edge.source)} to ${nameOf(edge.target)}`
    : `between ${nameOf(edge.source)} and ${nameOf(edge.target)}`;
  return `${evidenceClassLabel(edge.evidence_class)} ${relation}`;
}

type EdgeFocus = "normal" | "focused" | "muted";

function edgeFocusFor(edge: MeshEvidenceEdge, selectedNodeId: string | null): EdgeFocus {
  if (!selectedNodeId) return "normal";
  return edge.source === selectedNodeId || edge.target === selectedNodeId
    ? "focused"
    : "muted";
}

function buildFlowEdge(
  edge: MeshEvidenceEdge,
  positions: Map<string, MeshPoint>,
  nameOf: (ieee: string) => string,
  focus: EdgeFocus,
): Edge {
  const style = evidenceEdgeStyle(edge.evidence_class);
  const sourcePos = positions.get(edge.source);
  const targetPos = positions.get(edge.target);
  const borders =
    sourcePos && targetPos
      ? borderPositionsForEdge(
          { x: sourcePos.x, y: sourcePos.y, width: MESH_NODE_WIDTH, height: MESH_NODE_HEIGHT },
          { x: targetPos.x, y: targetPos.y, width: MESH_NODE_WIDTH, height: MESH_NODE_HEIGHT },
        )
      : undefined;
  const handles = borders ? handleIdsForPositions(borders) : undefined;

  const marker: EdgeMarker | undefined = edge.directional
    ? { type: MarkerType.ArrowClosed, color: style.stroke, width: 16, height: 16 }
    : undefined;

  // Visual focus only — never changes which evidence exists or its meaning.
  const baseOpacity = style.opacity ?? 1;
  const opacity =
    focus === "focused" ? Math.min(1, baseOpacity + 0.2) : focus === "muted" ? baseOpacity * 0.3 : baseOpacity;
  const strokeWidth = focus === "focused" ? style.strokeWidth + 0.75 : style.strokeWidth;

  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "straight",
    sourceHandle: handles?.sourceHandle,
    targetHandle: handles?.targetHandle,
    className: `mesh-edge mesh-edge--${edge.evidence_class} mesh-edge--focus-${focus}`,
    ariaLabel: edgeAriaLabel(edge, nameOf),
    interactionWidth: 24,
    style: {
      stroke: style.stroke,
      strokeWidth,
      strokeDasharray: style.strokeDasharray,
      strokeLinecap: style.strokeLinecap,
      opacity,
    },
    markerEnd: marker,
    data: { evidence: edge },
  };
}

/**
 * Mesh evidence graph renderer.
 *
 * Positions come from the synchronous, deterministic ZigbeeLens smart-layout
 * pipeline (never a generic auto-layout), overlaid with the user's saved
 * manual positions. Layout depends only on the device set, the full evidence
 * set, the layout mode and saved positions — so filter toggles, drawer
 * open/close and selection never move nodes. React Flow is keyed by
 * network/mode/reset identity so fitView fires only on first load, network
 * change, mode change and explicit reset.
 *
 * Edges attach on the node side that faces their neighbour (not fixed
 * top/bottom ports), and render as straight segments so lines leave boxes
 * in a sensible direction.
 */
export function MeshEvidenceGraph({
  devices,
  visibleEdges,
  allEdges,
  signatureSeed,
  layoutMode,
  positionStorageId,
  resetNonce,
  highlightIssueDevices,
  selectedNodeId,
  onSelectEdge,
  onSelectNode,
}: {
  devices: MeshEvidenceDevice[];
  visibleEdges: MeshEvidenceEdge[];
  allEdges: MeshEvidenceEdge[];
  signatureSeed: string;
  layoutMode: MeshLayoutMode;
  positionStorageId: string;
  resetNonce: number;
  highlightIssueDevices: boolean;
  selectedNodeId: string | null;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
}) {
  const [savedPositions, setSavedPositions] = useState<SavedPositions>(() =>
    loadSavedPositions(positionStorageId, layoutMode),
  );
  useEffect(() => {
    setSavedPositions(loadSavedPositions(positionStorageId, layoutMode));
  }, [positionStorageId, layoutMode, resetNonce]);

  const positions = useMemo(() => {
    const generated = computeMeshLayout(devices, allEdges, layoutMode);
    return applySavedPositions(generated, savedPositions);
  }, [devices, allEdges, layoutMode, savedPositions]);

  const nameById = useMemo(
    () => new Map(devices.map((d) => [d.ieee_address, d.friendly_name])),
    [devices],
  );
  const issueIds = useMemo(
    () => new Set(devices.filter(deviceHasIssue).map((d) => d.ieee_address)),
    [devices],
  );
  const selectionNeighbourhood = useMemo(() => {
    if (!selectedNodeId) return null;
    const ids = new Set<string>([selectedNodeId]);
    for (const edge of allEdges) {
      if (edge.source === selectedNodeId) ids.add(edge.target);
      if (edge.target === selectedNodeId) ids.add(edge.source);
    }
    return ids;
  }, [allEdges, selectedNodeId]);

  const emphasiseIssues = highlightIssueDevices || layoutMode === "health";

  const computedNodes: Node[] = useMemo(
    () =>
      devices.map((device) => {
        const isIssue = issueIds.has(device.ieee_address);
        const inNeighbourhood =
          selectionNeighbourhood?.has(device.ieee_address) ?? true;
        const mutedBySelection = selectionNeighbourhood !== null && !inNeighbourhood;
        const mutedByHealth =
          emphasiseIssues && layoutMode === "health" && !isIssue && device.role !== "coordinator";

        const classNames = ["mesh-node"];
        if (emphasiseIssues && isIssue) classNames.push("mesh-node--issue-highlight");
        if (mutedBySelection || mutedByHealth) classNames.push("mesh-node--muted");

        return {
          id: device.ieee_address,
          type: "meshDevice",
          position: positions.get(device.ieee_address) ?? { x: 0, y: 0 },
          width: MESH_NODE_WIDTH,
          height: MESH_NODE_HEIGHT,
          handles: STATIC_HANDLES,
          selected: device.ieee_address === selectedNodeId,
          className: classNames.join(" "),
          style: {
            opacity: mutedBySelection ? 0.35 : mutedByHealth ? 0.55 : 1,
            ...(emphasiseIssues && isIssue
              ? { boxShadow: "0 0 0 3px rgba(230, 116, 74, 0.65)", borderRadius: 10 }
              : {}),
          },
          data: { device },
        } satisfies Node;
      }),
    [devices, positions, selectedNodeId, issueIds, selectionNeighbourhood, emphasiseIssues, layoutMode],
  );

  const [nodes, setNodes] = useState<Node[]>(computedNodes);
  useEffect(() => {
    setNodes(computedNodes);
  }, [computedNodes]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      const next = saveNodePosition(positionStorageId, layoutMode, node.id, {
        x: node.position.x,
        y: node.position.y,
      });
      setSavedPositions(next);
    },
    [positionStorageId, layoutMode],
  );

  const edges: Edge[] = useMemo(
    () =>
      visibleEdges.map((edge) =>
        buildFlowEdge(
          edge,
          positions,
          (ieee) => nameById.get(ieee) ?? ieee,
          edgeFocusFor(edge, selectedNodeId),
        ),
      ),
    [visibleEdges, positions, nameById, selectedNodeId],
  );

  return (
    <div className="h-full" data-layout-mode={layoutMode}>
      <ReactFlow
        key={`${signatureSeed}|${layoutMode}|${resetNonce}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={onNodeDragStop}
        nodesDraggable
        fitView
        fitViewOptions={{ padding: 0.12, minZoom: 0.08, maxZoom: 1.5 }}
        minZoom={0.05}
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
        <MiniMap
          pannable
          zoomable
          ariaLabel="Graph overview minimap"
          className="!h-28 !w-44 !rounded-lg !border !border-zl-border !bg-zl-surface"
          maskColor="rgba(10, 15, 22, 0.7)"
          nodeColor={(node) => {
            const device = (node.data as { device?: MeshEvidenceDevice } | undefined)?.device;
            if (!device) return "#2a3648";
            if (issueIds.has(device.ieee_address)) return "#e6744a";
            if (device.role === "coordinator") return "#5b9fd4";
            if (device.role === "router") return "#3d6f9e";
            return "#2a3648";
          }}
        />
      </ReactFlow>
    </div>
  );
}
