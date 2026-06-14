import { Link, useParams } from "react-router-dom";
import { useMemo, useState } from "react";
import type { Incident, IncidentStatus } from "@zigbeelens/shared";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Badge,
  Card,
  ConfidenceBadge,
  CounterEvidenceList,
  DeviceRoleBadge,
  EmptyState,
  ErrorState,
  EvidenceList,
  HealthBadge,
  LifecycleBadge,
  LimitationsList,
  LoadingState,
  NetworkBadge,
  SeverityBadge,
} from "@/components/ui";
import { IncidentCard, TimelineEventRow } from "@/components/cards";
import {
  compareIncidents,
  devicePath,
  formatTime,
  healthRank,
  incidentTypeLabel,
  relativeTime,
  scopeLabel,
} from "@/lib/format";

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
  const [severity, setSeverity] = useState("");
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
    const q = search.trim().toLowerCase();
    return incidents
      .filter((inc) => {
        if (network && !inc.network_ids.includes(network)) return false;
        if (severity && inc.severity !== severity) return false;
        if (scope && inc.scope !== scope) return false;
        if (type && inc.type !== type) return false;
        if (lifecycle && inc.status !== lifecycle) return false;
        if (q) {
          const haystack = [
            inc.title,
            inc.summary,
            ...inc.affected_devices.map((d) => d.friendly_name),
            ...inc.affected_devices.map((d) => d.ieee_address),
          ]
            .join(" ")
            .toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        return true;
      })
      .sort(compareIncidents);
  }, [incidents, network, severity, scope, type, lifecycle, search]);

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
          Evidence-backed explanations — correlation, not guaranteed root cause.
        </p>
      </div>

      {incidents.length === 0 ? (
        <EmptyState title="No active incidents" detail="All monitored networks look stable." />
      ) : (
        <>
          <Card>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Select label="Network" value={network} onChange={setNetwork} options={options.networks} />
              <Select
                label="Severity"
                value={severity}
                onChange={setSeverity}
                options={["healthy", "watch", "incident", "critical"]}
              />
              <Select label="Scope" value={scope} onChange={setScope} options={options.scopes} labeller={scopeLabel as (v: string) => string} />
              <Select label="Type" value={type} onChange={setType} options={options.types} labeller={incidentTypeLabel} />
              <Select
                label="Lifecycle"
                value={lifecycle}
                onChange={setLifecycle}
                options={["open", "watching", "resolved"]}
              />
              <label className="flex flex-col gap-1 text-xs text-zl-muted">
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
              const items = filtered.filter((i) => i.status === key);
              if (items.length === 0) return null;
              return (
                <section key={key} className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
                    {label} · {items.length}
                  </h2>
                  {items.map((inc) => (
                    <IncidentCard key={inc.id} incident={inc} />
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

  const affected = [...inc.affected_devices].sort(
    (a, b) => healthRank(a.health_primary) - healthRank(b.health_primary),
  );
  const routerCandidates = affected.filter((d) => d.health_primary === "router_risk");
  const reportSnippet = buildSnippet(inc);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link to="/incidents" className="text-sm text-zl-accent hover:underline">
          ← Incidents
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{inc.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <LifecycleBadge status={inc.status} />
          <SeverityBadge severity={inc.severity} />
          <Badge>{incidentTypeLabel(inc.type)}</Badge>
          <span className="text-xs text-zl-muted">{scopeLabel(inc.scope)}</span>
          <ConfidenceBadge confidence={inc.confidence} />
          {inc.network_ids.map((n) => (
            <NetworkBadge key={n} network={n} />
          ))}
        </div>
        <p className="mt-3 text-xs text-zl-muted" title={`${inc.opened_at} → ${inc.updated_at}`}>
          Opened {formatTime(inc.opened_at)} · Updated {relativeTime(inc.updated_at)}
          {inc.resolved_at ? ` · Resolved ${formatTime(inc.resolved_at)}` : ""}
        </p>
      </div>

      <Card title="What ZigbeeLens thinks">
        <p className="leading-relaxed text-zl-text">{inc.interpretation || inc.summary}</p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <EvidenceList items={inc.evidence} />
        <CounterEvidenceList items={inc.counter_evidence} />
        <LimitationsList items={inc.limitations} />
      </div>

      <Card title="Affected devices" subtitle="Bad-first — identity is network + IEEE address">
        {affected.length === 0 ? (
          <p className="text-sm text-zl-muted">No devices attached to this incident.</p>
        ) : (
          <ul className="divide-y divide-zl-border">
            {affected.map((d) => (
              <li key={`${d.network_id}-${d.ieee_address}`} className="py-3">
                <Link
                  to={devicePath(d.network_id, d.ieee_address)}
                  className="flex items-center justify-between gap-3 hover:text-zl-accent"
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium">{d.friendly_name}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-zl-muted">
                      <NetworkBadge network={d.network_id} />
                      <span className="font-mono">{d.ieee_address}</span>
                    </div>
                  </div>
                  <HealthBadge primary={d.health_primary} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {routerCandidates.length > 0 && (
        <Card
          title="Related router candidates"
          subtitle="ZigbeeLens cannot confirm dependent routes without topology data."
        >
          <ul className="space-y-2">
            {routerCandidates.map((d) => (
              <li key={`${d.network_id}-${d.ieee_address}`} className="flex items-center gap-2">
                <DeviceRoleBadge role="router candidate" />
                <Link to={devicePath(d.network_id, d.ieee_address)} className="hover:text-zl-accent">
                  {d.friendly_name}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {inc.timeline.length > 0 && (
        <Card title="Timeline">
          <div className="space-y-1">
            {inc.timeline.map((e) => (
              <TimelineEventRow key={e.id} event={e} />
            ))}
          </div>
        </Card>
      )}

      <CopyableSnippet text={reportSnippet} />
    </div>
  );
}

function CopyableSnippet({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Card
      title="Report snippet"
      subtitle="Copyable summary for GitHub issues or community posts"
      actions={
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
          className="rounded-lg bg-zl-accent/20 px-3 py-1.5 text-sm font-medium text-zl-accent hover:bg-zl-accent/30"
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

function buildSnippet(inc: Incident): string {
  const lines = [
    `# ${inc.title}`,
    "",
    `- Type: ${incidentTypeLabel(inc.type)}`,
    `- Lifecycle: ${inc.status}`,
    `- Severity: ${inc.severity}`,
    `- Scope: ${scopeLabel(inc.scope)}`,
    `- Confidence: ${inc.confidence}`,
    `- Networks: ${inc.network_ids.join(", ") || "—"}`,
    `- Affected devices: ${inc.affected_device_count}`,
    "",
    "## What ZigbeeLens thinks",
    inc.interpretation || inc.summary,
  ];
  if (inc.evidence.length) {
    lines.push("", "## Evidence", ...inc.evidence.map((e) => `- ${e.summary}`));
  }
  if (inc.counter_evidence.length) {
    lines.push("", "## Counter-evidence", ...inc.counter_evidence.map((e) => `- ${e.summary}`));
  }
  if (inc.limitations.length) {
    lines.push("", "## Limitations", ...inc.limitations.map((l) => `- ${l.summary}`));
  }
  return lines.join("\n");
}
