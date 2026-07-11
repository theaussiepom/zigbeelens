import { MetricPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import type { TopologyEvidenceGraphDetail } from "@/types/topology";

export function TopologyMetricStrip({
  networkId,
  graphDetail,
  snapshot,
  liveEdgeCount,
}: {
  networkId: string;
  graphDetail: TopologyEvidenceGraphDetail | null;
  snapshot: NonNullable<TopologyEvidenceGraphDetail["latest_snapshot"]>;
  liveEdgeCount: number;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <MetricPill label="Network" value={graphDetail?.network_name ?? networkId} />
      {snapshot.captured_at && (
        <MetricPill label="Captured" value={relativeTime(snapshot.captured_at)} />
      )}
      <MetricPill label="Snapshot status" value={topologyStatusLabel(snapshot.status)} />
      <MetricPill
        label="Observed topology nodes"
        value={graphDetail?.nodes?.length ?? 0}
        description="Devices present in the latest parsed topology snapshot."
      />
      <MetricPill
        label="Snapshot evidence links"
        value={liveEdgeCount}
        description="Links reported in the latest topology snapshot."
      />
      {graphDetail?.counts && (
        <MetricPill
          label="Recent missing links"
          value={
            graphDetail.counts.historical_neighbor_edges +
            graphDetail.counts.historical_route_edges
          }
          description="Links seen in recent previous snapshots but not present in the latest usable snapshot."
        />
      )}
      {graphDetail?.inventory && (
        <MetricPill
          label="Known devices"
          value={graphDetail.inventory.device_count}
          description="Devices ZigbeeLens knows from Zigbee2MQTT inventory."
        />
      )}
    </div>
  );
}
