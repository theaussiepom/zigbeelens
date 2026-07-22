import { MetricPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import type { TopologyEvidenceGraphDetail } from "@/types/topology";

export function TopologyMetricStrip({
  graphDetail,
  snapshot,
  liveEdgeCount,
}: {
  graphDetail: TopologyEvidenceGraphDetail;
  snapshot: NonNullable<TopologyEvidenceGraphDetail["latest_snapshot"]>;
  liveEdgeCount: number;
}) {
  const historyAvailable = graphDetail.history_window.snapshots_considered > 0;
  const recentMissingLinkCount =
    graphDetail.counts.historical_neighbor_edges + graphDetail.counts.historical_route_edges;

  return (
    <div className="flex flex-wrap gap-2">
      <MetricPill label="Network" value={graphDetail.network_name} />
      {snapshot.captured_at && (
        <MetricPill label="Captured" value={relativeTime(snapshot.captured_at)} />
      )}
      <MetricPill label="Snapshot status" value={topologyStatusLabel(snapshot.status)} />
      <MetricPill
        label="Observed topology nodes"
        value={graphDetail.nodes.length}
        description="Devices present in the latest parsed topology snapshot."
      />
      <MetricPill
        label="Snapshot evidence links"
        value={liveEdgeCount}
        description="Links reported in the latest topology snapshot."
      />
      <MetricPill
        label="Recent missing links"
        value={historyAvailable ? recentMissingLinkCount : "—"}
        description={
          historyAvailable
            ? "Links seen in recent previous snapshots but not present in the latest usable snapshot."
            : "History unavailable because no previous snapshots were considered."
        }
      />
      {graphDetail.inventory && (
        <MetricPill
          label="Known devices"
          value={graphDetail.inventory.device_count}
          description="Devices ZigbeeLens knows from Zigbee2MQTT inventory."
        />
      )}
    </div>
  );
}
