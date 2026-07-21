import { useState } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api, type TopologyNetworkDetail, type TopologyOverview } from "@/lib/api";
import { Badge, Card, EmptyState, ErrorState, LoadingState, MetricPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import { RAW_SNAPSHOT_REFRESH_FAILED_COPY } from "@/lib/meshGraphCopy";
import { topologyRequestedByLabel } from "@/lib/topologyLabels";
import { TopologyViewTabs } from "@/components/meshGraph/TopologyViewTabs";
import { topologySnapshotPath } from "@/lib/routes";
import { buildTopologyLandingSnapshotViewModel } from "@/viewModels/topology/topologyLandingSnapshotViewModel";
import {
  buildTopologyRawDetailSnapshotViewModel,
} from "@/viewModels/topology/topologyRawDetailSnapshotViewModel";

const CAPTURE_WARNING =
  "Capturing a Zigbee network map asks Zigbee2MQTT to scan the mesh. On larger networks this may temporarily make Zigbee less responsive. ZigbeeLens will not change Zigbee state, but this diagnostic request can create temporary network load.";

const LIMITED_LAYOUT_COPY =
  "Topology snapshot was captured, but Zigbee2MQTT did not provide usable node/link layout data. Device health still comes from passive MQTT inventory and state updates.";

const POINT_IN_TIME_LIMITATION =
  "This is point-in-time snapshot evidence. It does not prove a live route, current parentage, or that a link failed.";

const CAPTURE_DISABLED_NOTICE =
  "Topology capture is disabled in configuration. Retained snapshots remain readable as support evidence.";

const NO_SNAPSHOT_COPY =
  "No topology snapshot is stored for this network. Missing topology data is not an incident by itself — it only limits mesh enrichment for incident context.";

function CaptureModal({
  networkId,
  capturing,
  error,
  onCancel,
  onConfirm,
}: {
  networkId: string;
  capturing: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (networkId: string) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-w-lg rounded-xl border border-zl-border bg-zl-surface p-6 shadow-xl">
        <h2 className="text-lg font-semibold">Capture topology snapshot?</h2>
        <p className="mt-3 text-sm leading-relaxed text-zl-muted">{CAPTURE_WARNING}</p>
        {error && <p className="mt-3 text-sm text-zl-critical">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-zl-border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={capturing}
            onClick={() => onConfirm(networkId)}
            className="rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {capturing ? "Capturing…" : "Capture topology snapshot"}
          </button>
        </div>
      </div>
    </div>
  );
}

function NetworkSnapshotNav({
  networks,
  activeId,
}: {
  networks: Array<{ network_id: string; network_name: string }>;
  activeId: string;
}) {
  return (
    <nav aria-label="Topology snapshot networks" className="flex flex-wrap gap-2">
      {networks.map((network) => (
        <NavLink
          key={network.network_id}
          to={topologySnapshotPath(network.network_id)}
          aria-current={network.network_id === activeId ? "page" : undefined}
          className={({ isActive }) =>
            `rounded-lg border px-4 py-2 text-sm font-medium transition-colors min-h-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50 ${
              isActive
                ? "border-zl-accent/40 bg-zl-accent/15 text-zl-accent"
                : "border-zl-border text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
            }`
          }
        >
          {network.network_name}
        </NavLink>
      ))}
    </nav>
  );
}

function DetailRefreshWarning({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      data-testid="raw-snapshot-refresh-warning"
      className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-4 py-3 text-sm text-zl-watch"
    >
      <p>{RAW_SNAPSHOT_REFRESH_FAILED_COPY}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 min-h-11 font-medium text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
      >
        Retry
      </button>
    </div>
  );
}

function TopologyNetworkDetailView({ detail }: { detail: TopologyNetworkDetail }) {
  const snapshot = detail.latest_snapshot;
  const nodes = detail.nodes ?? [];
  const links = detail.links ?? [];
  const inventory = detail.inventory;
  const presentation = buildTopologyRawDetailSnapshotViewModel(snapshot, nodes, links);

  if (presentation.kind === "no_snapshot") {
    return (
      <Card title="Diagnostics limited">
        <div className="space-y-3 text-sm text-zl-muted">
          <Badge severity="watch">{presentation.label}</Badge>
          <p>{NO_SNAPSHOT_COPY}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card
        title={`${detail.network_name} snapshot`}
        subtitle={snapshot?.captured_at ? `Captured ${relativeTime(snapshot.captured_at)}` : undefined}
        actions={<Badge severity={presentation.severity}>{presentation.label}</Badge>}
      >
        <div className="flex flex-wrap gap-2">
          {presentation.showTopologyCounts && (
            <>
              <MetricPill label="Topology routers" value={presentation.counts.routers} />
              <MetricPill label="Topology end devices" value={presentation.counts.endDevices} />
              <MetricPill label="Topology links" value={presentation.counts.links} />
            </>
          )}
          {inventory && (
            <>
              <MetricPill label="Known devices" value={inventory.device_count} />
              <MetricPill label="Known routers" value={inventory.router_count} />
              <MetricPill label="Known end devices" value={inventory.end_device_count} />
            </>
          )}
          {snapshot?.requested_by && (
            <MetricPill
              label="Requested by"
              value={topologyRequestedByLabel(snapshot.requested_by)}
            />
          )}
        </div>
        {presentation.statusCopy && (
          <p
            className={`mt-3 text-sm ${
              presentation.severity === "critical" ? "text-zl-critical" : "text-zl-muted"
            }`}
            data-testid="raw-detail-status-copy"
          >
            {presentation.statusCopy}
          </p>
        )}
        {presentation.showLimitedLayoutCopy && (
          <p className="mt-3 border-l-2 border-zl-watch/40 pl-3 text-sm text-zl-muted">
            {LIMITED_LAYOUT_COPY}
          </p>
        )}
        {presentation.showPointInTimeLimitation && (
          <p className="mt-3 text-sm text-zl-muted">{POINT_IN_TIME_LIMITATION}</p>
        )}
      </Card>

      {presentation.showRawContents ? (
        <details className="rounded-xl border border-zl-border bg-zl-surface p-5">
          <summary className="cursor-pointer text-sm font-semibold text-zl-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50">
            Raw snapshot contents
          </summary>
          <div className="mt-4 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-zl-text">
                Nodes
                <span className="ml-2 font-normal text-zl-muted">
                  {nodes.length} in latest snapshot
                </span>
              </h3>
              {nodes.length === 0 ? (
                <p className="mt-2 text-sm text-zl-muted">No nodes recorded in this snapshot.</p>
              ) : (
                <ul className="mt-2 divide-y divide-zl-border text-sm">
                  {nodes.slice(0, 50).map((node) => (
                    <li
                      key={node.ieee_address}
                      className="flex flex-wrap items-center justify-between gap-2 py-2"
                    >
                      <div className="min-w-0">
                        <div className="font-medium text-zl-text">
                          {node.friendly_name || node.ieee_address}
                        </div>
                        <div className="font-mono text-xs text-zl-muted">{node.ieee_address}</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {node.node_type && <Badge severity="healthy">{node.node_type}</Badge>}
                        {node.lqi != null && <MetricPill label="LQI" value={node.lqi} />}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {nodes.length > 50 && (
                <p className="mt-3 text-xs text-zl-muted">
                  Showing first 50 of {nodes.length} nodes.
                </p>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-zl-text">
                Links
                <span className="ml-2 font-normal text-zl-muted">
                  {links.length} in latest snapshot
                </span>
              </h3>
              {links.length === 0 ? (
                <p className="mt-2 text-sm text-zl-muted">No links recorded in this snapshot.</p>
              ) : (
                <ul className="mt-2 divide-y divide-zl-border text-sm">
                  {links.slice(0, 50).map((link, idx) => (
                    <li key={`${link.source_ieee}-${link.target_ieee}-${idx}`} className="py-2">
                      <div className="break-all font-mono text-xs text-zl-text">
                        {link.source_ieee} → {link.target_ieee}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-zl-muted">
                        {link.relationship && <span>{link.relationship}</span>}
                        {link.linkquality != null && <span>LQI {link.linkquality}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {links.length > 50 && (
                <p className="mt-3 text-xs text-zl-muted">
                  Showing first 50 of {links.length} links.
                </p>
              )}
            </div>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function TopologyLanding({
  topology,
  enabled,
  captureAllowed,
  onCapture,
}: {
  topology: TopologyOverview;
  enabled: boolean;
  captureAllowed: boolean;
  onCapture: (networkId: string) => void;
}) {
  const networks = topology.networks;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Topology snapshots</h1>
        <p className="mt-1 text-zl-muted">
          Advanced &amp; support view for point-in-time mesh snapshots and capture status. Device
          snapshot comparison lives on Device Detail. For investigation, use Mesh / Investigate.
        </p>
      </div>

      {!enabled && (
        <Card title="Topology capture disabled">
          <p className="text-sm text-zl-muted">{CAPTURE_DISABLED_NOTICE}</p>
        </Card>
      )}

      {topology.capture_in_progress && (
        <div className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-4 py-3 text-sm text-zl-watch">
          Topology capture in progress…
        </div>
      )}

      {topology.last_capture_error && (
        <div className="rounded-lg border border-zl-critical/40 bg-zl-critical/10 px-4 py-3 text-sm text-zl-critical">
          Last capture error: {topology.last_capture_error}
        </div>
      )}

      {networks.length === 0 && (
        <EmptyState title="No networks configured" detail="Add networks in configuration first." />
      )}

      {networks.length > 0 && (
        <Card title="Configured networks">
          <ul className="space-y-3 text-sm">
            {networks.map((network) => {
              const presentation = buildTopologyLandingSnapshotViewModel(network.latest_snapshot);
              return (
                <li key={network.network_id} className="flex flex-wrap items-stretch gap-2">
                  <Link
                    to={topologySnapshotPath(network.network_id)}
                    className="flex min-h-11 flex-1 flex-wrap items-center justify-between gap-3 rounded-lg border border-zl-border px-3 py-3 transition-colors hover:border-zl-accent/30 hover:bg-zl-surface-2/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
                  >
                    <div>
                      <div className="font-medium">{network.network_name}</div>
                      <div className="text-xs text-zl-muted">{presentation.summaryText}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge severity={presentation.severity}>{presentation.label}</Badge>
                      <span className="text-sm text-zl-accent">View snapshot details →</span>
                    </div>
                  </Link>
                  {captureAllowed && (
                    <button
                      type="button"
                      onClick={() => onCapture(network.network_id)}
                      className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
                    >
                      Capture snapshot
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}

function TopologyNetworkDetailPage({
  networkId,
  topology,
  enabled,
  captureAllowed,
  onCapture,
}: {
  networkId: string;
  topology: TopologyOverview;
  enabled: boolean;
  captureAllowed: boolean;
  onCapture: (networkId: string) => void;
}) {
  const networks = topology.networks;
  const known = networks.some((n) => n.network_id === networkId);
  const detail = useLiveResource(
    () => api.topologyNetwork(networkId),
    [networkId],
    { refetchOn: ["topology_updated"], enabled: known },
  );

  if (!known) {
    return (
      <div className="max-w-5xl space-y-6">
        <Link to="/topology" className="text-sm text-zl-accent hover:underline">
          ← Topology snapshots
        </Link>
        <ErrorState message={`Network “${networkId}” was not found.`} />
      </div>
    );
  }

  const refreshFailed = Boolean(detail.data && detail.error);

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link to="/topology" className="text-sm text-zl-accent hover:underline">
          ← Topology snapshots
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Raw snapshot</h1>
        <p className="mt-1 text-zl-muted">
          Point-in-time stored topology evidence for this network.
        </p>
      </div>

      {!enabled && (
        <Card title="Topology capture disabled">
          <p className="text-sm text-zl-muted">{CAPTURE_DISABLED_NOTICE}</p>
        </Card>
      )}

      <NetworkSnapshotNav networks={networks} activeId={networkId} />
      <TopologyViewTabs networkId={networkId} />

      {topology.capture_in_progress && (
        <div className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-4 py-3 text-sm text-zl-watch">
          Topology capture in progress…
        </div>
      )}

      {topology.last_capture_error && (
        <div className="rounded-lg border border-zl-critical/40 bg-zl-critical/10 px-4 py-3 text-sm text-zl-critical">
          Last capture error: {topology.last_capture_error}
        </div>
      )}

      {captureAllowed && (
        <button
          type="button"
          onClick={() => onCapture(networkId)}
          className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        >
          Capture snapshot
        </button>
      )}

      {refreshFailed && <DetailRefreshWarning onRetry={detail.refetch} />}

      {detail.loading && !detail.data ? (
        <LoadingState />
      ) : !detail.data && detail.error ? (
        <ErrorState message={detail.error} onRetry={detail.refetch} />
      ) : detail.data ? (
        <TopologyNetworkDetailView detail={detail.data} />
      ) : null}
    </div>
  );
}

export function TopologyPage() {
  const { status } = useScenario();
  const { networkId: routeNetworkId } = useParams<{ networkId?: string }>();
  // React Router already decodes path params — use the logical ID once.
  const networkId = routeNetworkId || undefined;
  const overview = useLiveResource(() => api.topology(), [], {
    refetchOn: ["topology_updated"],
  });
  const [modalNetwork, setModalNetwork] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status || (overview.loading && !overview.data)) return <LoadingState />;
  if (overview.error && !overview.data) {
    return <ErrorState message={overview.error} onRetry={overview.refetch} />;
  }

  const topology = overview.data;
  if (!topology) return <LoadingState />;
  const enabled = topology.enabled ?? status.topology?.enabled ?? false;
  const captureAllowed = enabled && topology.manual_capture_enabled;

  function requestCapture(targetNetworkId: string) {
    if (!captureAllowed) return;
    setModalNetwork(targetNetworkId);
  }

  async function confirmCapture(targetNetworkId: string) {
    if (!captureAllowed) {
      setModalNetwork(null);
      return;
    }
    setCapturing(true);
    setError(null);
    try {
      await api.captureTopology(targetNetworkId);
      setModalNetwork(null);
      await overview.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Capture failed");
    } finally {
      setCapturing(false);
    }
  }

  return (
    <>
      {networkId ? (
        <TopologyNetworkDetailPage
          networkId={networkId}
          topology={topology}
          enabled={enabled}
          captureAllowed={captureAllowed}
          onCapture={requestCapture}
        />
      ) : (
        <TopologyLanding
          topology={topology}
          enabled={enabled}
          captureAllowed={captureAllowed}
          onCapture={requestCapture}
        />
      )}

      {modalNetwork && captureAllowed && (
        <CaptureModal
          networkId={modalNetwork}
          capturing={capturing}
          error={error}
          onCancel={() => setModalNetwork(null)}
          onConfirm={confirmCapture}
        />
      )}
    </>
  );
}

export { LIMITED_LAYOUT_COPY, POINT_IN_TIME_LIMITATION, CAPTURE_DISABLED_NOTICE, NO_SNAPSHOT_COPY };
