import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  AvailabilityBadge,
  Badge,
  Card,
  DeviceRoleBadge,
  EmptyState,
  ErrorState,
  LoadingState,
  NetworkBadge,
} from "@/components/ui";
import { DeviceDecisionBadge } from "@/components/devices/DeviceDecisionBadge";
import { DeviceStorySection } from "@/components/meshGraph/DeviceStorySection";
import { DeviceSnapshotHistory } from "@/components/meshGraph/DeviceSnapshotHistory";
import { IncidentCard } from "@/components/cards";
import {
  availabilityLabel,
  deviceTypeLabel,
  formatTime,
  interviewStateLabel,
  powerSourceLabel,
} from "@/lib/format";
import {
  DEVICE_DECISION_FILTER_OPTIONS,
  buildDeviceInventoryRows,
  deviceInventorySummaryCounts,
  filterDeviceInventoryRows,
  type DeviceRowViewModel,
} from "@/viewModels/devices/deviceRowViewModel";
import { buildDeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";

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
  const [decisionStatus, setDecisionStatus] = useState("");
  const [availability, setAvailability] = useState("");
  const [coverageFilter, setCoverageFilter] = useState<"" | "limitations">("");
  const [search, setSearch] = useState("");

  useEffect(() => setNetwork(initialNetwork), [initialNetwork]);

  const devices = data ?? [];

  const inventoryRows = useMemo(
    () => buildDeviceInventoryRows(devices),
    [devices],
  );

  const options = useMemo(() => {
    const networks = new Set<string>();
    for (const d of devices) {
      networks.add(d.network_id);
    }
    return {
      networks: [...networks].sort(),
    };
  }, [devices]);

  const filtered = useMemo(
    () =>
      filterDeviceInventoryRows(inventoryRows, {
        networkId: network,
        decisionStatus,
        availability,
        coverageFilter,
        search,
      }),
    [inventoryRows, network, decisionStatus, availability, coverageFilter, search],
  );

  const summary = useMemo(
    () => deviceInventorySummaryCounts(inventoryRows),
    [inventoryRows],
  );

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading) return <LoadingState />;

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Devices</h1>
        <p className="mt-1 text-zl-muted">
          Inventory with Device Story decisions — search, filter, and open device detail.
        </p>
        <p className="mt-2 text-sm text-zl-muted">
          {summary.total} device{summary.total === 1 ? "" : "s"}
          {" · "}
          {summary.reviewFirst} review first
          {" · "}
          {summary.worthReviewing} worth reviewing
          {" · "}
          {summary.coverage} with coverage limitations
        </p>
      </div>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Select
            label="Network"
            value={network}
            onChange={setNetwork}
            options={options.networks}
          />
          <label className="flex flex-col gap-1 text-xs text-zl-muted">
            Decision
            <select
              value={decisionStatus}
              onChange={(e) => setDecisionStatus(e.target.value)}
              className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
            >
              <option value="">All decisions</option>
              {DEVICE_DECISION_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <Select
            label="Availability"
            value={availability}
            onChange={setAvailability}
            options={["online", "offline", "unknown"]}
            labeller={availabilityLabel as (v: string) => string}
            allLabel="All availability"
          />
          <label className="flex flex-col gap-1 text-xs text-zl-muted">
            Coverage
            <select
              value={coverageFilter}
              onChange={(e) =>
                setCoverageFilter(e.target.value === "limitations" ? "limitations" : "")
              }
              className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
            >
              <option value="">All coverage</option>
              <option value="limitations">Coverage limitations</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-zl-muted sm:col-span-2">
            Search
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name, IEEE, manufacturer, model, area…"
              className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
            />
          </label>
        </div>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState title="No devices match" detail="Try clearing filters." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-zl-border bg-zl-surface shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-zl-border bg-zl-surface-2 text-xs uppercase tracking-wide text-zl-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Device</th>
                  <th className="px-4 py-3 font-medium">Decision</th>
                  <th className="hidden px-4 py-3 font-medium md:table-cell">
                    Availability / coverage
                  </th>
                  <th className="hidden px-4 py-3 font-medium lg:table-cell">
                    Battery / LQI
                  </th>
                  <th className="hidden px-4 py-3 font-medium sm:table-cell">Last seen</th>
                  <th className="hidden px-4 py-3 font-medium xl:table-cell">
                    Area / model
                  </th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zl-border">
                {filtered.map((row) => (
                  <DeviceInventoryRow key={row.key} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function DeviceInventoryRow({ row }: { row: DeviceRowViewModel }) {
  return (
    <tr className="align-top">
      <td className="px-4 py-3">
        <div className="font-medium text-zl-text">{row.name}</div>
        <div className="mt-0.5 text-xs text-zl-muted">{row.secondaryLabel}</div>
        <div className="mt-2 space-y-1 md:hidden">
          <div className="text-xs text-zl-muted">
            {row.availabilityLabel}
            {row.coverageSummary ? ` · ${row.coverageSummary}` : ""}
          </div>
          <div className="text-xs text-zl-muted">
            {row.batterySummary} · {row.lqiSummary}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <DeviceDecisionBadge decision={row.decision} />
        <p className="mt-1 max-w-[14rem] text-xs text-zl-muted">{row.decision.headline}</p>
      </td>
      <td className="hidden px-4 py-3 md:table-cell">
        <div className="text-zl-text">{row.availabilityLabel}</div>
        {row.coverageSummary && (
          <div className="mt-1 text-xs text-zl-muted">{row.coverageSummary}</div>
        )}
      </td>
      <td className="hidden px-4 py-3 text-zl-muted lg:table-cell">
        <div>{row.batterySummary}</div>
        <div>{row.lqiSummary}</div>
      </td>
      <td
        className="hidden px-4 py-3 text-zl-muted sm:table-cell"
        title={row.lastSeenExact}
      >
        {row.lastSeenLabel}
      </td>
      <td className="hidden px-4 py-3 xl:table-cell">
        {row.areaLabel && <div className="text-zl-text">{row.areaLabel}</div>}
        <div className={row.areaLabel ? "mt-0.5 text-xs text-zl-muted" : "text-zl-muted"}>
          {row.modelLabel}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1 text-sm">
          <Link to={row.deviceHref} className="text-zl-accent hover:underline">
            View device →
          </Link>
          <Link to={row.meshHref} className="text-xs text-zl-muted hover:text-zl-accent">
            Review in Mesh
          </Link>
        </div>
      </td>
    </tr>
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
        .incidents({
          scenario: s,
          network_id: networkId!,
          device_ieee: ieee,
          limit: 50,
        })
        .then((r) => r.items),
    [networkId, ieeeAddress, scenario],
    { refetchOn: DEVICE_EVENTS, enabled: Boolean(networkId && ieeeAddress) },
  );

  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.refetch} />;
  if (detail.loading || !detail.data) return <LoadingState />;
  const device = detail.data;
  const related = incidents.data ?? [];
  const decision = buildDeviceDecisionBadgeViewModel(device.decision);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link to="/devices" className="text-sm text-zl-accent hover:underline">
          ← Devices
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{device.friendly_name}</h1>
          <DeviceDecisionBadge decision={decision} />
        </div>
        <p className="mt-2 text-sm font-medium text-zl-text">{decision.headline}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-zl-muted">
          <NetworkBadge network={device.network_id} />
          <span className="break-all font-mono">{device.ieee_address}</span>
          <span>{deviceTypeLabel(device.device_type)}</span>
          <span>{powerSourceLabel(device.power_source)}</span>
        </div>
      </div>

      {networkId && ieee && (
        <Card>
          <DeviceStorySection networkId={networkId} deviceIeee={ieee} scenario={s} />
        </Card>
      )}

      {networkId && ieee && (
        <Card>
          <DeviceSnapshotHistory
            networkId={networkId}
            deviceIeee={ieee}
            showHeading
            showRawSnapshotLink
          />
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Current state">
          <dl className="space-y-2 text-sm">
            <Row label="Availability" value={availabilityLabel(device.availability)} />
            <Row label="Last seen" value={formatTime(device.last_seen)} />
            <Row label="Last payload" value={formatTime(device.last_payload_at)} />
            <Row
              label="Battery"
              value={device.battery != null ? `${device.battery}%` : undefined}
            />
            <Row label="LQI" value={device.linkquality?.toString()} />
          </dl>
        </Card>
        <Card title="Identity">
          <dl className="space-y-2 text-sm">
            <Row label="Network" value={device.network_id} mono />
            <Row label="IEEE address" value={device.ieee_address} mono />
            <Row label="Friendly name" value={device.friendly_name} />
            <Row label="Area" value={device.ha_area} />
            <Row label="Manufacturer" value={device.manufacturer} />
            <Row label="Model" value={device.model} />
            <Row label="Device type" value={deviceTypeLabel(device.device_type)} />
            <Row label="Power source" value={powerSourceLabel(device.power_source)} />
            <Row label="Interview" value={interviewStateLabel(device.interview_state)} />
            <Row label="Definition" value={device.definition} />
          </dl>
        </Card>
      </div>

      {related.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
            Related incidents
          </h2>
          <div className="grid gap-3">
            {related.map((inc) => {
              const ref = inc.affected_devices.find(
                (d) =>
                  d.network_id === device.network_id && d.ieee_address === device.ieee_address,
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
                  <AvailabilityBadge availability={c.from} /> →{" "}
                  <AvailabilityBadge availability={c.to} />
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
                    <td className="py-2 pr-4 font-mono text-xs text-zl-muted">
                      {formatTime(t.timestamp)}
                    </td>
                    <td className="py-2 pr-4">{t.linkquality ?? "—"}</td>
                    <td className="py-2 pr-4">
                      {t.battery != null ? `${t.battery}%` : "—"}
                    </td>
                    <td className="py-2">
                      {t.availability ? availabilityLabel(t.availability) : "—"}
                    </td>
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
                <Badge
                  severity={
                    log.level === "error"
                      ? "incident"
                      : log.level === "warning"
                        ? "watch"
                        : "healthy"
                  }
                >
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
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
      <dt className="shrink-0 text-zl-muted">{label}</dt>
      <dd
        className={
          mono ? "min-w-0 break-all text-right font-mono" : "min-w-0 break-words text-right"
        }
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}
