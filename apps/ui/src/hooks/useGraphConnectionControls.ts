import { useMemo, useState } from "react";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  DEFAULT_CONNECTION_CONTROLS,
  clearConnectionControls,
  collectIssueDeviceIds,
  collectRouteCoveredPairs,
  loadConnectionControls,
  saveConnectionControls,
  selectAdaptiveBestNeighbourLinks,
  selectPassiveHintEdges,
  selectRecentMissingEdges,
  selectVisibleConnectionEdges,
  type ConnectionControls,
} from "@/lib/meshGraphDense";

export function useGraphConnectionControls({
  devices,
  edges,
  positionStorageId,
  selectedNodeId,
  selectedEdge,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  positionStorageId: string;
  selectedNodeId: string | null;
  selectedEdge: MeshEvidenceEdge | null;
}) {
  const [controls, setControls] = useState<ConnectionControls>(() =>
    loadConnectionControls(positionStorageId),
  );

  const bestNeighbourEdgeIds = useMemo(() => {
    const excludePairs = controls.routeHints ? collectRouteCoveredPairs(edges) : undefined;
    return selectAdaptiveBestNeighbourLinks(edges, devices.length, excludePairs).edgeIds;
  }, [edges, devices.length, controls.routeHints]);

  const hasOldUncertainLinks = useMemo(
    () => edges.some((edge) => edge.evidence_class === "stale_low_confidence"),
    [edges],
  );
  const hasRouteHints = useMemo(
    () => edges.some((edge) => edge.evidence_class === "latest_snapshot_route"),
    [edges],
  );
  const recentMissingEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          edge.evidence_class === "historical_neighbor" ||
          edge.evidence_class === "historical_route",
      ),
    [edges],
  );
  const hasRecentMissingLinks = recentMissingEdges.length > 0;
  const passiveHintEdges = useMemo(
    () => edges.filter((edge) => edge.evidence_class === "passive_derived_association"),
    [edges],
  );
  const hasPassiveHints = passiveHintEdges.length > 0;
  const hasLastKnownLinks = useMemo(
    () => edges.some((edge) => edge.evidence_class === "last_known_link"),
    [edges],
  );

  const recentMissingEdgeIds = useMemo(() => {
    const issueDeviceIds = collectIssueDeviceIds(devices);
    const devicesWithLatestNeighbourEvidence = new Set<string>();
    for (const edge of edges) {
      if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
      devicesWithLatestNeighbourEvidence.add(edge.source);
      devicesWithLatestNeighbourEvidence.add(edge.target);
    }
    const latestLayoutLimited = recentMissingEdges.some(
      (edge) => edge.latest_layout_limited === true,
    );
    return selectRecentMissingEdges(edges, {
      issueDeviceIds,
      devicesWithLatestNeighbourEvidence,
      latestLayoutLimited,
    });
  }, [devices, edges, recentMissingEdges]);

  const passiveHintEdgeIds = useMemo(
    () =>
      selectPassiveHintEdges(edges, {
        issueDeviceIds: collectIssueDeviceIds(devices),
        selectedNodeId,
      }),
    [edges, devices, selectedNodeId],
  );

  const visibleEdges = useMemo(
    () =>
      selectVisibleConnectionEdges(edges, controls, {
        bestNeighbourEdgeIds,
        recentMissingEdgeIds,
        passiveHintEdgeIds,
        selectedNodeId,
        selectedEdge,
      }),
    [
      edges,
      controls,
      bestNeighbourEdgeIds,
      recentMissingEdgeIds,
      passiveHintEdgeIds,
      selectedNodeId,
      selectedEdge,
    ],
  );

  const setControl = (key: keyof ConnectionControls) => (value: boolean) =>
    setControls((current) => {
      const next = { ...current, [key]: value };
      saveConnectionControls(positionStorageId, next);
      return next;
    });

  const resetConnectionChoices = () => {
    clearConnectionControls(positionStorageId);
    setControls({ ...DEFAULT_CONNECTION_CONTROLS });
  };

  return {
    controls,
    visibleEdges,
    hasOldUncertainLinks,
    hasRouteHints,
    hasRecentMissingLinks,
    hasPassiveHints,
    hasLastKnownLinks,
    setControl,
    resetConnectionChoices,
  };
}
