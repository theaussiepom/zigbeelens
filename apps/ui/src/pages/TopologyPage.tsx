import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api, type TopologyNetworkDetail } from "@/lib/api";
import { Badge, Card, EmptyState, ErrorState, LoadingState, MetricPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";

const CAPTURE_WARNING =
  "Capturing a Zigbee network map asks Zigbee2MQTT to scan the mesh. On larger networks this may temporarily make Zigbee less responsive. ZigbeeLens will not change Zigbee state, but this diagnostic request can create temporary network load.";

function NetworkTabs({
  networks,
  activeId,
}: {
  networks: Array<{ network_id: string; network_name: string }>;
  activeId: string;
}) {
  return (
    <div
      className="flex flex-wrap gap-2"
      role="tablist"
      aria-label="Topology networks"
    >
      {networks.map((network) => (
        <NavLink
          key={network.network_id}
          to={`/topology/${network.network_id}`}
          role="tab"
          aria-selected={network.network_id === activeId}
          className={({ isActive }) =>
            `rounded-lg border px-4 py-2 text-sm font-medium transition-colors min-h-11 ${
              isActive
                ? "border-zl-accent/40 bg-zl-accent/15 text-zl-accent"
                : "border-zl-border text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
            }`
          }
        >
          {network.network_name}
        </NavLink>
      ))}
    </div>
  );
}

function MissingSnapshotState() {
  return (
    <Card title="Diagnostics limited">
      <div className="space-y-3 text-sm text-zl-muted">
        <Badge severity="watch">diagnostics limited</Badge>
        <p>
          Waiting for a topology snapshot. After startup, ZigbeeLens requests one network map per
          network once MQTT and the bridge are ready, then relies on passive updates.
        </p>
        <p>
          Missing topology data is not an incident by itself — it only limits mesh enrichment for
          router risk and incident context.
        </p>
      </div>
    </Card>
  );
}

function TopologyNetworkDetailView({ detail }: { detail: TopologyNetworkDetail }) {
  const snapshot = detail.latest_snapshot;
  const nodes = detail.nodes ?? [];
  const links = detail.links ?? [];

  if (!snapshot) {
    return <MissingSnapshotState />;
  }

  const routerCount = snapshot.router_count ?? nodes.filter((n) => n.node_type === "Router").length;
  const endDeviceCount =
    snapshot.end_device_count ?? nodes.filter((n) => n.node_type === "EndDevice").length;
  const linkCount = snapshot.link_count ?? links.length;
  const hasLayout = nodes.length > 0 || links.length > 0;

  return (
    <div className="space-y-4">
      <Card
        title={`${detail.network_name} snapshot`}
        subtitle={snapshot.captured_at ? `Captured ${relativeTime(snapshot.captured_at)}` : undefined}
        actions={
          snapshot.status === "complete" ? (
            <Badge severity="healthy">complete</Badge>
          ) : (
            <Badge severity="watch">{snapshot.status ?? "pending"}</Badge>
          )
        }
      >
        <div className="flex flex-wrap gap-2">
          <MetricPill label="Routers" value={routerCount} />
          <MetricPill label="End devices" value={endDeviceCount} />
          <MetricPill label="Links" value={linkCount} />
          {snapshot.requested_by && (
            <MetricPill label="Requested by" value={snapshot.requested_by} />
          )}
        </div>
        {snapshot.error && (
          <p className="mt-3 text-sm text-zl-critical">{snapshot.error}</p>
        )}
        {!hasLayout && (
          <p className="mt-3 border-l-2 border-zl-watch/40 pl-3 text-sm text-zl-muted">
            Snapshot stored, but node and link layout data is limited or empty. ZigbeeLens still
            uses passive MQTT updates for device health.
          </p>
        )}
      </Card>

      {hasLayout ? (
        <>
          <Card title="Nodes" subtitle={`${nodes.length} in latest snapshot`}>
            {nodes.length === 0 ? (
              <p className="text-sm text-zl-muted">No nodes recorded in this snapshot.</p>
            ) : (
              <ul className="divide-y divide-zl-border text-sm">
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
              <p className="mt-3 text-xs text-zl-muted">Showing first 50 of {nodes.length} nodes.</p>
            )}
          </Card>

          <Card title="Links" subtitle={`${links.length} in latest snapshot`}>
            {links.length === 0 ? (
              <p className="text-sm text-zl-muted">No links recorded in this snapshot.</p>
            ) : (
              <ul className="divide-y divide-zl-border text-sm">
                {links.slice(0, 50).map((link, idx) => (
                  <li key={`${link.source_ieee}-${link.target_ieee}-${idx}`} className="py-2">
                    <div className="font-mono text-xs text-zl-text break-all">
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
              <p className="mt-3 text-xs text-zl-muted">Showing first 50 of {links.length} links.</p>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}

export function TopologyPage() {
  const { status } = useScenario();
  const { networkId } = useParams<{ networkId?: string }>();
  const navigate = useNavigate();
  const overview = useLiveResource(() => api.topology(), []);
  const [modalNetwork, setModalNetwork] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const networks = overview.data?.networks ?? [];
  const activeNetworkId = useMemo(() => {
    if (networkId && networks.some((n) => n.network_id === networkId)) {
      return networkId;
    }
    return networks[0]?.network_id;
  }, [networkId, networks]);

  useEffect(() => {
    if (!overview.loading && networks.length > 0 && !networkId) {
      navigate(`/topology/${networks[0].network_id}`, { replace: true });
    }
  }, [overview.loading, networks, networkId, navigate]);

  const detail = useLiveResource(
    () =>
      activeNetworkId
        ? api.topologyNetwork(activeNetworkId)
        : Promise.reject(new Error("No network selected")),
    [activeNetworkId],
  );

  if (!status || overview.loading) return <LoadingState />;
  if (overview.error) return <ErrorState message={overview.error} onRetry={overview.refetch} />;

  const topology = overview.data;
  const enabled = topology?.enabled ?? status.topology?.enabled ?? false;

  async function confirmCapture(targetNetworkId: string) {
    setCapturing(true);
    setError(null);
    try {
      await api.captureTopology(targetNetworkId);
      setModalNetwork(null);
      await overview.refetch();
      if (targetNetworkId === activeNetworkId) {
        await detail.refetch();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Capture failed");
    } finally {
      setCapturing(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Topology</h1>
        <p className="mt-1 text-zl-muted">
          Point-in-time mesh snapshots for diagnostic enrichment. Select a network to inspect its
          latest snapshot.
        </p>
      </div>

      {!enabled && (
        <Card title="Topology disabled">
          <p className="text-sm text-zl-muted">
            Topology capture is disabled in configuration. Enable{" "}
            <code className="rounded bg-zl-surface-2 px-1">topology.enabled</code> to store
            snapshots and enrich diagnostics.
          </p>
        </Card>
      )}

      {enabled && networks.length === 0 && (
        <EmptyState title="No networks configured" detail="Add networks in configuration first." />
      )}

      {enabled && networks.length > 0 && activeNetworkId && (
        <>
          <NetworkTabs networks={networks} activeId={activeNetworkId} />

          {topology?.capture_in_progress && (
            <div className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-4 py-3 text-sm text-zl-watch">
              Topology capture in progress…
            </div>
          )}

          {topology?.last_capture_error && (
            <div className="rounded-lg border border-zl-critical/40 bg-zl-critical/10 px-4 py-3 text-sm text-zl-critical">
              Last capture error: {topology.last_capture_error}
            </div>
          )}

          {detail.loading && !detail.data ? (
            <LoadingState />
          ) : detail.error ? (
            <ErrorState message={detail.error} onRetry={detail.refetch} />
          ) : detail.data ? (
            <TopologyNetworkDetailView detail={detail.data} />
          ) : null}

          <Card title="All networks">
            <ul className="space-y-3 text-sm">
              {networks.map((network) => {
                const latest = network.latest_snapshot;
                const isActive = network.network_id === activeNetworkId;
                return (
                  <li
                    key={network.network_id}
                    className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border px-3 py-3 ${
                      isActive ? "border-zl-accent/40 bg-zl-accent/5" : "border-zl-border"
                    }`}
                  >
                    <div>
                      <div className="font-medium">{network.network_name}</div>
                      <div className="text-xs text-zl-muted">
                        {latest
                          ? `Latest snapshot ${relativeTime(latest.captured_at)} · ${latest.router_count} routers · ${latest.link_count} links`
                          : "No topology snapshot captured yet"}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {latest ? (
                        <Badge severity="healthy">snapshot</Badge>
                      ) : (
                        <Badge severity="watch">diagnostics limited</Badge>
                      )}
                      <Link
                        to={`/topology/${network.network_id}`}
                        className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
                      >
                        View topology
                      </Link>
                      {enabled && topology?.manual_capture_enabled && (
                        <button
                          type="button"
                          onClick={() => setModalNetwork(network.network_id)}
                          className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
                        >
                          Capture snapshot
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        </>
      )}

      {modalNetwork && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-w-lg rounded-xl border border-zl-border bg-zl-surface p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Capture topology snapshot?</h2>
            <p className="mt-3 text-sm leading-relaxed text-zl-muted">{CAPTURE_WARNING}</p>
            {error && <p className="mt-3 text-sm text-zl-critical">{error}</p>}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalNetwork(null)}
                className="rounded-lg border border-zl-border px-4 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={capturing}
                onClick={() => confirmCapture(modalNetwork)}
                className="rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {capturing ? "Capturing…" : "Capture topology snapshot"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
