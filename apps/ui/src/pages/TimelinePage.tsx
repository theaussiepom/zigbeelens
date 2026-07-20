import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { TimelineEventRow } from "@/components/cards";

const TIMELINE_EVENTS = [
  "dashboard_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  "incidents_updated",
  "timeline_updated",
  "health_updated",
  "collector_status",
];

const WINDOWS: Record<string, number> = {
  "1h": 3600_000,
  "24h": 86_400_000,
  "7d": 604_800_000,
};

export function TimelinePage() {
  const { scenario } = useScenario();
  const [searchParams] = useSearchParams();
  const initialNetwork = searchParams.get("network") ?? "";

  const [network, setNetwork] = useState(initialNetwork);
  const [kind, setKind] = useState("");
  const [severity, setSeverity] = useState("");
  const [window, setWindow] = useState("");
  const [incidentsOnly, setIncidentsOnly] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => setNetwork(initialNetwork), [initialNetwork]);

  const { data, error, loading, refetch } = useLiveResource(
    () => api.timeline(scenario || undefined, network || undefined).then((r) => r.items),
    [scenario, network],
    { refetchOn: TIMELINE_EVENTS },
  );

  const events = data ?? [];

  const options = useMemo(() => {
    const networks = new Set<string>();
    const kinds = new Set<string>();
    for (const e of events) {
      if (e.network_id) networks.add(e.network_id);
      kinds.add(e.kind);
    }
    return { networks: [...networks].sort(), kinds: [...kinds].sort() };
  }, [events]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const cutoff = window ? Date.now() - WINDOWS[window] : null;
    return events
      .filter((e) => {
        if (kind && e.kind !== kind) return false;
        if (severity && e.severity !== severity) return false;
        if (incidentsOnly && !e.incident_id) return false;
        if (cutoff && new Date(e.timestamp).getTime() < cutoff) return false;
        if (q) {
          const hay = `${e.title} ${e.summary} ${e.friendly_name ?? ""}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      })
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  }, [events, kind, severity, incidentsOnly, window, search]);

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Timeline</h1>
        <p className="mt-1 text-zl-muted">A troubleshooting trail in reverse chronological order.</p>
      </div>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Select label="Network" value={network} onChange={setNetwork} options={options.networks} />
          <Select label="Event type" value={kind} onChange={setKind} options={options.kinds} labeller={(k) => k.replace(/_/g, " ")} />
          <Select label="Severity" value={severity} onChange={setSeverity} options={["healthy", "watch", "incident", "critical"]} />
          <Select label="Time window" value={window} onChange={setWindow} options={["1h", "24h", "7d"]} labeller={(w) => `Last ${w}`} allLabel="All time" />
          <label className="flex flex-col gap-1 text-xs text-zl-muted">
            Search
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Title, device…"
              className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
            />
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm text-zl-muted">
            <input
              type="checkbox"
              checked={incidentsOnly}
              onChange={(e) => setIncidentsOnly(e.target.checked)}
            />
            Incidents only
          </label>
        </div>
      </Card>

      <Card>
        {filtered.length === 0 ? (
          <EmptyState title="No timeline events" detail="Try another filter or time window." />
        ) : (
          <div className="space-y-1">
            {filtered.map((e) => (
              <TimelineEventRow key={e.id} event={e} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  labeller,
  allLabel = "All",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  labeller?: (v: string) => string;
  allLabel?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zl-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
      >
        <option value="">{allLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {labeller ? labeller(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}
