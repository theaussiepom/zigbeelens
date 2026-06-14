import { Link } from "react-router-dom";
import type {
  DeviceSummary,
  DiagnosticConclusion,
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
  CounterEvidenceList,
  EvidenceList,
  HealthBadge,
  LastSeenText,
  LimitationsList,
  LifecycleBadge,
  MetricPill,
  NetworkBadge,
  SeverityBadge,
} from "@/components/ui";
import {
  confidenceLabel,
  devicePath,
  healthLabel,
  incidentTypeLabel,
  relativeTime,
  scopeLabel,
  severityDot,
} from "@/lib/format";

/* ----------------------------------------------------------------------- */
/* Current finding — the most important surface on the overview            */
/* ----------------------------------------------------------------------- */

export function CurrentFindingCard({
  finding,
  incidentId,
}: {
  finding: DiagnosticConclusion;
  incidentId?: string;
}) {
  return (
    <Card
      title="Current finding"
      subtitle="What ZigbeeLens sees right now — with evidence and limits"
      className="border-zl-accent/30 bg-gradient-to-br from-zl-surface to-zl-surface-2"
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-zl-muted">Likely scope: {scopeLabel(finding.scope)}</span>
        <ConfidenceBadge confidence={finding.confidence} />
      </div>
      <p className="mb-6 text-lg leading-relaxed text-zl-text">{finding.summary}</p>
      <div className="grid gap-4 md:grid-cols-3">
        <EvidenceList items={finding.evidence} emptyText="No supporting evidence yet." />
        <CounterEvidenceList items={finding.counter_evidence} />
        <LimitationsList items={finding.limitations} />
      </div>
      {incidentId && (
        <Link
          to={`/incidents/${incidentId}`}
          className="mt-4 inline-block text-sm text-zl-accent hover:underline"
        >
          View incident detail →
        </Link>
      )}
    </Card>
  );
}

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
/* Device health card (used in bad-first lists)                             */
/* ----------------------------------------------------------------------- */

export function DeviceHealthCard({ device }: { device: DeviceSummary }) {
  const flags = (device.health.flags ?? []).filter((f) => f !== device.health.primary);
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
            <span className="text-zl-muted">{device.device_type}</span>
          </div>
        </div>
        <HealthBadge primary={device.health.primary} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
        <AvailabilityBadge availability={device.availability} />
        <span title={`Confidence: ${confidenceLabel(device.health.confidence)}`}>
          {confidenceLabel(device.health.confidence)} confidence
        </span>
        {device.linkquality != null && <MetricPill label="LQI" value={device.linkquality} />}
        {device.battery != null && <MetricPill label="Batt" value={`${device.battery}%`} />}
        <LastSeenText iso={device.last_seen} prefix="seen" />
      </div>
      {flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {flags.map((f) => (
            <span key={f} className="text-xs text-zl-muted">
              · {healthLabel(f)}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}

/* ----------------------------------------------------------------------- */
/* Network health card                                                      */
/* ----------------------------------------------------------------------- */

export function NetworkHealthCard({ network }: { network: NetworkSummary }) {
  return (
    <Link
      to={`/networks/${network.id}`}
      className="block rounded-xl border border-zl-border bg-zl-surface p-5 transition-colors hover:border-zl-accent/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-zl-text">{network.name}</h3>
          <p className="mt-0.5 font-mono text-xs text-zl-muted">{network.base_topic}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <SeverityBadge severity={network.incident_state} />
          <Badge severity={network.bridge_state === "online" ? "healthy" : "critical"}>
            Bridge {network.bridge_state}
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
        {network.recently_unstable_count > 0 && (
          <MetricPill label="Unstable" value={network.recently_unstable_count} severity="watch" />
        )}
        {network.weak_link_count > 0 && (
          <MetricPill label="Weak" value={network.weak_link_count} severity="watch" />
        )}
        {network.low_battery_count > 0 && (
          <MetricPill label="Low batt" value={network.low_battery_count} severity="watch" />
        )}
        {network.stale_count > 0 && (
          <MetricPill label="Stale" value={network.stale_count} severity="watch" />
        )}
      </div>
    </Link>
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
            <span className="font-mono">{router.ieee_address}</span>
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
      <div className="w-40 shrink-0">
        <div className="font-mono text-xs text-zl-muted" title={new Date(event.timestamp).toLocaleString()}>
          {relativeTime(event.timestamp)}
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-xs">
          <span className={`h-1.5 w-1.5 rounded-full ${severityDot(event.severity)}`} />
          <span className="text-zl-muted">{event.kind.replace(/_/g, " ")}</span>
        </div>
      </div>
      <div className="min-w-0">
        <div className="font-medium text-zl-text">{event.title}</div>
        {event.summary && <div className="mt-0.5 text-sm text-zl-muted">{event.summary}</div>}
        {(event.network_id || event.friendly_name) && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
            {event.network_id && <NetworkBadge network={event.network_id} />}
            {event.friendly_name && <span>{event.friendly_name}</span>}
          </div>
        )}
      </div>
    </>
  );

  if (target) {
    return (
      <Link
        to={target}
        className="flex gap-4 rounded-lg border-l-2 border-zl-border py-2 pl-4 pr-2 transition-colors hover:border-zl-accent/60 hover:bg-zl-bg/30"
      >
        {body}
      </Link>
    );
  }
  return <div className="flex gap-4 border-l-2 border-zl-border py-2 pl-4">{body}</div>;
}
