import { useMemo, useState } from "react";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  clearConnectionControls,
  collectIssueDeviceIds,
  collectRouteCoveredPairs,
  saveConnectionControls,
  selectAdaptiveBestNeighbourLinks,
  selectPassiveHintEdges,
  selectRecentMissingEdges,
  selectVisibleConnectionEdges,
  type ConnectionControls,
} from "@/lib/meshGraphDense";
import {
  type GraphViewPresetId,
  type NamedGraphViewPresetId,
  GRAPH_VIEW_PRESET_CONTROLS,
  clearViewPreset,
  controlsMatchPreset,
  derivePresetFromControls,
  isNamedGraphViewPresetId,
  loadInitialGraphViewState,
  resetGraphViewToDefaultPreset,
  saveViewPreset,
} from "@/lib/meshGraphPresets";

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
  const [initial] = useState(() => loadInitialGraphViewState(positionStorageId));
  const [controls, setControls] = useState<ConnectionControls>(initial.controls);
  const [activePreset, setActivePreset] = useState<GraphViewPresetId>(initial.preset);

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

  const persistControls = (next: ConnectionControls, preset: GraphViewPresetId) => {
    saveConnectionControls(positionStorageId, next);
    saveViewPreset(positionStorageId, preset);
  };

  const setControl = (key: keyof ConnectionControls) => (value: boolean) =>
    setControls((current) => {
      const next = { ...current, [key]: value };
      const preset = derivePresetFromControls(next);
      persistControls(next, preset);
      setActivePreset(preset);
      return next;
    });

  const setPreset = (preset: GraphViewPresetId) => {
    if (preset === "custom") return;
    const next = { ...GRAPH_VIEW_PRESET_CONTROLS[preset as NamedGraphViewPresetId] };
    setControls(next);
    setActivePreset(preset);
    persistControls(next, preset);
  };

  const resetConnectionChoices = () => {
    clearConnectionControls(positionStorageId);
    clearViewPreset(positionStorageId);
    const { controls: next, preset } = resetGraphViewToDefaultPreset();
    setControls(next);
    setActivePreset(preset);
    persistControls(next, preset);
  };

  const presetMatchesControls = useMemo(() => {
    if (!isNamedGraphViewPresetId(activePreset)) return false;
    return controlsMatchPreset(controls, activePreset);
  }, [activePreset, controls]);

  return {
    controls,
    visibleEdges,
    hasOldUncertainLinks,
    hasRouteHints,
    hasRecentMissingLinks,
    hasPassiveHints,
    hasLastKnownLinks,
    activePreset,
    presetMatchesControls,
    setControl,
    setPreset,
    resetConnectionChoices,
  };
}
