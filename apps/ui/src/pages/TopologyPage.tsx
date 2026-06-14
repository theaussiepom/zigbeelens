import { useState } from "react";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { Badge, Card, LoadingState } from "@/components/ui";
import { relativeTime } from "@/lib/format";

const CAPTURE_WARNING =
  "Capturing a Zigbee network map asks Zigbee2MQTT to scan the mesh. On larger networks this may temporarily make Zigbee less responsive. ZigbeeLens will not change Zigbee state, but this diagnostic request can create temporary network load.";

export function TopologyPage() {
  const { status } = useScenario();
  const overview = useLiveResource(() => api.topology(), []);
  const [modalNetwork, setModalNetwork] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status || overview.loading) return <LoadingState />;

  const topology = overview.data;
  const enabled = topology?.enabled ?? status.topology?.enabled ?? false;

  async function confirmCapture(networkId: string) {
    setCapturing(true);
    setError(null);
    try {
      await api.captureTopology(networkId);
      setModalNetwork(null);
      await overview.refetch();
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
          Optional point-in-time mesh snapshots for diagnostic enrichment. Topology is never required.
        </p>
      </div>

      {!enabled && (
        <Card title="Topology disabled">
          <p className="text-sm text-zl-muted">
            Topology capture is disabled in configuration. Enable{" "}
            <code className="rounded bg-zl-surface-2 px-1">topology.enabled</code> and{" "}
            <code className="rounded bg-zl-surface-2 px-1">features.manual_network_map</code> to
            capture snapshots manually.
          </p>
        </Card>
      )}

      <Card title="Networks">
        <ul className="space-y-3 text-sm">
          {(topology?.networks ?? []).map((network) => {
            const latest = network.latest_snapshot;
            return (
              <li
                key={network.network_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zl-border px-3 py-3"
              >
                <div>
                  <div className="font-medium">{network.network_name}</div>
                  <div className="text-xs text-zl-muted">
                    {latest
                      ? `Latest snapshot ${relativeTime(latest.captured_at)} · ${latest.router_count} routers · ${latest.link_count} links`
                      : "No topology snapshot captured yet"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {latest ? (
                    <Badge severity="healthy">snapshot</Badge>
                  ) : (
                    <Badge severity="watch">none</Badge>
                  )}
                  {enabled && topology?.manual_capture_enabled && (
                    <button
                      type="button"
                      onClick={() => setModalNetwork(network.network_id)}
                      className="min-h-11 w-full rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 active:bg-zl-surface-2 sm:w-auto"
                    >
                      Capture topology snapshot
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </Card>

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
