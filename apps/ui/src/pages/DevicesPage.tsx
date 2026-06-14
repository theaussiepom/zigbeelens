import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import type { DeviceDetail, Incident } from "@zigbeelens/shared";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  AvailabilityBadge,
  Badge,
  Card,
  ConfidenceBadge,
  CounterEvidenceList,
  DeviceRoleBadge,
  EmptyState,
  ErrorState,
  EvidenceList,
  HealthBadge,
  LimitationsList,
  LoadingState,
  NetworkBadge,
  SeverityBadge,
} from "@/components/ui";
import { DeviceHealthCard, IncidentCard } from "@/components/cards";
import {
  availabilityLabel,
  compareDevices,
  deviceTypeLabel,
  formatTime,
  healthLabel,
  interviewStateLabel,
  powerSourceLabel,
} from "@/lib/format";

const DEVICE_EVENTS = [
  "device_health_updated",
  "health_updated",
  "dashboard_updated",
  "incidents_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
];

export function DevicesPage() {
  const { scenario } = useScenario();
  const [searchParams] = useSearchParams();
  const initialNetwork = searchParams.get("network") ?? "";

  const { data, error, loading, refetch } = useLiveResource(
    () => api.devices(scenario || undefined).then((r) => r.items),
    [scenario],
    { refetchOn: DEVICE_EVENTS },
  );

  const [network, setNetwork] = useState(initialNetwork);
  const [health, setHealth] = useState("");
  const [deviceType, setDeviceType] = useState("");
  const [power, setPower] = useState("");
  const [availability, setAvailability] = useState("");
  const [hasIncident, setHasIncident] = useState(false);
  const [search, setSearch] = useState("");
  const [showHealthy, setShowHealthy] = useState(false);

  useEffect(() => setNetwork(initialNetwork), [initialNetwork]);

  const devices = data ?? [];

  const options = useMemo(() => {
    const networks = new Set<string>();
    const types = new Set<string>();
    const powers = new Set<string>();
    const healths = new Set<string>();
    for (const d of devices) {
      networks.add(d.network_id);
      types.add(d.device_type);
      powers.add(d.power_source);
      healths.add(d.health.primary);
    }
    return {
      networks: [...networks].sort(),
      types: [...types].sort(),
      powers: [...powers].sort(),
      healths: [...healths].sort(),
    };
  }, [devices]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return devices
      .filter((d) => {
        if (network && d.network_id !== network) return false;
        if (health && d.health.primary !== health) return false;
        if (deviceType && d.device_type !== deviceType) return false;
        if (power && d.power_source !== power) return false;
        if (availability && d.availability !== availability) return false;
        if (hasIncident && !d.incident_affected) return false;
        if (q) {
          const hay = `${d.friendly_name} ${d.ieee_address}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      })
      .sort(compareDevices);
  }, [devices, network, health, deviceType, power, availability, hasIncident, search]);

  const concerning = filtered.filter((d) => d.incident_affected || d.health.primary !== "healthy");
  const healthy = filtered.filter((d) => !d.incident_affected && d.health.primary === "healthy");

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Devices</h1>
        <p className="mt-1 text-zl-muted">
          Bad-first. Identity is network + IEEE address — never friendly name alone.
        </p>
      </div>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Select label="Network" value={network} onChange={setNetwork} options={options.networks} />
          <Select label="Health" value={health} onChange={setHealth} options={options.healths} labeller={healthLabel as (v: string) => string} />
          <Select label="Device type" value={deviceType} onChange={setDeviceType} options={options.types} labeller={deviceTypeLabel} />
          <Select label="Power source" value={power} onChange={setPower} options={options.powers} labeller={powerSourceLabel} />
          <Select label="Availability" value={availability} onChange={setAvailability} options={["online", "offline", "unknown"]} labeller={availabilityLabel as (v: string) => string} />
          <label className="flex flex-col gap-1 text-xs text-zl-muted">
            Search
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Friendly name or IEEE…"
              className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
            />
          </label>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm text-zl-muted">
          <input
            type="checkbox"
            checked={hasIncident}
            onChange={(e) => setHasIncident(e.target.checked)}
          />
          Only devices in an incident
        </label>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState title="No devices match" detail="Try clearing filters." />
      ) : (
        <>
          {concerning.length === 0 ? (
            <EmptyState title="No current device health concerns" />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {concerning.map((d) => (
                <DeviceHealthCard key={`${d.network_id}-${d.ieee_address}`} device={d} />
              ))}
            </div>
          )}

          {healthy.length > 0 && (
            <Card>
              <button
                type="button"
                onClick={() => setShowHealthy((v) => !v)}
                className="flex w-full items-center justify-between text-sm text-zl-muted"
              >
                <span>
                  {healthy.length} healthy device{healthy.length === 1 ? "" : "s"}
                </span>
                <span>{showHealthy ? "Hide" : "Show"}</span>
              </button>
              {showHealthy && (
                <ul className="mt-3 divide-y divide-zl-border">
                  {healthy.map((d) => (
                    <li key={`${d.network_id}-${d.ieee_address}`}>
                      <Link
                        to={`/devices/${d.network_id}/${encodeURIComponent(d.ieee_address)}`}
                        className="flex items-center justify-between gap-3 py-2 text-sm hover:text-zl-accent"
                      >
                        <span className="truncate">{d.friendly_name}</span>
                        <span className="flex items-center gap-2 text-xs text-zl-muted">
                          <NetworkBadge network={d.network_id} />
                          {deviceTypeLabel(d.device_type)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
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

function suggestsLine(device: DeviceDetail, related: Incident[]): string {
  const active = related.find((i) => i.status === "open" || i.status === "watching");
  if (active) {
    return "This device is part of a correlated incident ZigbeeLens is currently tracking.";
  }
  if (device.health.primary === "unknown") {
    return "ZigbeeLens has not observed enough data to classify this device yet.";
  }
  if (device.health.primary === "healthy") {
    return "This device currently looks healthy.";
  }
  return "This currently looks isolated to this device.";
}

export function DeviceDetailPage() {
  const { networkId, ieeeAddress } = useParams();
  const { scenario } = useScenario();
  const s = scenario || undefined;
  const ieee = ieeeAddress ? decodeURIComponent(ieeeAddress) : "";

  const detail = useLiveResource(
    () => api.device(networkId!, ieee, s),
    [networkId, ieeeAddress, scenario],
    { refetchOn: DEVICE_EVENTS, enabled: Boolean(networkId && ieeeAddress) },
  );
  const incidents = useLiveResource(
    () =>
      api
        .incidents(s)
        .then((r) =>
          r.items.filter((i) =>
            i.affected_devices.some(
              (d) => d.network_id === networkId && d.ieee_address === ieee,
            ),
          ),
        ),
    [networkId, ieeeAddress, scenario],
    { refetchOn: DEVICE_EVENTS, enabled: Boolean(networkId && ieeeAddress) },
  );

  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.refetch} />;
  if (detail.loading || !detail.data) return <LoadingState />;
  const device = detail.data;
  const related = incidents.data ?? [];
  const flags = (device.health.flags ?? []).filter((f) => f !== device.health.primary);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link to="/devices" className="text-sm text-zl-accent hover:underline">
          ← Devices
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{device.friendly_name}</h1>
          <HealthBadge primary={device.health.primary} />
          <SeverityBadge severity={device.health.severity} />
          <ConfidenceBadge confidence={device.health.confidence} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-zl-muted">
          <NetworkBadge network={device.network_id} />
          <span className="font-mono">{device.ieee_address}</span>
          <span>{deviceTypeLabel(device.device_type)}</span>
          <span>{powerSourceLabel(device.power_source)}</span>
        </div>
        {flags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {flags.map((f) => (
              <Badge key={f} severity="watch">
                {healthLabel(f)}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Identity">
          <dl className="space-y-2 text-sm">
            <Row label="Network" value={device.network_id} mono />
            <Row label="IEEE address" value={device.ieee_address} mono />
            <Row label="Friendly name" value={device.friendly_name} />
            <Row label="Manufacturer" value={device.manufacturer} />
            <Row label="Model" value={device.model} />
            <Row label="Definition" value={device.definition} />
            <Row label="Interview" value={interviewStateLabel(device.interview_state)} />
          </dl>
        </Card>
        <Card title="Telemetry">
          <dl className="space-y-2 text-sm">
            <Row label="Availability" value={availabilityLabel(device.availability)} />
            <Row label="Last seen" value={formatTime(device.last_seen)} />
            <Row label="Last payload" value={formatTime(device.last_payload_at)} />
            <Row label="Link quality" value={device.linkquality?.toString()} />
            <Row label="Battery" value={device.battery != null ? `${device.battery}%` : undefined} />
          </dl>
        </Card>
      </div>

      <Card title="Diagnostic conclusion">
        <p className="mb-3 text-lg leading-relaxed text-zl-text">{suggestsLine(device, related)}</p>
        {device.diagnostic.summary && (
          <p className="mb-4 text-sm text-zl-muted">{device.diagnostic.summary}</p>
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <EvidenceList items={device.diagnostic.evidence} emptyText="No supporting evidence yet." />
          <CounterEvidenceList items={device.diagnostic.counter_evidence} />
          <LimitationsList items={device.diagnostic.limitations} />
        </div>
      </Card>

      {related.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Related incidents
          </h2>
          <div className="grid gap-3">
            {related.map((inc) => {
              const ref = inc.affected_devices.find(
                (d) => d.network_id === device.network_id && d.ieee_address === device.ieee_address,
              );
              return (
                <div key={inc.id} className="space-y-1">
                  {ref && (
                    <div className="flex items-center gap-2 px-1">
                      <DeviceRoleBadge role="affected device" />
                      <span className="text-xs text-zl-muted">in this incident</span>
                    </div>
                  )}
                  <IncidentCard incident={inc} />
                </div>
              );
            })}
          </div>
        </section>
      )}

      {device.recent_availability_changes.length > 0 && (
        <Card title="Availability changes">
          <ul className="space-y-2 text-sm">
            {device.recent_availability_changes.map((c, i) => (
              <li key={i} className="flex items-center gap-3">
                <span className="font-mono text-xs text-zl-muted" title={formatTime(c.timestamp)}>
                  {formatTime(c.timestamp)}
                </span>
                <span>
                  <AvailabilityBadge availability={c.from} /> → <AvailabilityBadge availability={c.to} />
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {device.trends && device.trends.length > 0 && (
        <Card title="Recent metric samples">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-zl-muted">
                <tr>
                  <th className="py-2 pr-4 font-medium">Time</th>
                  <th className="py-2 pr-4 font-medium">LQI</th>
                  <th className="py-2 pr-4 font-medium">Battery</th>
                  <th className="py-2 font-medium">Availability</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zl-border">
                {device.trends.map((t, i) => (
                  <tr key={i}>
                    <td className="py-2 pr-4 font-mono text-xs text-zl-muted">{formatTime(t.timestamp)}</td>
                    <td className="py-2 pr-4">{t.linkquality ?? "—"}</td>
                    <td className="py-2 pr-4">{t.battery != null ? `${t.battery}%` : "—"}</td>
                    <td className="py-2">{t.availability ? availabilityLabel(t.availability) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {device.recent_bridge_logs.length > 0 && (
        <Card title="Bridge logs mentioning this device">
          <ul className="space-y-2 text-sm">
            {device.recent_bridge_logs.map((log, i) => (
              <li key={i} className="flex gap-3">
                <span className="font-mono text-xs text-zl-muted">{formatTime(log.timestamp)}</span>
                <Badge severity={log.level === "error" ? "incident" : log.level === "warning" ? "watch" : "healthy"}>
                  {log.level}
                </Badge>
                <span className="text-zl-muted">{log.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {device.recent_events.length > 0 && (
        <Card title="Recent events">
          <ul className="space-y-2 text-sm">
            {device.recent_events.map((e) => (
              <li key={e.id} className="flex gap-3">
                <span className="font-mono text-xs text-zl-muted">{formatTime(e.timestamp)}</span>
                <span>{e.title}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-zl-muted">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{value ?? "—"}</dd>
    </div>
  );
}
