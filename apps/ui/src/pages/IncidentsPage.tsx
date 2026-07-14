import { Link, useParams } from "react-router-dom";
import { useMemo, useState } from "react";
import type { IncidentStatus } from "@zigbeelens/shared";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Badge,
  Card,
  CounterEvidenceList,
  EmptyState,
  ErrorState,
  EvidenceList,
  LifecycleBadge,
  LimitationsList,
  LoadingState,
  NetworkBadge,
} from "@/components/ui";
import { IncidentRecordCard } from "@/components/incidents/IncidentRecordCard";
import { TimelineEventRow } from "@/components/cards";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { incidentTypeLabel, scopeLabel } from "@/lib/format";
import {
  buildIncidentRecordViewModel,
  compareIncidentsByRecordTiming,
  incidentMatchesSearch,
} from "@/viewModels/incidents/incidentViewModel";
import {
  buildIncidentDetailViewModel,
  incidentTimingLine,
  recordedSeverityConfidenceLine,
} from "@/viewModels/incidents/incidentDetailViewModel";

const INCIDENT_EVENTS = [
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  "incidents_updated",
  "dashboard_updated",
];

export function IncidentsPage() {
  const { scenario } = useScenario();
  const { data, error, loading, refetch } = useLiveResource(
    () => api.incidents(scenario || undefined).then((r) => r.items),
    [scenario],
    { refetchOn: INCIDENT_EVENTS },
  );

  const [network, setNetwork] = useState("");
  const [scope, setScope] = useState("");
  const [type, setType] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");

  const incidents = data ?? [];

  const options = useMemo(() => {
    const networks = new Set<string>();
    const scopes = new Set<string>();
    const types = new Set<string>();
    for (const inc of incidents) {
      inc.network_ids.forEach((n) => networks.add(n));
      scopes.add(inc.scope);
      types.add(inc.type);
    }
    return {
      networks: [...networks].sort(),
      scopes: [...scopes].sort(),
      types: [...types].sort(),
    };
  }, [incidents]);

  const filtered = useMemo(() => {
    return incidents
      .filter((inc) => {
        if (network && !inc.network_ids.includes(network)) return false;
        if (scope && inc.scope !== scope) return false;
        if (type && inc.type !== type) return false;
        if (lifecycle && inc.status !== lifecycle) return false;
        if (!incidentMatchesSearch(inc, search)) return false;
        return true;
      })
      .sort(compareIncidentsByRecordTiming)
      .map(buildIncidentRecordViewModel);
  }, [incidents, network, scope, type, lifecycle, search]);

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;

  const groups: Array<{ key: IncidentStatus; label: string }> = [
    { key: "open", label: "Open" },
    { key: "watching", label: "Watching" },
    { key: "resolved", label: "Recently resolved" },
  ];

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Incidents</h1>
        <p className="mt-1 text-zl-muted">
          Recorded incidents and lifecycle history, with current Device Story
          decisions for affected devices.
        </p>
      </div>

      {incidents.length === 0 ? (
        <EmptyState
          title="No incident records"
          detail="No incident history is available for the current view."
        />
      ) : (
        <>
          <Card>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Select label="Network" value={network} onChange={setNetwork} options={options.networks} />
              <Select
                label="Lifecycle"
                value={lifecycle}
                onChange={setLifecycle}
                options={["open", "watching", "resolved"]}
              />
              <Select
                label="Scope"
                value={scope}
                onChange={setScope}
                options={options.scopes}
                labeller={scopeLabel as (v: string) => string}
              />
              <Select
                label="Type"
                value={type}
                onChange={setType}
                options={options.types}
                labeller={incidentTypeLabel}
              />
              <label className="flex flex-col gap-1 text-xs text-zl-muted sm:col-span-2">
                Search
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Device, friendly name, IEEE…"
                  className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
                />
              </label>
            </div>
          </Card>

          {filtered.length === 0 ? (
            <EmptyState title="No incidents match" detail="Try clearing filters." />
          ) : (
            groups.map(({ key, label }) => {
              const items = filtered.filter((i) => i.lifecycle === key);
              if (items.length === 0) return null;
              return (
                <section key={key} className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
                    {label} · {items.length}
                  </h2>
                  {items.map((record) => (
                    <IncidentRecordCard key={record.id} record={record} />
                  ))}
                </section>
              );
            })
          )}
        </>
      )}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  labeller,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  labeller?: (v: string) => string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zl-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {labeller ? labeller(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}

export function IncidentDetailPage() {
  const { incidentId } = useParams();
  const { scenario } = useScenario();
  const { data: inc, error, loading, refetch } = useLiveResource(
    () => api.incident(incidentId!, scenario || undefined),
    [incidentId, scenario],
    { refetchOn: INCIDENT_EVENTS, enabled: Boolean(incidentId) },
  );

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading || !inc) return <LoadingState />;

  const detail = buildIncidentDetailViewModel(inc);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link to="/incidents" className="text-sm text-zl-accent hover:underline">
          ← Incidents
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{detail.record.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <LifecycleBadge status={detail.record.lifecycle} />
          <Badge>{detail.record.typeLabel}</Badge>
          <span className="text-xs text-zl-muted">{detail.record.scopeLabel}</span>
          {detail.record.networks.map((n) => (
            <NetworkBadge key={n} network={n} />
          ))}
        </div>
        <p className="mt-2 text-xs text-zl-muted">{recordedSeverityConfidenceLine(inc)}</p>
        <p
          className="mt-1 text-xs text-zl-muted"
          title={`${inc.opened_at} → ${inc.updated_at}`}
        >
          {incidentTimingLine(inc)}
        </p>
      </div>

      <Card title="Incident record">
        <p className="leading-relaxed text-zl-text">{detail.record.recordSummary}</p>
      </Card>

      {detail.recordedInterpretation ? (
        <Card
          title="Recorded interpretation"
          subtitle="Stored with this incident when it was created or updated."
        >
          <p className="leading-relaxed text-zl-muted">{detail.recordedInterpretation}</p>
        </Card>
      ) : null}

      {detail.currentDeviceDecisions.length > 0 ? (
        <Card
          title="Current device decisions"
          subtitle="Current Device Story decisions are shown separately from the stored incident record."
        >
          <ul className="divide-y divide-zl-border">
            {detail.currentDeviceDecisions.map((device) => (
              <li key={device.key} className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{device.name}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-zl-muted">
                      <NetworkBadge network={device.networkId} />
                      <span className="break-all font-mono">{device.ieeeAddress}</span>
                    </div>
                    <p className="mt-2 text-sm text-zl-text">{device.decision.headline}</p>
                    <Link
                      to={device.deviceHref}
                      className="mt-2 inline-block text-sm text-zl-accent hover:underline"
                    >
                      View device →
                    </Link>
                  </div>
                  <div className="shrink-0">
                    <DeviceDecisionBadge decision={device.decision} />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          Stored incident evidence
        </h2>
        <div className="grid gap-4 lg:grid-cols-3">
          <EvidenceList items={detail.evidence} />
          <CounterEvidenceList items={detail.counterEvidence} />
          <LimitationsList items={detail.limitations} />
        </div>
      </div>

      {detail.timeline.length > 0 && (
        <Card title="Timeline">
          <div className="space-y-1">
            {detail.timeline.map((e) => (
              <TimelineEventRow key={e.id} event={e} />
            ))}
          </div>
        </Card>
      )}

      <CopyableSnippet text={detail.snippet} />
    </div>
  );
}

function CopyableSnippet({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Card
      title="Incident record snippet"
      subtitle="Copyable record summary for GitHub issues or community posts"
      actions={
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
          className="min-h-11 rounded-lg bg-zl-accent/20 px-4 py-2 text-sm font-medium text-zl-accent hover:bg-zl-accent/30 active:bg-zl-accent/40"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      }
    >
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs text-zl-muted">
        {text}
      </pre>
    </Card>
  );
}
