import { useState } from "react";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";

export function useGraphSelection() {
  const [selectedEdge, setSelectedEdge] = useState<MeshEvidenceEdge | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<MeshEvidenceDevice | null>(null);

  const selectEdge = (edge: MeshEvidenceEdge) => {
    setSelectedDevice(null);
    setSelectedEdge(edge);
  };

  const selectNode = (device: MeshEvidenceDevice) => {
    setSelectedEdge(null);
    setSelectedDevice(device);
  };

  const clearSelection = () => {
    setSelectedEdge(null);
    setSelectedDevice(null);
  };

  const clearEdge = () => setSelectedEdge(null);
  const clearNode = () => setSelectedDevice(null);

  return {
    selectedEdge,
    selectedDevice,
    selectedNodeId: selectedDevice?.ieee_address ?? null,
    selectEdge,
    selectNode,
    clearSelection,
    clearEdge,
    clearNode,
  };
}
