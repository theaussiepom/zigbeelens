import { Link, useParams } from "react-router-dom";
import type { NetworkSummary } from "@zigbeelens/shared";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricPill,
  StatTile,
} from "@/components/ui";
import {
  DeviceDecisionCard,
  IncidentCard,
  NetworkDecisionCard,
  TimelineEventRow,
} from "@/components/cards";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { bridgeStateLabel, bridgeStateSeverity, compareDevices } from "@/lib/format";
import { investigatePath, topologySnapshotPath } from "@/lib/routes";
import { buildDeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";
import { decisionStatusLabel } from "@/viewModels/decisionCopy";

const NETWORK_EVENTS = [
  "network_health_updated",
  "health_updated",
  "dashboard_updated",
  "incidents_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
];

export function NetworksPage() {
  const { scenario, status } = useScenario();
  const { data, error, loading, refetch } = useLiveResource(
    () => api.networks(scenario || undefined).then((r) => r.items),
    [scenario],
    { refetchOn: NETWORK_EVENTS },
  );

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;
  const networks = data ?? [];

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Networks</h1>
        <p className="mt-1 text-zl-muted">Compare Zigbee2MQTT networks side by side.</p>
      </div>
      {networks.length === 0 ? (
        <EmptyState
          title="No networks configured"
          detail="ZigbeeLens has not observed any Zigbee2MQTT networks yet."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {networks.map((n) => (
            <NetworkDecisionCard
              key={n.id}
              network={n}
              showRawSnapshotLink={status?.topology?.enabled ?? false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const REVIEW_STATUSES = new Set([
  "review_first",
  "worth_reviewing",
  "improve_data_coverage",
  "watch",
]);

function networkStatusLine(net: NetworkSummary): string {
  if (net.device_count === 0 || net.bridge_state === "unknown") {
    return "ZigbeeLens has not observed enough data for this network yet.";
  }
  if (net.active_incident_count > 0) {
    return "This network has active incidents.";
  }
  return `Decision status: ${decisionStatusLabel(net.decision.status)}.`;
}

export function NetworkDetailPage() {
  const { networkId } = useParams();
  const { scenario, status } = useScenario();
  const s = scenario || undefined;

  const net = useLiveResource(() => api.network(networkId!, s), [networkId, scenario], {
    refetchOn: NETWORK_EVENTS,
    enabled: Boolean(networkId),
  });
  const devices = useLiveResource(
    () => api.devices(s, networkId).then((r) => r.items),
    [networkId, scenario],
    { refetchOn: NETWORK_EVENTS, enabled: Boolean(networkId) },
  );
  const activeIncidentsResource = useLiveResource(
    () =>
      api
        .incidents({
          scenario: s,
          network_id: networkId!,
          status: ["open", "watching"],
          limit: 50,
        })
        .then((r) => r.items),
    [networkId, scenario],
    { refetchOn: NETWORK_EVENTS, enabled: Boolean(networkId) },
  );
  const resolvedIncidentsResource = useLiveResource(
    () =>
      api
        .incidents({
          scenario: s,
          network_id: networkId!,
          status: "resolved",
          limit: 20,
        })
        .then((r) => r.items),
    [networkId, scenario],
    { refetchOn: NETWORK_EVENTS, enabled: Boolean(networkId) },
  );
  const timeline = useLiveResource(
    () => api.timeline(s, networkId).then((r) => r.items),
    [networkId, scenario],
    { refetchOn: NETWORK_EVENTS, enabled: Boolean(networkId) },
  );

  if (net.error) return <ErrorState message={net.error} onRetry={net.refetch} />;
  if (net.loading || !net.data) return <LoadingState />;
  const n = net.data;

  const reviewDevices = [...(devices.data ?? [])]
    .filter((d) => REVIEW_STATUSES.has(d.decision.status))
    .sort(compareDevices)
    .slice(0, 6);
  const activeIncidents = activeIncidentsResource.data ?? [];
  const resolvedIncidents = resolvedIncidentsResource.data ?? [];
  const statusCounts = n.decision_summary.status_counts;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link to="/networks" className="text-sm text-zl-accent hover:underline">
          ← Networks
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{n.name}</h1>
          <DeviceDecisionBadge decision={buildDeviceDecisionBadgeViewModel(n.decision)} />
        </div>
        <p className="break-all font-mono text-sm text-zl-muted">{n.base_topic}</p>
        <p className="mt-2 text-zl-text">{networkStatusLine(n)}</p>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <Link
            to={investigatePath(n.id)}
            className="inline-flex min-h-11 items-center text-sm text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
          >
            Review this network in Mesh →
          </Link>
          {status?.topology?.enabled && (
            <Link
              to={topologySnapshotPath(n.id)}
              className="inline-flex min-h-11 items-center text-sm text-zl-muted hover:text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
            >
              Raw snapshot →
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="Bridge"
          value={bridgeStateLabel(n.bridge_state)}
          severity={bridgeStateSeverity(n.bridge_state)}
        />
        <StatTile label="Devices" value={n.device_count} />
        <StatTile
          label="Unavailable"
          value={n.unavailable_count}
          severity={n.unavailable_count ? "incident" : "healthy"}
        />
        <StatTile
          label="Incidents"
          value={n.active_incident_count}
          severity={n.active_incident_count ? "incident" : "healthy"}
        />
      </div>

      <Card title="Inventory and decision counts">
        <div className="flex flex-wrap gap-2">
          <MetricPill label="Routers" value={n.router_count} />
          <MetricPill label="End devices" value={n.end_device_count} />
          <MetricPill
            label="Review first"
            value={statusCounts.review_first ?? 0}
            severity={(statusCounts.review_first ?? 0) ? "incident" : "healthy"}
          />
          <MetricPill
            label="Worth reviewing"
            value={statusCounts.worth_reviewing ?? 0}
            severity={(statusCounts.worth_reviewing ?? 0) ? "watch" : "healthy"}
          />
          <MetricPill
            label="Coverage warnings"
            value={n.decision_summary.coverage_warning_count}
            severity={n.decision_summary.coverage_warning_count ? "watch" : "healthy"}
          />
          <MetricPill label="Bridge warnings" value={n.recent_bridge_warnings} severity={n.recent_bridge_warnings ? "watch" : "healthy"} />
          <MetricPill label="Bridge errors" value={n.recent_bridge_errors} severity={n.recent_bridge_errors ? "incident" : "healthy"} />
        </div>
      </Card>

      {n.coordinator && (
        <Card title="Coordinator">
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
            <Field label="IEEE" value={n.coordinator.ieee_address} mono />
            <Field label="Channel" value={n.coordinator.channel?.toString()} />
            <Field label="Model" value={n.coordinator.model} />
            <Field label="Manufacturer" value={n.coordinator.manufacturer} />
            <Field label="Firmware" value={n.coordinator.firmware} />
            <Field label="PAN ID" value={n.coordinator.pan_id} mono />
          </dl>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          Active incidents
        </h2>
        {activeIncidents.length === 0 ? (
          <EmptyState title="No active incidents on this network" />
        ) : (
          <div className="grid gap-3">
            {activeIncidents.map((inc) => (
              <IncidentCard key={inc.id} incident={inc} />
            ))}
          </div>
        )}
      </section>

      {reviewDevices.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Devices to review
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {reviewDevices.map((d) => (
              <DeviceDecisionCard key={`${d.network_id}-${d.ieee_address}`} device={d} />
            ))}
          </div>
        </section>
      )}

      {resolvedIncidents.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Recently resolved
          </h2>
          <div className="grid gap-3">
            {resolvedIncidents.map((inc) => (
              <IncidentCard key={inc.id} incident={inc} />
            ))}
          </div>
        </section>
      )}

      <Card
        title="Recent timeline"
        actions={
          <Link to={`/timeline?network=${n.id}`} className="text-sm text-zl-accent hover:underline">
            Full timeline →
          </Link>
        }
      >
        {(timeline.data?.length ?? 0) === 0 ? (
          <p className="text-sm text-zl-muted">No recent events.</p>
        ) : (
          <div className="space-y-1">
            {timeline.data!.slice(0, 12).map((e) => (
              <TimelineEventRow key={e.id} event={e} />
            ))}
          </div>
        )}
      </Card>

      <Link to={`/devices?network=${n.id}`} className="inline-flex text-sm text-zl-accent hover:underline">
        View all devices on {n.name} →
      </Link>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-zl-muted">{label}</dt>
      <dd className={mono ? "min-w-0 break-all text-right font-mono" : "min-w-0 break-words text-right"}>{value ?? "—"}</dd>
    </div>
  );
}
