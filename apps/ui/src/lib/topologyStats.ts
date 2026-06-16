import type {
  TopologyLinkRow,
  TopologyNodeRow,
  TopologySnapshotSummary,
} from "@/lib/api";

export const TOPOLOGY_LIMITED_VALUE = "—";

export type TopologyMetricValue = number | typeof TOPOLOGY_LIMITED_VALUE;

export interface TopologyDisplayCounts {
  layoutAvailable: boolean;
  routers: TopologyMetricValue;
  endDevices: TopologyMetricValue;
  links: TopologyMetricValue;
}

export interface TopologyInventoryCounts {
  device_count: number;
  router_count: number;
  end_device_count: number;
}

export function topologyLayoutAvailable(
  nodes: TopologyNodeRow[],
  links: TopologyLinkRow[],
): boolean {
  return nodes.length > 0 || links.length > 0;
}

export function resolveTopologyDisplayCounts(
  snapshot: TopologySnapshotSummary | null | undefined,
  nodes: TopologyNodeRow[],
  links: TopologyLinkRow[],
): TopologyDisplayCounts {
  const layoutAvailable = topologyLayoutAvailable(nodes, links);
  if (!layoutAvailable) {
    return {
      layoutAvailable: false,
      routers: TOPOLOGY_LIMITED_VALUE,
      endDevices: TOPOLOGY_LIMITED_VALUE,
      links: TOPOLOGY_LIMITED_VALUE,
    };
  }

  const routersFromNodes = nodes.filter((node) => {
    const type = (node.node_type ?? "").toLowerCase();
    return type === "router" || type === "coordinator";
  }).length;
  const endDevicesFromNodes = nodes.filter((node) =>
    (node.node_type ?? "").toLowerCase().includes("end"),
  ).length;

  return {
    layoutAvailable: true,
    routers: snapshot?.router_count ?? routersFromNodes,
    endDevices: snapshot?.end_device_count ?? endDevicesFromNodes,
    links: snapshot?.link_count ?? links.length,
  };
}

export function snapshotSummaryLooksLimited(snapshot: {
  router_count?: number | null;
  end_device_count?: number | null;
  link_count?: number | null;
  status?: string | null;
}): boolean {
  if (snapshot.status !== "complete") return false;
  return (
    (snapshot.router_count ?? 0) === 0 &&
    (snapshot.end_device_count ?? 0) === 0 &&
    (snapshot.link_count ?? 0) === 0
  );
}
