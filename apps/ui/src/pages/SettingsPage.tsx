import { Link } from "react-router-dom";
import { useAuth } from "@/context/BrowserAuthContext";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { api } from "@/lib/api";
import { Badge, Card, LoadingState } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import { HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT } from "@/lib/events";

export function SettingsPage() {
  const auth = useAuth();
  const { status, refreshStatus, scenario, dataMode, isScenarioMode } = useScenario();
  const health = useLiveResource(() => api.health(), [], {
    refetchOn: [
      "collector_status",
      "collector_connected",
      "collector_disconnected",
      HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    ],
  });
  const storage = useLiveResource(() => api.storageStatus(), [], {
    refetchOn: ["storage_maintenance_completed"],
  });

  if (!status) return <LoadingState />;

  const healthPresent = health.data != null;
  const collector = health.data?.collector;
  const warnings = buildWarnings({
    dataMode,
    isScenarioMode,
    mqttConnected: status.mqtt_connected,
    collectorEnabled: collector?.enabled,
    lastMessageAt: healthPresent ? collector?.last_message_at : undefined,
    networkCount: status.configured_networks.length,
  });
  if (health.error && healthPresent) {
    warnings.unshift({
      text: "Core health refresh failed — showing the last accepted status.",
      severity: "watch",
    });
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings &amp; status</h1>
        <p className="text-sm leading-relaxed text-zl-muted">
          Core, collector, and configuration health. Secrets are never shown. For a full explanation
          of health rules and incidents, see{" "}
          <Link to="/monitoring" className="text-zl-accent hover:underline">
            How monitoring works
          </Link>
          .
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
              storage.refetch();
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
          <Row label="Enabled" value={formatHealthBool(healthPresent, collector?.enabled)} />
          <Row label="Connected" value={status.mqtt_connected ? "yes" : "no"} />
          <Row
            label="Subscribed topics"
            value={formatHealthCount(healthPresent, collector?.subscribed_topics_count)}
          />
          <Row
            label="Last message"
            value={
              !healthPresent
                ? "—"
                : collector?.last_message_at
                  ? relativeTime(collector.last_message_at)
                  : "none yet"
            }
          />
          <Row
            label="Last error"
            value={!healthPresent ? "—" : (collector?.last_error ?? "none")}
          />
        </dl>
        {collector?.networks && collector.networks.length > 0 && (
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
              // Configuration feature flag is distinct from live publisher health.
              (health.data?.mqtt_discovery?.enabled ?? status.features.mqtt_discovery)
                ? "yes"
                : "no"
            }
          />
          <Row
            label="Publisher connected"
            value={formatHealthBool(healthPresent, health.data?.mqtt_discovery?.connected)}
          />
          <Row
            label="Published entities"
            value={formatHealthCount(
              healthPresent,
              health.data?.mqtt_discovery?.published_entities_count,
            )}
          />
          <Row
            label="Last publish"
            value={
              !healthPresent
                ? "—"
                : health.data?.mqtt_discovery?.last_publish_at
                  ? relativeTime(health.data.mqtt_discovery.last_publish_at)
                  : "never"
            }
          />
          <Row
            label="Last error"
            value={
              !healthPresent ? "—" : (health.data?.mqtt_discovery?.last_error ?? "none")
            }
          />
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
            value={
              // Configuration topology flag may answer when live health is absent.
              (health.data?.topology?.enabled ?? status.topology?.enabled) ? "yes" : "no"
            }
          />
          <Row
            label="Manual capture"
            value={formatHealthBool(healthPresent, health.data?.topology?.manual_capture_enabled)}
          />
          <Row
            label="Capture in progress"
            value={formatHealthBool(healthPresent, health.data?.topology?.capture_in_progress)}
          />
          <Row
            label="Last capture error"
            value={
              !healthPresent ? "—" : (health.data?.topology?.last_capture_error ?? "none")
            }
          />
        </dl>
      </Card>

      <Card title="Home Assistant enrichment">
        <dl className="space-y-3 text-sm">
          <Row
            label="Enabled"
            value={formatHealthBool(
              healthPresent,
              health.data?.home_assistant_enrichment?.enabled,
            )}
          />
          <Row
            label="Matched devices"
            value={formatHealthCount(
              healthPresent,
              health.data?.home_assistant_enrichment?.matched_devices,
            )}
          />
          <Row
            label="Last push"
            value={
              !healthPresent
                ? "—"
                : health.data?.home_assistant_enrichment?.last_push_at
                  ? relativeTime(health.data.home_assistant_enrichment.last_push_at)
                  : "never"
            }
          />
        </dl>
      </Card>

      <Card title="Browser access">
        <dl className="space-y-3 text-sm">
          <Row
            label="Auth method"
            value={
              auth.authMethod === "session"
                ? "browser session"
                : auth.authMethod === "trusted_local"
                  ? "trusted local"
                  : auth.authMethod === "home_assistant_ingress"
                    ? "Home Assistant ingress"
                    : "—"
            }
          />
          <Row label="Browser sessions enabled" value={auth.browserSessionEnabled ? "yes" : "no"} />
          {auth.authMethod === "session" && auth.expiresAt && (
            <Row
              label="Session expires"
              value={(() => {
                const ms = Date.parse(auth.expiresAt);
                return Number.isNaN(ms) ? auth.expiresAt : new Date(ms).toLocaleString();
              })()}
            />
          )}
        </dl>
        {auth.authMethod === "session" && (
          <div className="mt-4 space-y-2">
            <button
              type="button"
              onClick={() => void auth.logout()}
              disabled={auth.logoutBusy}
              aria-busy={auth.logoutBusy}
              className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
            >
              {auth.logoutBusy ? "Signing out…" : "Sign out"}
            </button>
            {auth.logoutError && (
              <p className="text-sm text-zl-critical" role="alert">
                {auth.logoutError}
              </p>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-zl-muted">
          The UI exchanges an API token once for an HttpOnly browser session. The token is not stored
          in the browser. Sign out clears this browser cookie; it does not revoke copies of a stolen
          cookie.
        </p>
      </Card>

      <Card title="Storage and retention">
        <dl className="space-y-3 text-sm">
          <Row label="Database ready" value={status.storage_ready ? "yes" : "no"} />
          <Row
            label="Telemetry history"
            value={`${status.retention_days} days`}
          />
          <Row
            label="Resolved incidents"
            value={
              status.resolved_incident_retention_days == null
                ? "Kept indefinitely"
                : `${status.resolved_incident_retention_days} days`
            }
          />
          <Row
            label="Reports"
            value={
              status.report_retention_days == null
                ? "Until manually deleted"
                : `${status.report_retention_days} days`
            }
          />
          <Row
            label="Topology max snapshots / network"
            value={
              status.storage?.policy.topology_max_snapshots_per_network?.toString() ?? "—"
            }
          />
          <Row
            label="Maintenance interval"
            value={
              status.maintenance_interval_hours != null
                ? `${status.maintenance_interval_hours} hours`
                : "—"
            }
          />
          <Row
            label="Maintenance running"
            value={
              storage.data == null
                ? "—"
                : storage.data.maintenance.running
                  ? "yes"
                  : "no"
            }
          />
          <Row
            label="Last successful maintenance"
            value={
              storage.data?.maintenance.last_successful_at
                ? relativeTime(storage.data.maintenance.last_successful_at)
                : storage.data
                  ? "Never run"
                  : "—"
            }
          />
          <Row
            label="Next maintenance"
            value={
              storage.data?.maintenance.next_scheduled_at
                ? relativeTime(storage.data.maintenance.next_scheduled_at)
                : "—"
            }
          />
          <Row
            label="Last result"
            value={formatMaintenanceResult(storage.data?.maintenance)}
          />
          <Row
            label="Rows removed (last cycle)"
            value={
              storage.data?.maintenance.total_rows_deleted == null
                ? "—"
                : String(storage.data.maintenance.total_rows_deleted)
            }
          />
          <Row
            label="Last duration"
            value={
              storage.data?.maintenance.duration_ms == null
                ? "—"
                : `${storage.data.maintenance.duration_ms} ms`
            }
          />
          <Row
            label="Malformed timestamps"
            value={formatCategoryCount(
              storage.data?.maintenance.malformed_timestamps_by_category,
            )}
          />
          <Row
            label="Future timestamps"
            value={formatCategoryCount(
              storage.data?.maintenance.future_timestamps_by_category,
            )}
          />
          <Row
            label="WAL checkpoint busy"
            value={
              storage.data?.maintenance.wal_checkpoint?.busy == null
                ? "—"
                : storage.data.maintenance.wal_checkpoint.busy
                  ? "yes"
                  : "no"
            }
          />
          <Row
            label="Database size"
            value={formatBytes(storage.data?.footprint.database_bytes)}
          />
          <Row label="WAL size" value={formatBytes(storage.data?.footprint.wal_bytes)} />
          <Row
            label="Reusable space"
            value={formatBytes(storage.data?.footprint.reusable_bytes)}
          />
          <Row
            label="Integrity (quick)"
            value={storage.data?.integrity.quick_check.status ?? "—"}
          />
          <Row
            label="Integrity (foreign keys)"
            value={storage.data?.integrity.foreign_key_check.status ?? "—"}
          />
        </dl>
        <p className="mt-3 text-xs text-zl-muted">
          Retention and backups are local operator CLI responsibilities. There is no purge,
          vacuum, backup, or restore control in the UI.
        </p>
      </Card>

      <Card title="Configuration">
        <dl className="space-y-3 text-sm">
          <Row label="MQTT server" value={status.mqtt_server} />
          <Row label="Storage path" value={status.storage_path} mono />
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
  lastMessageAt: string | null | undefined;
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
  if (
    args.dataMode === "live" &&
    args.collectorEnabled === true &&
    args.mqttConnected &&
    args.lastMessageAt === null
  ) {
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

/** Health-request counts: absent health or missing field is unknown, not measured zero. */
function formatHealthCount(
  healthPresent: boolean,
  value: number | null | undefined,
): string {
  if (!healthPresent || value == null) return "—";
  return String(value);
}

/** Health-request booleans: absent health or missing field is unavailable, not factual "no". */
function formatHealthBool(
  healthPresent: boolean,
  value: boolean | null | undefined,
): string {
  if (!healthPresent || value == null) return "—";
  return value ? "yes" : "no";
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

const MAINTENANCE_ERROR_COPY: Record<string, string> = {
  interrupted: "Interrupted (previous cycle did not finish)",
  database_busy: "Database busy",
  integrity_check_failed: "Integrity check failed",
  maintenance_failed: "Maintenance failed",
};

function formatMaintenanceResult(
  maintenance:
    | {
        last_error_code: string | null;
        last_successful_at: string | null;
      }
    | null
    | undefined,
): string {
  if (!maintenance) return "—";
  if (maintenance.last_error_code) {
    return MAINTENANCE_ERROR_COPY[maintenance.last_error_code] ?? maintenance.last_error_code;
  }
  if (maintenance.last_successful_at) return "ok";
  return "—";
}

function formatCategoryCount(value: Record<string, number> | null | undefined): string {
  if (!value) return "—";
  const total = Object.values(value).reduce((sum, n) => sum + n, 0);
  return total > 0 ? String(total) : "—";
}
