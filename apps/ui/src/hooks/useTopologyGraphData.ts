import { useMemo } from "react";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { buildLiveMeshEvidence } from "@/lib/meshEvidenceLive";
import {
  EVIDENCE_GRAPH_EVENTS,
  MESH_INVENTORY_EVENTS,
} from "@/lib/liveResourceEvents";

export function useTopologyGraphData(networkId: string | undefined) {
  const { status, scenario } = useScenario();

  const detail = useLiveResource(
    () =>
      networkId
        ? api.topologyEvidenceGraph(networkId)
        : Promise.reject(new Error("No network selected")),
    [networkId],
    {
      enabled: Boolean(networkId),
      refetchOn: EVIDENCE_GRAPH_EVENTS,
    },
  );
  const inventory = useLiveResource(
    () => api.devices(scenario || undefined, networkId),
    [networkId, scenario],
    {
      enabled: Boolean(networkId),
      refetchOn: MESH_INVENTORY_EVENTS,
    },
  );

  const liveEvidence = useMemo(() => {
    if (!detail.data) return null;
    return buildLiveMeshEvidence(detail.data, inventory.data?.items ?? null);
  }, [detail.data, inventory.data]);

  const snapshot = detail.data?.latest_snapshot;
  const layoutAvailable = detail.data
    ? Boolean(
        detail.data.layout_available ??
          (detail.data.nodes.length > 0 || detail.data.links.length > 0),
      )
    : false;
  const topologyEnabled = status?.topology?.enabled ?? true;

  // Stable data identity for layout caching: network + snapshot only.
  const liveSignatureSeed = `live|${networkId ?? "none"}|${
    snapshot?.snapshot_id ?? snapshot?.captured_at ?? "no-snapshot"
  }`;

  return {
    detail,
    inventory,
    liveEvidence,
    snapshot,
    layoutAvailable,
    topologyEnabled,
    liveSignatureSeed,
    graphDetail: detail.data,
  };
}
