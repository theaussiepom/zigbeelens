import { Link } from "react-router-dom";
import { useCallback } from "react";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SeverityBadge,
  StatTile,
} from "@/components/ui";
import {
  CurrentFindingCard,
  DeviceHealthCard,
  IncidentCard,
  NetworkHealthCard,
  RouterRiskCard,
  TimelineEventRow,
} from "@/components/cards";
import { SharedAvailabilityEventCard } from "@/components/overview/SharedAvailabilityEventCard";
import { buildSharedAvailabilityEventViewModel } from "@/viewModels/overview/sharedAvailabilityEventViewModel";
import { compareIncidents } from "@/lib/format";

const DASHBOARD_EVENTS = [
  "dashboard_update",
  "dashboard_updated",
  "health_updated",
  "network_health_updated",
  "device_health_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  "incidents_updated",
];

export function OverviewPage() {
  const { scenario, status } = useScenario();

  const dashboard = useLiveResource(() => api.dashboard(scenario || undefined), [scenario], {
    refetchOn: DASHBOARD_EVENTS,
  });
  const incidents = useLiveResource(
    () => api.incidents(scenario || undefined).then((r) => r.items),
    [scenario],
    { refetchOn: DASHBOARD_EVENTS },
  );

  const retry = useCallback(() => {
    dashboard.refetch();
    incidents.refetch();
  }, [dashboard, incidents]);

  if (dashboard.error) return <ErrorState message={dashboard.error} onRetry={retry} />;
  if (dashboard.loading || !dashboard.data) return <LoadingState />;

  const data = dashboard.data;
  const networkNames = Object.fromEntries(data.networks.map((network) => [network.id, network.name]));
  const sharedAvailabilityEvents = data.shared_availability_events.map((event) =>
    buildSharedAvailabilityEventViewModel(event, networkNames[event.network_id]),
  );
  const allIncidents = incidents.data ?? [];
  const active = allIncidents
    .filter((i) => i.status === "open" || i.status === "watching")
    .sort(compareIncidents);
  const topOpenIncidentId = active.find((i) => i.status === "open")?.id ?? active[0]?.id;

  return (
    <div className="max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-zl-muted">Is anything broken, where, and what does the evidence say?</p>
        </div>
        <SeverityBadge severity={data.overall_severity} />
      </header>

      <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile
          label="Active incidents"
          value={data.active_incident_count}
          severity={data.active_incident_count ? "incident" : "healthy"}
        />
        <StatTile label="Networks" value={data.networks.length} />
        <StatTile label="Devices" value={data.health_snapshot.device_count} />
        <StatTile
          label="Unavailable"
          value={data.health_snapshot.unavailable_count}
          severity={data.health_snapshot.unavailable_count ? "incident" : "healthy"}
        />
        <StatTile
          label="Watching"
          value={data.watching_incident_count}
          severity={data.watching_incident_count ? "watch" : "healthy"}
        />
        <StatTile
          label="Router risks"
          value={data.router_risks.length}
          severity={data.router_risks.length ? "watch" : "healthy"}
        />
        <StatTile
          label="Recently unstable"
          value={data.recently_unstable.length}
          severity={data.recently_unstable.length ? "watch" : "healthy"}
        />
        <StatTile
          label="Stale"
          value={data.stale_devices.length}
          severity={data.stale_devices.length ? "watch" : "healthy"}
        />
        <StatTile
          label="Weak links"
          value={data.weak_links.length}
          severity={data.weak_links.length ? "watch" : "healthy"}
        />
        <StatTile
          label="Low battery"
          value={data.low_batteries.length}
          severity={data.low_batteries.length ? "watch" : "healthy"}
        />
      </div>

      <CurrentFindingCard finding={data.current_finding} incidentId={topOpenIncidentId} />

      {sharedAvailabilityEvents.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Recent shared availability events
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {sharedAvailabilityEvents.map((event) => (
              <SharedAvailabilityEventCard key={event.id} event={event} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">Networks</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {data.networks.map((n) => (
            <NetworkHealthCard
              key={n.id}
              network={n}
              topologyEnabled={status?.topology?.enabled ?? false}
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Active incidents
          </h2>
          {allIncidents.length > 0 && (
            <Link to="/incidents" className="text-sm text-zl-accent hover:underline">
              All incidents →
            </Link>
          )}
        </div>
        {active.length === 0 ? (
          <EmptyState title="No active incidents" detail="No correlated incident patterns right now." />
        ) : (
          <div className="grid gap-3">
            {active.slice(0, 4).map((inc) => (
              <IncidentCard key={inc.id} incident={inc} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          Top affected devices
        </h2>
        {data.top_affected_devices.length === 0 ? (
          <EmptyState title="No current device health concerns" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.top_affected_devices.map((d) => (
              <DeviceHealthCard key={`${d.network_id}-${d.ieee_address}`} device={d} />
            ))}
          </div>
        )}
      </section>

      {data.router_risks.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Router risks
          </h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.router_risks.map((r) => (
              <RouterRiskCard key={`${r.network_id}-${r.ieee_address}`} router={r} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          Health signal summaries
        </h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <SignalGroup title="Recently unstable" devices={data.recently_unstable} />
          <SignalGroup title="Weak links" devices={data.weak_links} />
          <SignalGroup title="Low battery" devices={data.low_batteries} />
          <SignalGroup title="Stale reporting" devices={data.stale_devices} />
        </div>
      </section>

      <Card
        title="Recent timeline"
        subtitle="Latest meaningful network events"
        actions={
          <Link to="/timeline" className="text-sm text-zl-accent hover:underline">
            Full timeline →
          </Link>
        }
      >
        {data.recent_timeline.length === 0 ? (
          <p className="text-sm text-zl-muted">No recent events.</p>
        ) : (
          <div className="space-y-1">
            {data.recent_timeline.slice(0, 12).map((e) => (
              <TimelineEventRow key={e.id} event={e} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function SignalGroup({
  title,
  devices,
}: {
  title: string;
  devices: import("@zigbeelens/shared").DeviceSummary[];
}) {
  return (
    <Card title={title}>
      {devices.length === 0 ? (
        <p className="text-sm text-zl-muted">None detected.</p>
      ) : (
        <div className="space-y-2">
          {devices.slice(0, 5).map((d) => (
            <DeviceHealthCard key={`${d.network_id}-${d.ieee_address}`} device={d} />
          ))}
        </div>
      )}
    </Card>
  );
}

