import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { Badge, Card, LoadingState } from "@/components/ui";
import { relativeTime } from "@/lib/format";

export function SettingsPage() {
  const { status, refreshStatus, scenario, dataMode, isScenarioMode } = useScenario();
  const health = useLiveResource(() => api.health(), [], {
    refetchOn: ["collector_status", "collector_connected", "collector_disconnected"],
  });

  if (!status) return <LoadingState />;

  const collector = health.data?.collector ?? {};
  const warnings = buildWarnings({
    dataMode,
    isScenarioMode,
    mqttConnected: status.mqtt_connected,
    collectorEnabled: collector.enabled,
    lastMessageAt: collector.last_message_at ?? null,
    networkCount: status.configured_networks.length,
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings &amp; status</h1>
        <p className="mt-1 text-zl-muted">
          Core, collector, and configuration health. Secrets are never shown.
        </p>
      </div>

      {warnings.length > 0 && (
        <Card title="Warnings">
          <ul className="space-y-2">
            {warnings.map((w) => (
              <li key={w.text} className="flex items-center gap-2 text-sm">
                <Badge severity={w.severity}>{w.severity === "incident" ? "warning" : "note"}</Badge>
                <span className="text-zl-text">{w.text}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Core status"
        actions={
          <button
            type="button"
            onClick={() => {
              refreshStatus();
              health.refetch();
            }}
            className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 active:bg-zl-surface-2"
          >
            Refresh
          </button>
        }
      >
        <dl className="space-y-3 text-sm">
          <Row label="Version" value={status.version} />
          <Row label="Uptime" value={`${status.uptime_seconds}s`} />
          <Row label="Health" value={health.data?.status ?? "—"} />
          <Row label="Database" value={health.data?.database ?? (status.storage_ready ? "ok" : "—")} />
          <Row label="Migration version" value={health.data?.migration_version?.toString() ?? "—"} />
          <Row label="Data mode" value={status.data_mode} />
          <Row label="Active scenario" value={isScenarioMode ? (status.active_scenario ?? scenario) || "default" : "—"} />
        </dl>
      </Card>

      <Card title="Collector status">
        <dl className="space-y-3 text-sm">
          <Row label="Enabled" value={collector.enabled ? "yes" : "no"} />
          <Row label="Connected" value={status.mqtt_connected ? "yes" : "no"} />
          <Row label="Subscribed topics" value={(collector.subscribed_topics_count ?? 0).toString()} />
          <Row
            label="Last message"
            value={collector.last_message_at ? relativeTime(collector.last_message_at) : "none yet"}
          />
          <Row label="Last error" value={collector.last_error ?? "none"} />
        </dl>
        {collector.networks && collector.networks.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm">
            {collector.networks.map((n) => (
              <li key={n.network_id} className="flex items-center justify-between gap-3">
                <span className="break-all font-mono text-zl-muted">{n.network_id}</span>
                <Badge severity={n.subscribed ? "healthy" : "watch"}>
                  {n.subscribed ? "subscribed" : "not subscribed"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="MQTT Discovery">
        <dl className="space-y-3 text-sm">
          <Row
            label="Enabled"
            value={
              (health.data?.mqtt_discovery?.enabled ?? status.features.mqtt_discovery)
                ? "yes"
                : "no"
            }
          />
          <Row
            label="Publisher connected"
            value={health.data?.mqtt_discovery?.connected ? "yes" : "no"}
          />
          <Row
            label="Published entities"
            value={(health.data?.mqtt_discovery?.published_entities_count ?? 0).toString()}
          />
          <Row
            label="Last publish"
            value={
              health.data?.mqtt_discovery?.last_publish_at
                ? relativeTime(health.data.mqtt_discovery.last_publish_at)
                : "never"
            }
          />
          <Row label="Last error" value={health.data?.mqtt_discovery?.last_error ?? "none"} />
        </dl>
        {status.mqtt_discovery && (
          <dl className="mt-4 space-y-3 border-t border-zl-border/40 pt-4 text-sm">
            <Row label="Discovery prefix" value={String(status.mqtt_discovery.topic_prefix ?? "—")} mono />
            <Row
              label="State prefix"
              value={String(status.mqtt_discovery.state_topic_prefix ?? "—")}
              mono
            />
            <Row label="Retain states" value={status.mqtt_discovery.retain ? "yes" : "no"} />
          </dl>
        )}
      </Card>

      <Card title="Topology snapshots">
        <dl className="space-y-3 text-sm">
          <Row
            label="Enabled"
            value={(health.data?.topology?.enabled ?? status.topology?.enabled) ? "yes" : "no"}
          />
          <Row
            label="Manual capture"
            value={health.data?.topology?.manual_capture_enabled ? "yes" : "no"}
          />
          <Row
            label="Capture in progress"
            value={health.data?.topology?.capture_in_progress ? "yes" : "no"}
          />
          <Row label="Last capture error" value={health.data?.topology?.last_capture_error ?? "none"} />
        </dl>
      </Card>

      <Card title="Home Assistant enrichment">
        <dl className="space-y-3 text-sm">
          <Row
            label="Enabled"
            value={health.data?.home_assistant_enrichment?.enabled ? "yes" : "no"}
          />
          <Row
            label="Matched devices"
            value={String(health.data?.home_assistant_enrichment?.matched_devices ?? 0)}
          />
          <Row
            label="Last push"
            value={
              health.data?.home_assistant_enrichment?.last_push_at
                ? relativeTime(health.data.home_assistant_enrichment.last_push_at)
                : "never"
            }
          />
        </dl>
      </Card>

      <Card title="Configuration">
        <dl className="space-y-3 text-sm">
          <Row label="MQTT server" value={status.mqtt_server} />
          <Row label="Storage path" value={status.storage_path} mono />
          <Row label="Retention (configured)" value={`${status.retention_days} days — purged on Core startup`} />
        </dl>
        <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-zl-muted">
          Configured networks
        </h3>
        <ul className="space-y-2 text-sm">
          {status.configured_networks.length === 0 ? (
            <li className="text-zl-muted">No networks configured.</li>
          ) : (
            status.configured_networks.map((n) => (
              <li key={n.id} className="rounded-lg border border-zl-border px-3 py-2">
                <div className="font-medium">{n.name}</div>
                <div className="break-all font-mono text-xs text-zl-muted">{n.id} · {n.base_topic}</div>
              </li>
            ))
          )}
        </ul>
      </Card>

      <Card title="Features">
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          {Object.entries(status.features).map(([k, v]) => (
            <div key={k} className="flex flex-col gap-1 border-b border-zl-border/40 py-2 sm:flex-row sm:justify-between">
              <dt className="text-zl-muted">{k.replace(/_/g, " ")}</dt>
              <dd>{v ? "enabled" : "disabled"}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {status.diagnostics && Object.keys(status.diagnostics).length > 0 && (
        <Card title="Diagnostics thresholds">
          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            {Object.entries(status.diagnostics).map(([k, v]) => (
              <div key={k} className="flex flex-col gap-1 border-b border-zl-border/40 py-2 sm:flex-row sm:justify-between">
                <dt className="text-zl-muted">{k.replace(/_/g, " ")}</dt>
                <dd className="break-all font-mono">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <Card title="Read-only guarantee">
        <p className="text-sm leading-relaxed text-zl-muted">
          ZigbeeLens never performs destructive Zigbee actions — no force-remove, permit-join,
          reset, repair, reconfigure, bind, unbind, OTA, or channel changes. It observes
          Zigbee2MQTT over MQTT, never publishes commands or request topics, and never mutates
          Zigbee state.
        </p>
      </Card>
    </div>
  );
}

function buildWarnings(args: {
  dataMode: "mock" | "live";
  isScenarioMode: boolean;
  mqttConnected: boolean;
  collectorEnabled?: boolean;
  lastMessageAt: string | null;
  networkCount: number;
}): Array<{ text: string; severity: "incident" | "watch" }> {
  const out: Array<{ text: string; severity: "incident" | "watch" }> = [];
  if (args.isScenarioMode) {
    out.push({ text: "Scenario/mock mode is active — data shown is fixture data.", severity: "watch" });
  }
  if (args.dataMode === "live" && args.collectorEnabled && !args.mqttConnected) {
    out.push({ text: "The MQTT collector is not connected.", severity: "incident" });
  }
  if (args.networkCount === 0) {
    out.push({ text: "No networks are configured.", severity: "watch" });
  }
  if (args.dataMode === "live" && args.mqttConnected && !args.lastMessageAt) {
    out.push({ text: "Connected, but no MQTT data has been received yet.", severity: "watch" });
  }
  return out;
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-zl-muted">{label}</dt>
      <dd className={mono ? "break-all text-right font-mono" : "text-right"}>{value}</dd>
    </div>
  );
}
