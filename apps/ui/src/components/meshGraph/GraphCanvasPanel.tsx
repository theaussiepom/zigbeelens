import { Card } from "@/components/ui";
import {
  MeshEvidenceGraph,
  type InvestigationFocus,
} from "@/components/meshGraph/MeshEvidenceGraph";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import type { MeshLayoutMode } from "@/lib/meshGraphSmartLayout";

export function GraphCanvasPanel({
  devices,
  visibleEdges,
  allEdges,
  signatureSeed,
  layoutMode,
  positionStorageId,
  resetNonce,
  selectedNodeId,
  investigationFocus,
  onSelectEdge,
  onSelectNode,
  onClearSelection,
}: {
  devices: MeshEvidenceDevice[];
  visibleEdges: MeshEvidenceEdge[];
  allEdges: MeshEvidenceEdge[];
  signatureSeed: string;
  layoutMode: MeshLayoutMode;
  positionStorageId: string;
  resetNonce: number;
  selectedNodeId: string | null;
  investigationFocus: InvestigationFocus | null;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
  onClearSelection: () => void;
}) {
  return (
    <Card className="flex !p-2">
      <div
        className="min-h-[600px] w-full lg:min-h-[calc(100dvh-13rem)]"
        data-testid="mesh-evidence-graph"
      >
        <MeshEvidenceGraph
          devices={devices}
          visibleEdges={visibleEdges}
          allEdges={allEdges}
          signatureSeed={signatureSeed}
          layoutMode={layoutMode}
          positionStorageId={positionStorageId}
          resetNonce={resetNonce}
          selectedNodeId={selectedNodeId}
          investigationFocus={investigationFocus}
          onSelectEdge={onSelectEdge}
          onSelectNode={onSelectNode}
          onClearSelection={onClearSelection}
        />
      </div>
    </Card>
  );
}
