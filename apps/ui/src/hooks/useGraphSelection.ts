import { useEffect, useMemo, useState } from "react";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";

interface GraphSelectionEvidence {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
}

type GraphSelection =
  | { kind: "edge"; networkId: string; id: string }
  | { kind: "device"; networkId: string; id: string }
  | null;

export function useGraphSelection(
  networkId: string | undefined,
  evidence: GraphSelectionEvidence | null,
) {
  const [selection, setSelection] = useState<GraphSelection>(null);
  const selectionIsForNetwork = selection?.networkId === networkId;

  const selectedEdge = useMemo(() => {
    if (!selectionIsForNetwork || selection?.kind !== "edge" || evidence === null) return null;
    return evidence.edges.find((edge) => edge.id === selection.id) ?? null;
  }, [evidence, selection, selectionIsForNetwork]);

  const selectedDevice = useMemo(() => {
    if (!selectionIsForNetwork || selection?.kind !== "device" || evidence === null) return null;
    return evidence.devices.find((device) => device.ieee_address === selection.id) ?? null;
  }, [evidence, selection, selectionIsForNetwork]);

  useEffect(() => {
    if (selection === null) return;
    if (!selectionIsForNetwork) {
      setSelection(null);
      return;
    }
    if (evidence === null) return;
    const identityStillExists =
      selection.kind === "edge"
        ? evidence.edges.some((edge) => edge.id === selection.id)
        : evidence.devices.some((device) => device.ieee_address === selection.id);
    if (!identityStillExists) setSelection(null);
  }, [evidence, selection, selectionIsForNetwork]);

  const selectEdge = (edge: MeshEvidenceEdge) => {
    setSelection({ kind: "edge", networkId: networkId ?? edge.network_id, id: edge.id });
  };

  const selectNode = (device: MeshEvidenceDevice) => {
    setSelection({
      kind: "device",
      networkId: networkId ?? device.network_id,
      id: device.ieee_address,
    });
  };

  const clearSelection = () => {
    setSelection(null);
  };

  const clearEdge = () => setSelection((current) => (current?.kind === "edge" ? null : current));
  const clearNode = () => setSelection((current) => (current?.kind === "device" ? null : current));

  return {
    selectedEdge,
    selectedDevice,
    selectedNodeId:
      selectionIsForNetwork && selection?.kind === "device" ? selection.id : null,
    selectEdge,
    selectNode,
    clearSelection,
    clearEdge,
    clearNode,
  };
}
