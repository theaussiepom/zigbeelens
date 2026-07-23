import { useMemo } from "react";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { buildLiveMeshEvidence } from "@/lib/meshEvidenceLive";
import { HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT } from "@/lib/events";

/** Factual device-inventory invalidations; excludes topology_updated. */
const DEVICE_INVENTORY_EVENTS = [
  "device_health_updated",
  "health_updated",
  "dashboard_updated",
  "incidents_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

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
      // Explicit topology history invalidation; do not rely on default-all-events.
      refetchOn: ["topology_updated", HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    },
  );
  const inventory = useLiveResource(
    () => api.devices(scenario || undefined, networkId),
    [networkId, scenario],
    {
      enabled: Boolean(networkId),
      refetchOn: [...DEVICE_INVENTORY_EVENTS],
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
