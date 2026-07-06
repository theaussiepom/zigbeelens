import { useEffect, useMemo, useRef, useState } from "react";
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
  buildGraphSignature,
  buildStructuralLayoutEdges,
  chooseLayoutStrategy,
  layoutMeshGraph,
  type MeshLayoutResult,
} from "@/lib/meshGraphLayout";

export const LAYOUT_ERROR_COPY =
  "The graph layout could not be computed for this snapshot. The topology data is still available in the snapshot and device views.";

export const FAST_LAYOUT_NOTE_COPY =
  "Dense graph mode used a faster layout to keep the graph responsive.";

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

type EdgeFocus = "normal" | "focused" | "muted";

function edgeFocusFor(edge: MeshEvidenceEdge, selectedNodeId: string | null): EdgeFocus {
  if (!selectedNodeId) return "normal";
  return edge.source === selectedNodeId || edge.target === selectedNodeId
    ? "focused"
    : "muted";
}

function buildFlowEdge(
  edge: MeshEvidenceEdge,
  roleOf: (ieee: string) => MeshRole,
  nameOf: (ieee: string) => string,
  focus: EdgeFocus,
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

  // Visual focus only — never changes which evidence exists or its meaning.
  const baseOpacity = style.opacity ?? 1;
  const opacity =
    focus === "focused" ? Math.min(1, baseOpacity + 0.2) : focus === "muted" ? baseOpacity * 0.3 : baseOpacity;
  const strokeWidth = focus === "focused" ? style.strokeWidth + 0.75 : style.strokeWidth;

  return {
    id: edge.id,
    source: renderSource,
    target: renderTarget,
    type: edgeType(edge),
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
    markerEnd: flip ? undefined : marker,
    markerStart: flip ? marker : undefined,
    data: { evidence: edge },
  };
}

/**
 * Mesh evidence graph renderer.
 *
 * Layout is computed with ELK from the full (unfiltered) evidence set and is
 * cached per graph signature: routine API refetches, filter toggles, drawer
 * open/close and selection changes never recompute layout or move nodes.
 * React Flow is keyed by the signature of the *displayed* layout, so fitView
 * fires only on first load and when the positional graph materially changes.
 */
export function MeshEvidenceGraph({
  devices,
  visibleEdges,
  allEdges,
  signatureSeed,
  selectedNodeId,
  onSelectEdge,
  onSelectNode,
}: {
  devices: MeshEvidenceDevice[];
  visibleEdges: MeshEvidenceEdge[];
  allEdges: MeshEvidenceEdge[];
  /**
   * Stable identity of the data source: network id, data-source mode and
   * snapshot id/captured-at. Must not include fetch times or UI state.
   */
  signatureSeed: string;
  selectedNodeId: string | null;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
}) {
  const structuralEdges = useMemo(
    () => buildStructuralLayoutEdges(devices, allEdges),
    [devices, allEdges],
  );
  const strategy = chooseLayoutStrategy(structuralEdges.length);
  const signature = useMemo(
    () => buildGraphSignature(signatureSeed, devices, structuralEdges, strategy),
    [signatureSeed, devices, structuralEdges, strategy],
  );

  const [layout, setLayout] = useState<{ signature: string; result: MeshLayoutResult } | null>(
    null,
  );
  const [layoutFailed, setLayoutFailed] = useState(false);

  // The effect below is keyed on the signature alone; it reads the latest
  // inputs through this ref so identity-only changes (fresh arrays from a
  // routine refetch with identical content) never trigger a relayout.
  const layoutInputRef = useRef({ devices, allEdges, structuralEdges });
  layoutInputRef.current = { devices, allEdges, structuralEdges };

  useEffect(() => {
    let cancelled = false;
    const input = layoutInputRef.current;
    layoutMeshGraph(input.devices, input.allEdges, { structuralEdges: input.structuralEdges })
      .then((result) => {
        // A resolve racing a newer signature must never overwrite it.
        if (cancelled) return;
        setLayout({ signature, result });
        setLayoutFailed(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // Diagnostics only — counts and the ELK error, no payload contents.
        console.error(
          `[mesh-graph] layout failed for ${input.devices.length} devices / ${input.allEdges.length} evidence edges`,
          error,
        );
        setLayoutFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [signature]);

  const positions = layout?.result.positions ?? null;

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
          edgeFocusFor(edge, selectedNodeId),
        ),
      ),
    [visibleEdges, roleById, nameById, selectedNodeId],
  );

  if (layoutFailed) {
    return (
      <div
        role="alert"
        data-testid="graph-layout-error"
        className="flex h-full items-center justify-center p-6"
      >
        <div className="max-w-md space-y-2 rounded-lg border border-zl-watch/40 bg-zl-watch/10 p-4 text-sm">
          <p className="font-medium text-zl-text">Graph layout unavailable</p>
          <p className="text-zl-muted">{LAYOUT_ERROR_COPY}</p>
        </div>
      </div>
    );
  }

  if (!layout) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zl-muted">
        <span className="animate-pulse">Computing layout…</span>
      </div>
    );
  }

  return (
    <div
      className="relative h-full"
      data-layout-strategy={layout.result.strategy}
      data-layout-structural-edges={layout.result.structuralEdgeCount}
    >
      <ReactFlow
        // Keyed by the displayed layout's signature: fitView reruns only when
        // the positional graph truly changed, never on routine refresh.
        key={layout.signature}
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
      {layout.result.strategy === "mrtree" && (
        <p
          data-testid="graph-fast-layout-note"
          className="pointer-events-none absolute bottom-2 right-2 rounded-md border border-zl-border bg-zl-surface/90 px-2 py-1 text-[11px] text-zl-muted"
        >
          {FAST_LAYOUT_NOTE_COPY}
        </p>
      )}
    </div>
  );
}
