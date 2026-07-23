import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { investigatePath } from "@/lib/routes";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricPill,
} from "@/components/ui";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { buildDeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";
import { bridgeStateLabel, bridgeStateSeverity } from "@/lib/format";
import { HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT } from "@/lib/events";

const NETWORK_EVENTS = [
  "network_health_updated",
  "health_updated",
  "dashboard_updated",
  "incidents_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
];

export function InvestigateLandingPage() {
  const { scenario } = useScenario();
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
        <h1 className="text-2xl font-semibold">Mesh / Investigate</h1>
        <p className="mt-1 text-zl-muted">
          Explore the evidence around one network after ZigbeeLens has identified what is worth
          checking.
        </p>
      </div>

      {networks.length === 0 ? (
        <div className="space-y-3">
          <EmptyState
            title="No networks configured"
            detail="Add a Zigbee2MQTT network in Settings, then return here to investigate."
          />
          <Link
            to="/settings"
            className="inline-flex min-h-11 items-center text-sm text-zl-accent hover:underline"
          >
            Open Settings →
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {networks.map((network) => {
            const summary = network.decision_summary;
            const reviewFirst = summary.status_counts.review_first ?? 0;
            const worthReviewing = summary.status_counts.worth_reviewing ?? 0;
            return (
              <Link
                key={network.id}
                to={investigatePath(network.id)}
                className="block rounded-xl border border-zl-border bg-zl-surface p-5 transition-colors hover:border-zl-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-zl-text">{network.name}</h2>
                    <p className="mt-0.5 break-all font-mono text-xs text-zl-muted">
                      {network.base_topic}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <DeviceDecisionBadge
                      decision={buildDeviceDecisionBadgeViewModel(network.decision)}
                    />
                    <Badge severity={bridgeStateSeverity(network.bridge_state)}>
                      Bridge: {bridgeStateLabel(network.bridge_state)}
                    </Badge>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  <MetricPill label="Devices" value={network.device_count} />
                  {network.active_incident_count > 0 && (
                    <MetricPill
                      label="Incidents"
                      value={network.active_incident_count}
                      severity="incident"
                    />
                  )}
                  {reviewFirst > 0 && (
                    <MetricPill label="Review first" value={reviewFirst} severity="incident" />
                  )}
                  {worthReviewing > 0 && (
                    <MetricPill label="Worth reviewing" value={worthReviewing} severity="watch" />
                  )}
                </div>
                <p className="mt-4 text-sm text-zl-accent">Investigate →</p>
              </Link>
            );
          })}
        </div>
      )}

      {networks.length > 0 && (
        <Card title="Supporting evidence">
          <p className="text-sm text-zl-muted">
            Raw topology snapshots remain available under Advanced &amp; support for capture status
            and snapshot detail.
          </p>
          <Link
            to="/topology"
            className="mt-3 inline-flex min-h-11 items-center text-sm text-zl-accent hover:underline"
          >
            Topology snapshots →
          </Link>
        </Card>
      )}
    </div>
  );
}
