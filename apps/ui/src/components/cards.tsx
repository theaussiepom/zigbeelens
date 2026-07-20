import { Link } from "react-router-dom";
import type {
  DeviceSummary,
  Incident,
  NetworkSummary,
  RouterRisk,
  TimelineEvent,
} from "@zigbeelens/shared";
import {
  AvailabilityBadge,
  Badge,
  Card,
  ConfidenceBadge,
  LastSeenText,
  LifecycleBadge,
  MetricPill,
  NetworkBadge,
  SeverityBadge,
} from "@/components/ui";
import {
  bridgeStateLabel,
  bridgeStateSeverity,
  confidenceLabel,
  devicePath,
  deviceTypeLabel,
  incidentTypeLabel,
  relativeTime,
  scopeLabel,
  severityDot,
} from "@/lib/format";
import { investigatePath, topologySnapshotPath } from "@/lib/routes";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { buildDeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";

/* ----------------------------------------------------------------------- */
/* Incident card                                                            */
/* ----------------------------------------------------------------------- */

export function IncidentCard({ incident }: { incident: Incident }) {
  const topEvidence = incident.evidence[0]?.summary ?? incident.conclusion.evidence[0]?.summary;
  const topLimitation =
    incident.limitations[0]?.summary ?? incident.conclusion.limitations[0]?.summary;
  return (
    <Link
      to={`/incidents/${incident.id}`}
      className="block rounded-xl border border-zl-border bg-zl-surface p-5 transition-colors hover:border-zl-accent/40"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <LifecycleBadge status={incident.status} />
        <SeverityBadge severity={incident.severity} />
        <Badge>{incidentTypeLabel(incident.type)}</Badge>
        <span className="text-xs text-zl-muted">
          {scopeLabel(incident.scope)} · {confidenceLabel(incident.confidence)} confidence
        </span>
      </div>
      <h3 className="text-lg font-semibold text-zl-text">{incident.title}</h3>
      <p className="mt-1 text-sm text-zl-muted">{incident.summary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {incident.network_ids.map((n) => (
          <NetworkBadge key={n} network={n} />
        ))}
        <span className="text-xs text-zl-muted">
          {incident.affected_device_count} affected device
          {incident.affected_device_count === 1 ? "" : "s"}
        </span>
      </div>
      {(topEvidence || topLimitation) && (
        <div className="mt-3 space-y-1 border-t border-zl-border/60 pt-3 text-xs text-zl-muted">
          {topEvidence && <p>Evidence: {topEvidence}</p>}
          {topLimitation && <p className="text-zl-watch">Limitation: {topLimitation}</p>}
        </div>
      )}
      <p
        className="mt-3 text-xs text-zl-muted"
        title={`Opened ${incident.opened_at} · Updated ${incident.updated_at}`}
      >
        Opened {relativeTime(incident.opened_at)} · Updated {relativeTime(incident.updated_at)}
        {incident.resolved_at ? ` · Resolved ${relativeTime(incident.resolved_at)}` : ""}
      </p>
    </Link>
  );
}

/* ----------------------------------------------------------------------- */
/* Device decision card (inventory / review lists)                          */
/* ----------------------------------------------------------------------- */

export function DeviceDecisionCard({ device }: { device: DeviceSummary }) {
  const decisionVm = buildDeviceDecisionBadgeViewModel(device.decision);
  return (
    <Link
      to={devicePath(device.network_id, device.ieee_address)}
      className="block rounded-lg border border-zl-border bg-zl-bg/40 p-4 transition-colors hover:border-zl-accent/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-zl-text">{device.friendly_name}</span>
            {device.incident_affected && <Badge severity="incident">In incident</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <NetworkBadge network={device.network_id} />
            <span className="text-zl-muted">{deviceTypeLabel(device.device_type)}</span>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <DeviceDecisionBadge decision={decisionVm} />
          <p className="mt-1 text-xs text-zl-muted">{decisionVm.headline}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
        <AvailabilityBadge availability={device.availability} />
        {device.linkquality != null && <MetricPill label="LQI" value={device.linkquality} />}
        {device.battery != null && <MetricPill label="Batt" value={`${device.battery}%`} />}
        <LastSeenText iso={device.last_seen} prefix="seen" />
      </div>
    </Link>
  );
}

/* ----------------------------------------------------------------------- */
/* Network decision card                                                    */
/* ----------------------------------------------------------------------- */

export function NetworkDecisionCard({
  network,
  topologyEnabled = false,
}: {
  network: NetworkSummary;
  topologyEnabled?: boolean;
}) {
  const summary = network.decision_summary;
  const reviewFirst = summary.status_counts.review_first ?? 0;
  const worthReviewing = summary.status_counts.worth_reviewing ?? 0;
  const coverage = summary.coverage_warning_count;
  return (
    <div className="rounded-xl border border-zl-border bg-zl-surface p-5 transition-colors hover:border-zl-accent/40">
      <Link
        to={`/networks/${network.id}`}
        className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-zl-text">{network.name}</h3>
            <p className="mt-0.5 break-all font-mono text-xs text-zl-muted">{network.base_topic}</p>
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
          {network.active_incident_count > 0 && (
            <MetricPill label="Incidents" value={network.active_incident_count} severity="incident" />
          )}
          <MetricPill label="Devices" value={network.device_count} />
          {network.unavailable_count > 0 && (
            <MetricPill label="Offline" value={network.unavailable_count} severity="incident" />
          )}
          {reviewFirst > 0 && (
            <MetricPill label="Review first" value={reviewFirst} severity="incident" />
          )}
          {worthReviewing > 0 && (
            <MetricPill label="Worth reviewing" value={worthReviewing} severity="watch" />
          )}
          {coverage > 0 && (
            <MetricPill label="Coverage" value={coverage} severity="watch" />
          )}
        </div>
      </Link>
      {topologyEnabled && (
        <Link
          to={topologySnapshotPath(network.id)}
          className="relative z-10 mt-4 inline-flex min-h-11 items-center rounded-lg text-sm text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        >
          View topology →
        </Link>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Router risk card                                                         */
/* ----------------------------------------------------------------------- */

export function RouterRiskCard({ router }: { router: RouterRisk }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={devicePath(router.network_id, router.ieee_address)}
            className="text-lg font-semibold text-zl-text hover:text-zl-accent"
          >
            {router.friendly_name}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
            <NetworkBadge network={router.network_id} />
            <span className="break-all font-mono">{router.ieee_address}</span>
          </div>
        </div>
        <SeverityBadge severity={router.risk.severity} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-zl-text">{router.risk.summary}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">
        <AvailabilityBadge availability={router.availability} />
        {router.linkquality != null && <MetricPill label="LQI" value={router.linkquality} />}
        {router.correlated_affected_devices > 0 && (
          <MetricPill
            label="Correlated"
            value={router.correlated_affected_devices}
            severity="watch"
          />
        )}
        <ConfidenceBadge confidence={router.risk.confidence} />
      </div>
      {router.risk.limitations.length > 0 && (
        <p className="mt-3 border-l-2 border-zl-watch/40 pl-3 text-sm text-zl-watch">
          {router.risk.limitations[0]?.summary}
        </p>
      )}
      <Link
        to={investigatePath(router.network_id)}
        className="mt-4 inline-flex min-h-11 items-center text-sm text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
      >
        Review in Mesh →
      </Link>
    </Card>
  );
}

/* ----------------------------------------------------------------------- */
/* Timeline event row                                                       */
/* ----------------------------------------------------------------------- */

export function TimelineEventRow({ event }: { event: TimelineEvent }) {
  const target = event.incident_id
    ? `/incidents/${event.incident_id}`
    : event.network_id && event.ieee_address
      ? devicePath(event.network_id, event.ieee_address)
      : event.network_id
        ? `/networks/${event.network_id}`
        : null;

  const body = (
    <>
      <div className="w-full shrink-0 sm:w-32">
        <div className="font-mono text-xs text-zl-muted" title={new Date(event.timestamp).toLocaleString()}>
          {relativeTime(event.timestamp)}
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-xs">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${severityDot(event.severity)}`} />
          <span className="break-words text-zl-muted">{event.kind.replace(/_/g, " ")}</span>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words font-medium text-zl-text">{event.title}</div>
        {event.summary && (
          <div className="mt-0.5 break-words text-sm text-zl-muted">{event.summary}</div>
        )}
        {(event.network_id || event.friendly_name) && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
            {event.network_id && <NetworkBadge network={event.network_id} />}
            {event.friendly_name && <span className="break-words">{event.friendly_name}</span>}
          </div>
        )}
      </div>
    </>
  );

  if (target) {
    return (
      <Link
        to={target}
        className="flex flex-col gap-2 overflow-hidden rounded-lg border-l-2 border-zl-border py-2 pl-4 pr-2 transition-colors hover:border-zl-accent/60 hover:bg-zl-bg/30 active:bg-zl-bg/30 sm:flex-row sm:gap-4"
      >
        {body}
      </Link>
    );
  }
  return (
    <div className="flex flex-col gap-2 overflow-hidden border-l-2 border-zl-border py-2 pl-4 pr-2 sm:flex-row sm:gap-4">
      {body}
    </div>
  );
}
