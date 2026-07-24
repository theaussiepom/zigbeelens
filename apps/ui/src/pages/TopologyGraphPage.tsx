import { Link, useParams } from "react-router-dom";
import {
  Badge,
  Card,
  ErrorState,
  LoadingState,
  MetricPill,
  StaleRefreshNotice,
} from "@/components/ui";
import { GraphPanel } from "@/components/meshGraph/GraphPanel";
import { EvidenceCoverageStrip } from "@/components/meshGraph/EvidenceCoverageStrip";
import { TopologyMetricStrip } from "@/components/meshGraph/TopologyMetricStrip";
import { EdgeDrawer } from "@/components/meshGraph/EdgeDrawer";
import { NodeDrawer } from "@/components/meshGraph/NodeDrawer";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";
import { useGraphSelection } from "@/hooks/useGraphSelection";
import { useTopologyGraphData } from "@/hooks/useTopologyGraphData";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import { topologySnapshotPath } from "@/lib/routes";
import { GRAPH_SAFETY_COPY_LIVE, EVIDENCE_COVERAGE_STRIP_TITLE } from "@/lib/meshGraphCopy";
import { buildEvidenceCoverageStripViewModel } from "@/viewModels/coverage/coverageStripViewModel";
import {
  buildConnectionHistoryPresentationViewModel,
} from "@/viewModels/topology/connectionHistoryPresentationViewModel";

const LIMITED_LAYOUT_COPY =
  "Topology snapshot was captured, but Zigbee2MQTT did not provide usable node/link layout data. Device health still comes from passive MQTT inventory and state updates.";

export function TopologyGraphPage() {
  const { networkId } = useParams<{ networkId?: string }>();
  const {
    detail,
    inventory,
    liveEvidence,
    snapshot,
    layoutAvailable,
    topologyEnabled,
    liveSignatureSeed,
    graphDetail,
  } = useTopologyGraphData(networkId);
  const {
    selectedEdge,
    selectedDevice,
    selectedNodeId,
    selectEdge,
    selectNode,
    clearSelection,
    clearEdge,
    clearNode,
  } = useGraphSelection(networkId, liveEvidence);

  const networkCoverageStrip = buildEvidenceCoverageStripViewModel(
    graphDetail?.topology_facts?.coverage ?? [],
  );
  const historyPresentation = graphDetail
    ? buildConnectionHistoryPresentationViewModel(graphDetail)
    : null;

  return (
    <div
      className="max-w-7xl space-y-6"
      aria-busy={Boolean(detail.refreshing || inventory.refreshing)}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mesh / Investigate</h1>
          <p className="mt-1 text-zl-muted">
            Evidence graph for network{" "}
            <span className="font-mono">{networkId ?? "—"}</span>
            {detail.data?.network_name ? ` (${detail.data.network_name})` : ""}. Topology links are
            evidence from the latest snapshot, not proof of current routing.
          </p>
        </div>
        <span
          data-testid="graph-mode-badge"
          className="inline-flex items-center gap-1.5 rounded-full border border-zl-healthy/40 bg-zl-healthy/10 px-3 py-1 text-xs font-medium text-zl-healthy"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-zl-healthy" aria-hidden="true" />
          Live topology snapshot
        </span>
      </header>

      {networkId && <TopologyViewTabs networkId={networkId} />}

      <div
        role="note"
        aria-label="Evidence safety note"
        className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-3 text-sm leading-relaxed text-zl-text"
      >
        {GRAPH_SAFETY_COPY_LIVE}
      </div>

      {detail.data && detail.error && (
        <StaleRefreshNotice
          resourceLabel="Mesh evidence graph"
          onRetry={detail.refetch}
          retryLabel="Retry Mesh evidence graph"
        />
      )}

      {detail.data && inventory.data === null && (
        <MeshInventoryWarning
          message={
            inventory.loading
              ? "Device inventory is still loading. Showing topology evidence without inventory confirmation."
              : "Device inventory is unavailable. Showing topology evidence without inventory confirmation."
          }
          onRetry={inventory.error ? inventory.refetch : undefined}
        />
      )}

      {detail.data && inventory.data !== null && inventory.error && (
        <StaleRefreshNotice
          resourceLabel="Mesh device inventory"
          onRetry={inventory.refetch}
          retryLabel="Retry device inventory"
        />
      )}

      {!networkId ? (
        <Card title="No network selected">
          <p className="text-sm text-zl-muted">
            Choose a network from{" "}
            <Link to="/investigate" className="text-zl-accent">
              Mesh / Investigate
            </Link>{" "}
            to open its evidence graph.
          </p>
        </Card>
      ) : !topologyEnabled ? (
        <Card title="Topology disabled">
          <p className="text-sm text-zl-muted">
            Topology capture is disabled in configuration, so no live snapshot evidence is
            available.
          </p>
        </Card>
      ) : (detail.loading && !detail.data) || (inventory.loading && !detail.data) ? (
        <LoadingState />
      ) : detail.error && !detail.data ? (
        <ErrorState
          message={detail.error}
          onRetry={detail.refetch}
          retryLabel="Retry Mesh evidence graph"
        />
      ) : !snapshot ? (
        <Card title="Waiting for a topology snapshot">
          <div className="space-y-3 text-sm text-zl-muted">
            <Badge severity="watch">diagnostics limited</Badge>
            <p>
              No topology snapshot has been captured for this network yet. After startup,
              ZigbeeLens requests one network map per network once MQTT and the bridge are
              ready, then relies on passive updates.
            </p>
            <p>
              Missing topology data is not an incident by itself — it only limits mesh
              enrichment. Device health still comes from passive MQTT inventory and state
              updates.
            </p>
            <p>
              <Link to={topologySnapshotPath(networkId)} className="text-zl-accent">
                Raw snapshot
              </Link>{" "}
              ·{" "}
              <Link to="/devices" className="text-zl-accent">
                Open devices
              </Link>
            </p>
          </div>
        </Card>
      ) : !layoutAvailable ? (
        <Card
          title="Topology layout limited"
          subtitle={
            snapshot.captured_at
              ? `Latest snapshot captured ${relativeTime(snapshot.captured_at)}`
              : undefined
          }
        >
          <div className="space-y-3 text-sm">
            <p className="border-l-2 border-zl-watch/40 pl-3 text-zl-muted">
              {LIMITED_LAYOUT_COPY}
            </p>
            <div className="flex flex-wrap gap-2">
              <MetricPill label="Snapshot status" value={topologyStatusLabel(snapshot.status)} />
              <MetricPill label="Observed topology nodes" value="—" />
              <MetricPill label="Observed topology links" value="—" />
              {detail.data?.inventory && (
                <>
                  <MetricPill label="Known devices" value={detail.data.inventory.device_count} />
                  <MetricPill label="Known routers" value={detail.data.inventory.router_count} />
                  <MetricPill
                    label="Known end devices"
                    value={detail.data.inventory.end_device_count}
                  />
                </>
              )}
            </div>
            <p className="text-zl-muted">
              Missing topology data is not an incident by itself.{" "}
              <Link to={topologySnapshotPath(networkId)} className="text-zl-accent">
                Raw snapshot
              </Link>{" "}
              ·{" "}
              <Link to="/devices" className="text-zl-accent">
                Open devices
              </Link>
            </p>
          </div>
        </Card>
      ) : graphDetail && liveEvidence && snapshot && historyPresentation ? (
        <>
          <TopologyMetricStrip
            graphDetail={graphDetail}
            snapshot={snapshot}
            liveEdgeCount={liveEvidence.edges.filter((edge) => edge.in_latest_snapshot).length}
          />
          <EvidenceCoverageStrip
            title={EVIDENCE_COVERAGE_STRIP_TITLE}
            items={networkCoverageStrip.items}
          />
          <GraphPanel
            // Remount per network so persisted connection choices and
            // layout state are restored for the network being viewed.
            key={networkId ?? "unknown-network"}
            devices={liveEvidence.devices}
            edges={liveEvidence.edges}
            investigations={detail.data?.investigations ?? []}
            signatureSeed={liveSignatureSeed}
            networkId={networkId ?? "unknown-network"}
            networkName={detail.data?.network_name ?? null}
            positionStorageId={networkId ?? "unknown-network"}
            onSelectEdge={selectEdge}
            onSelectNode={selectNode}
            onClearSelection={clearSelection}
            selectedNodeId={selectedNodeId}
            selectedEdge={selectedEdge}
            historyPresentation={historyPresentation}
          />
        </>
      ) : null}

      {selectedEdge && (
        <EdgeDrawer
          edge={selectedEdge}
          devices={liveEvidence?.devices ?? []}
          onClose={clearEdge}
        />
      )}
      {selectedDevice && (
        <NodeDrawer device={selectedDevice} onClose={clearNode} />
      )}
    </div>
  );
}

function MeshInventoryWarning({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="status"
      className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-3 py-2 text-sm text-zl-watch"
    >
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          aria-label="Retry device inventory"
          onClick={onRetry}
          className="mt-2 min-h-11 rounded-lg border border-zl-border px-3 py-1.5 text-sm text-zl-text hover:bg-zl-surface-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}
