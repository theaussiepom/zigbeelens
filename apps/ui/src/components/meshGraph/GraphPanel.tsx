import { useMemo, useState } from "react";
import { GraphCanvasPanel } from "@/components/meshGraph/GraphCanvasPanel";
import { GraphSidebar } from "@/components/meshGraph/GraphSidebar";
import { GraphToolbar } from "@/components/meshGraph/GraphToolbar";
import type { InvestigationFocus } from "@/components/meshGraph/MeshEvidenceGraph";
import { useGraphConnectionControls } from "@/hooks/useGraphConnectionControls";
import type { InvestigationCard } from "@/lib/api";
import { type MeshEvidenceDevice, type MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  DEFAULT_LAYOUT_MODE,
  clearSavedPositions,
  type MeshLayoutMode,
} from "@/lib/meshGraphSmartLayout";
import type {
  ConnectionHistoryPresentationViewModel,
} from "@/viewModels/topology/connectionHistoryPresentationViewModel";

export function GraphPanel({
  devices,
  edges,
  investigations,
  signatureSeed,
  networkId,
  networkName,
  positionStorageId,
  onSelectEdge,
  onSelectNode,
  onClearSelection,
  selectedNodeId,
  selectedEdge,
  historyPresentation,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  investigations: InvestigationCard[];
  signatureSeed: string;
  networkId: string;
  networkName?: string | null;
  positionStorageId: string;
  onSelectEdge: (edge: MeshEvidenceEdge) => void;
  onSelectNode: (device: MeshEvidenceDevice) => void;
  onClearSelection: () => void;
  selectedNodeId: string | null;
  selectedEdge: MeshEvidenceEdge | null;
  historyPresentation: ConnectionHistoryPresentationViewModel;
}) {
  const {
    controls,
    visibleEdges,
    hasOldUncertainLinks,
    hasRouteHints,
    hasRecentMissingLinks,
    hasPassiveHints,
    hasLastKnownLinks,
    activePreset,
    setControl,
    setPreset,
    resetConnectionChoices,
  } = useGraphConnectionControls({
    devices,
    edges,
    positionStorageId,
    selectedNodeId,
    selectedEdge,
  });

  const [layoutMode, setLayoutMode] = useState<MeshLayoutMode>(DEFAULT_LAYOUT_MODE);
  const [resetNonce, setResetNonce] = useState(0);
  // Investigation focus is visual only: it highlights involved devices,
  // ensures involved edges are drawn, and dims the rest. It never moves
  // nodes, never changes connection controls, never mutates saved layout.
  const [activeInvestigation, setActiveInvestigation] = useState<InvestigationCard | null>(null);

  // Visual focus comes from the active investigation card.
  const visualFocus: InvestigationFocus | null = useMemo(() => {
    if (activeInvestigation) {
      return {
        deviceIds: new Set(activeInvestigation.device_ieees),
        edgeIds: new Set(activeInvestigation.edge_ids),
      };
    }
    return null;
  }, [activeInvestigation]);

  // A focused investigation's edges are drawn even when they would normally
  // sit outside the focused-view budget. Connection controls are untouched,
  // and layout does not depend on visible edges, so nothing moves.
  const renderedEdges = useMemo(() => {
    if (!visualFocus) return visibleEdges;
    const present = new Set(visibleEdges.map((edge) => edge.id));
    const extras = edges.filter(
      (edge) => !present.has(edge.id) && visualFocus.edgeIds.has(edge.id),
    );
    return extras.length ? [...visibleEdges, ...extras] : visibleEdges;
  }, [visibleEdges, edges, visualFocus]);

  const resetLayout = () => {
    clearSavedPositions(positionStorageId, layoutMode);
    setResetNonce((nonce) => nonce + 1);
  };

  // Selecting a searched device reuses the existing selected-device
  // behaviour (highlight, evidence neighbourhood, device details panel).
  // Search never moves nodes, never recomputes layout and never touches the
  // saved connection choices. Investigation focus is cleared so the focus
  // mechanisms cannot fight.
  const selectSearchedDevice = (device: MeshEvidenceDevice) => {
    setActiveInvestigation(null);
    onSelectNode(device);
  };

  const canOpenPrimaryDevice = (card: InvestigationCard): boolean => {
    const ieee = card.primary_neighbourhood_ieee;
    return Boolean(ieee && devices.some((device) => device.ieee_address === ieee));
  };

  const openPrimaryDevice = (card: InvestigationCard) => {
    const ieee = card.primary_neighbourhood_ieee;
    if (!ieee) return;
    const device = devices.find((entry) => entry.ieee_address === ieee);
    if (!device) return;
    // Keep investigation focus while opening the existing device drawer.
    setActiveInvestigation(card);
    onSelectNode(device);
  };

  return (
    <div className="space-y-4">
      <GraphToolbar
        devices={devices}
        edges={edges}
        networkId={networkId}
        networkName={networkName}
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        onResetLayout={resetLayout}
        onSelectDevice={selectSearchedDevice}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-stretch">
        {/* The graph stretches to the full grid row: at least the viewport
            (minus app chrome) and never shorter than the sidebar column, so
            it always reaches the bottom of the content area. */}
        <GraphCanvasPanel
          devices={devices}
          visibleEdges={renderedEdges}
          allEdges={edges}
          signatureSeed={signatureSeed}
          layoutMode={layoutMode}
          positionStorageId={positionStorageId}
          resetNonce={resetNonce}
          selectedNodeId={selectedNodeId}
          investigationFocus={visualFocus}
          onSelectEdge={onSelectEdge}
          onSelectNode={onSelectNode}
          onClearSelection={onClearSelection}
        />
        <GraphSidebar
          investigations={investigations}
          activeInvestigationId={activeInvestigation?.id ?? null}
          onFocusInvestigation={setActiveInvestigation}
          onClearInvestigationFocus={() => setActiveInvestigation(null)}
          canOpenPrimaryDevice={canOpenPrimaryDevice}
          onOpenPrimaryDevice={openPrimaryDevice}
          hasPassiveHints={hasPassiveHints}
          hasLastKnownLinks={hasLastKnownLinks}
          hasRouteHints={hasRouteHints}
          hasOldUncertainLinks={hasOldUncertainLinks}
          hasRecentMissingLinks={hasRecentMissingLinks}
          historyPresentation={historyPresentation}
          controls={controls}
          activePreset={activePreset}
          setControl={setControl}
          setPreset={setPreset}
          resetConnectionChoices={resetConnectionChoices}
        />
      </div>
    </div>
  );
}
