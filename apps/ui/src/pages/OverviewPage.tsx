import { Link } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  StatTile,
} from "@/components/ui";
import {
  IncidentCard,
  NetworkDecisionCard,
  TimelineEventRow,
} from "@/components/cards";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { SharedAvailabilityEventCard } from "@/components/overview/SharedAvailabilityEventCard";
import { ModelPatternCard } from "@/components/overview/ModelPatternCard";
import { InvestigationPriorityCard } from "@/components/overview/InvestigationPriorityCard";
import { RecentChangesSection } from "@/components/overview/RecentChangesSection";
import { DataCoverageWarningCard } from "@/components/overview/DataCoverageWarningCard";
import { buildSharedAvailabilityEventViewModel } from "@/viewModels/overview/sharedAvailabilityEventViewModel";
import { buildModelPatternViewModel } from "@/viewModels/overview/modelPatternViewModel";
import {
  INVESTIGATION_PRIORITY_EMPTY_COPY,
  INVESTIGATION_PRIORITY_SECTION_SUBTITLE,
  INVESTIGATION_PRIORITY_SECTION_TITLE,
  buildInvestigationPriorityViewModel,
} from "@/viewModels/overview/investigationPriorityViewModel";
import { buildRecentChangesSectionViewModel } from "@/viewModels/overview/recentChangesViewModel";
import {
  DATA_COVERAGE_SECTION_TITLE,
  buildDataCoverageWarningViewModel,
} from "@/viewModels/overview/dataCoverageViewModel";
import {
  isValidOverviewVisitTimestamp,
  overviewVisitScope,
  readOverviewLastViewedAt,
  resolveOverviewPreviousLastViewedAt,
  writeOverviewLastViewedAt,
} from "@/lib/overviewVisitStorage";
import { buildDeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";

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
  const { scenario } = useScenario();
  const visitScope = overviewVisitScope(scenario);

  // Scenario selection changes in place without remounting the routed page.
  // Key the data-owning body by source scope so no frozen timestamp, accepted
  // resource, or write guard can cross from one source into another.
  return (
    <OverviewPageForScope
      key={visitScope}
      scenario={scenario}
      visitScope={visitScope}
    />
  );
}

function OverviewPageForScope({
  scenario,
  visitScope,
}: {
  scenario: string;
  visitScope: string;
}) {
  const dashboard = useLiveResource(() => api.dashboard(scenario || undefined), [scenario], {
    refetchOn: DASHBOARD_EVENTS,
  });
  const storedLastViewedAt = useMemo(
    () => readOverviewLastViewedAt(visitScope),
    [visitScope],
  );
  const [visitTimestamp, setVisitTimestamp] = useState<string | null>(null);
  const visitTimestampWritten = useRef(false);

  useEffect(() => {
    if (
      visitTimestamp === null &&
      dashboard.data &&
      !dashboard.loading &&
      isValidOverviewVisitTimestamp(dashboard.data.generated_at)
    ) {
      // Freeze the first accepted Core clock for this mount. Dashboard
      // refreshes must not move the boundary for the visit already underway.
      setVisitTimestamp(dashboard.data.generated_at);
    }
  }, [dashboard.data, dashboard.loading, visitTimestamp]);

  const previousLastViewedAt = useMemo(
    () =>
      visitTimestamp
        ? resolveOverviewPreviousLastViewedAt(storedLastViewedAt, visitTimestamp)
        : null,
    [storedLastViewedAt, visitTimestamp],
  );

  const activeIncidentsResource = useLiveResource(
    () =>
      api.incidents({
        scenario: scenario || undefined,
        status: ["open", "watching"],
        limit: 20,
      }).then((r) => r.items),
    [scenario],
    { refetchOn: DASHBOARD_EVENTS },
  );
  const recentIncidentsResource = useLiveResource(
    () => {
      if (!visitTimestamp || !previousLastViewedAt) {
        return Promise.resolve([]);
      }
      return api
        .incidents({
          scenario: scenario || undefined,
          updated_after: previousLastViewedAt,
          order: "recent",
          limit: 50,
        })
        .then((r) => r.items);
    },
    [scenario, previousLastViewedAt, visitTimestamp],
    { enabled: Boolean(visitTimestamp), refetchOn: DASHBOARD_EVENTS },
  );

  useEffect(() => {
    const recentIncidentEvidenceAccepted =
      previousLastViewedAt === null || recentIncidentsResource.data !== null;
    if (
      !visitTimestampWritten.current &&
      visitTimestamp !== null &&
      dashboard.data &&
      !dashboard.loading &&
      recentIncidentEvidenceAccepted
    ) {
      writeOverviewLastViewedAt(visitScope, visitTimestamp);
      visitTimestampWritten.current = true;
    }
  }, [
    dashboard.data,
    dashboard.loading,
    previousLastViewedAt,
    recentIncidentsResource.data,
    visitScope,
    visitTimestamp,
  ]);

  if (dashboard.error) return <ErrorState message={dashboard.error} onRetry={() => {
    dashboard.refetch();
    activeIncidentsResource.refetch();
    recentIncidentsResource.refetch();
  }} />;
  if (dashboard.loading || !dashboard.data) return <LoadingState />;

  const data = dashboard.data;
  const networkNames = Object.fromEntries(data.networks.map((network) => [network.id, network.name]));
  const investigationPriorities = data.investigation_priorities.map((priority) =>
    buildInvestigationPriorityViewModel(priority, networkNames[priority.network_id]),
  );
  const sharedAvailabilityEvents = data.shared_availability_events.map((event) =>
    buildSharedAvailabilityEventViewModel(event, networkNames[event.network_id]),
  );
  const modelPatterns = data.model_patterns.map((pattern) =>
    buildModelPatternViewModel(pattern, networkNames[pattern.network_id]),
  );
  // Server owns collection order (lifecycle rank, updated_at DESC, id DESC).
  const active = activeIncidentsResource.data;
  const recentChanges = buildRecentChangesSectionViewModel({
    previousLastViewedAt,
    dashboard: data,
    incidents: recentIncidentsResource.data ?? [],
  });
  const dataCoverageWarnings = (data.data_coverage_warnings ?? []).map((warning) =>
    buildDataCoverageWarningViewModel(warning, networkNames[warning.network_id]),
  );
  const estateDecision = buildDeviceDecisionBadgeViewModel({
    status: data.decision_summary.overall_status,
    priority: data.decision_summary.highest_priority,
    headline_code: `estate_${data.decision_summary.overall_status}`,
    coverage_label_codes: [],
  });
  const reviewFirst = data.decision_summary.status_counts.review_first ?? 0;
  const worthReviewing = data.decision_summary.status_counts.worth_reviewing ?? 0;

  return (
    <div className="max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-zl-muted">
            What needs review first, what changed, and where coverage is limited?
          </p>
        </div>
        <DeviceDecisionBadge decision={estateDecision} />
      </header>

      <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile
          label="Active incidents"
          value={data.active_incident_count}
          severity={data.active_incident_count ? "incident" : "healthy"}
        />
        <StatTile
          label="Unavailable"
          value={data.unavailable_device_count}
          severity={data.unavailable_device_count ? "incident" : "healthy"}
        />
        <StatTile
          label="Watching"
          value={data.watching_incident_count}
          severity={data.watching_incident_count ? "watch" : "healthy"}
        />
        <StatTile label="Networks" value={data.network_count} />
        <StatTile label="Devices" value={data.device_count} />
      </div>

      {(reviewFirst > 0 || worthReviewing > 0 || data.decision_summary.coverage_warning_count > 0) && (
        <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-3">
          <StatTile
            label="Review first"
            value={reviewFirst}
            severity={reviewFirst ? "incident" : "healthy"}
          />
          <StatTile
            label="Worth reviewing"
            value={worthReviewing}
            severity={worthReviewing ? "watch" : "healthy"}
          />
          <StatTile
            label="Coverage warnings"
            value={data.decision_summary.coverage_warning_count}
            severity={data.decision_summary.coverage_warning_count ? "watch" : "healthy"}
          />
        </div>
      )}

      <section className="space-y-3" aria-label={INVESTIGATION_PRIORITY_SECTION_TITLE}>
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            {INVESTIGATION_PRIORITY_SECTION_TITLE}
          </h2>
          <p className="mt-1 text-sm text-zl-muted">{INVESTIGATION_PRIORITY_SECTION_SUBTITLE}</p>
        </div>
        {investigationPriorities.length === 0 ? (
          <EmptyState title={INVESTIGATION_PRIORITY_EMPTY_COPY} />
        ) : (
          <div className="grid gap-4">
            {investigationPriorities.map((priority, index) => (
              <InvestigationPriorityCard
                key={priority.id}
                priority={priority}
                emphasized={index === 0}
              />
            ))}
          </div>
        )}
      </section>

      <RecentChangesSection
        section={recentChanges}
        incidentEvidence={
          previousLastViewedAt
            ? {
                hasAcceptedData: recentIncidentsResource.data !== null,
                loading: recentIncidentsResource.loading,
                error: recentIncidentsResource.error,
                onRetry: recentIncidentsResource.refetch,
              }
            : undefined
        }
      />

      {dataCoverageWarnings.length > 0 && (
        <section className="space-y-3" aria-label={DATA_COVERAGE_SECTION_TITLE}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            {DATA_COVERAGE_SECTION_TITLE}
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {dataCoverageWarnings.map((warning) => (
              <DataCoverageWarningCard key={warning.id} warning={warning} />
            ))}
          </div>
        </section>
      )}

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

      {modelPatterns.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Recent model patterns
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {modelPatterns.map((pattern) => (
              <ModelPatternCard key={pattern.id} pattern={pattern} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">Networks</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {data.networks.map((n) => (
            <NetworkDecisionCard key={n.id} network={n} showRawSnapshotLink={false} />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Active incidents
          </h2>
          {active && active.length > 0 && (
            <Link to="/incidents" className="text-sm text-zl-accent hover:underline">
              All incidents →
            </Link>
          )}
        </div>
        {active === null && activeIncidentsResource.loading ? (
          <LoadingState label="Loading active incidents…" />
        ) : active === null ? (
          <ErrorState
            message="Active incidents are unavailable."
            onRetry={activeIncidentsResource.refetch}
            retryLabel="Retry active incidents"
          />
        ) : (
          <div className="space-y-3">
            {activeIncidentsResource.error && (
              <SectionRefreshWarning
                message="Active incidents could not be refreshed. Showing the last loaded results."
                onRetry={activeIncidentsResource.refetch}
                retryLabel="Retry active incidents"
              />
            )}
            {active.length === 0 ? (
              <EmptyState
                title="No active incidents"
                detail="No correlated incident patterns right now."
              />
            ) : (
              <div className="grid gap-3">
                {active.slice(0, 4).map((inc) => (
                  <IncidentCard key={inc.id} incident={inc} />
                ))}
              </div>
            )}
          </div>
        )}
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

function SectionRefreshWarning({
  message,
  onRetry,
  retryLabel,
}: {
  message: string;
  onRetry: () => void;
  retryLabel: string;
}) {
  return (
    <div
      role="status"
      className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-3 py-2 text-sm text-zl-watch"
    >
      <p>{message}</p>
      <button
        type="button"
        aria-label={retryLabel}
        onClick={onRetry}
        className="mt-2 min-h-11 rounded-lg border border-zl-border px-3 py-1.5 text-sm text-zl-text hover:bg-zl-surface-2"
      >
        Retry
      </button>
    </div>
  );
}
