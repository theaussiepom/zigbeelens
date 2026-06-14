import { useEffect, useMemo, useState } from "react";
import type {
  RedactionProfile,
  ReportFormat,
  ReportRequest,
  ReportScope,
} from "@zigbeelens/shared";
import { api, downloadReportUrl } from "@/lib/api";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LimitationsList,
  LoadingState,
  SeverityBadge,
} from "@/components/ui";

interface OptionState {
  preserveFriendly: boolean;
  hashIeee: boolean;
  redactHostnames: boolean;
  redactIp: boolean;
  redactNetworkNames: boolean;
  includeTimeline: boolean;
  includeRaw: boolean;
}

const PROFILE_DEFAULTS: Record<RedactionProfile, OptionState> = {
  standard: {
    preserveFriendly: true,
    hashIeee: true,
    redactHostnames: false,
    redactIp: false,
    redactNetworkNames: false,
    includeTimeline: true,
    includeRaw: false,
  },
  strict: {
    preserveFriendly: false,
    hashIeee: true,
    redactHostnames: true,
    redactIp: true,
    redactNetworkNames: true,
    includeTimeline: true,
    includeRaw: false,
  },
  public_safe: {
    preserveFriendly: false,
    hashIeee: true,
    redactHostnames: true,
    redactIp: true,
    redactNetworkNames: true,
    includeTimeline: true,
    includeRaw: false,
  },
};

const SCOPES: { value: ReportScope; label: string }[] = [
  { value: "full", label: "Full diagnostic" },
  { value: "incident", label: "Incident" },
  { value: "network", label: "Network" },
  { value: "device", label: "Device" },
];

const FORMATS: { value: ReportFormat; label: string }[] = [
  { value: "json", label: "JSON" },
  { value: "yaml", label: "YAML" },
  { value: "markdown", label: "Markdown" },
];

const PROFILES: { value: RedactionProfile; label: string; hint: string }[] = [
  { value: "standard", label: "Standard", hint: "Secrets redacted, names preserved" },
  { value: "public_safe", label: "Public safe", hint: "Best for GitHub / forums" },
  { value: "strict", label: "Strict", hint: "Most private" },
];

export function ReportsPage() {
  const { scenario } = useScenario();
  const scen = scenario || undefined;

  const [scope, setScope] = useState<ReportScope>("full");
  const [format, setFormat] = useState<ReportFormat>("json");
  const [profile, setProfile] = useState<RedactionProfile>("standard");
  const [networkId, setNetworkId] = useState("");
  const [incidentId, setIncidentId] = useState("");
  const [deviceKey, setDeviceKey] = useState("");
  const [options, setOptions] = useState<OptionState>(PROFILE_DEFAULTS.standard);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    setOptions(PROFILE_DEFAULTS[profile]);
  }, [profile]);

  const selectors = useLiveResource(
    async () => {
      const [networks, incidents, devices] = await Promise.all([
        api.networks(scen),
        api.incidents(scen),
        api.devices(scen),
      ]);
      return {
        networks: networks.items,
        incidents: incidents.items,
        devices: devices.items,
      };
    },
    [scenario],
    { refetchOn: ["dashboard_updated", "incidents_updated"] },
  );

  const [deviceNetwork, deviceIeee] = deviceKey ? deviceKey.split("|") : ["", ""];

  const request: ReportRequest = useMemo(
    () => ({
      format,
      scope,
      network_id: scope === "network" ? networkId : scope === "device" ? deviceNetwork || null : null,
      incident_id: scope === "incident" ? incidentId : null,
      device: scope === "device" ? deviceIeee || null : null,
      redaction: {
        profile,
        preserve_friendly_names: options.preserveFriendly,
        hash_ieee_addresses: options.hashIeee,
        redact_hostnames: options.redactHostnames,
        redact_ip_addresses: options.redactIp,
        redact_network_names: options.redactNetworkNames,
        include_timeline: options.includeTimeline,
        include_raw_payloads: options.includeRaw,
      },
    }),
    [format, scope, networkId, incidentId, deviceNetwork, deviceIeee, profile, options],
  );

  const targetReady =
    scope === "full" ||
    (scope === "incident" && !!incidentId) ||
    (scope === "network" && !!networkId) ||
    (scope === "device" && !!deviceIeee);

  const requestKey = JSON.stringify({ request, scenario });
  const preview = useLiveResource(
    () => api.previewReport(request, scen),
    [requestKey],
    { refetchOn: ["dashboard_updated", "incidents_updated"], enabled: targetReady },
  );

  const stored = useLiveResource(() => api.listReports(), [reloadKey]);

  function flash(message: string) {
    setToast(message);
    setTimeout(() => setToast(null), 2500);
  }

  async function generate() {
    setBusy(true);
    try {
      await api.createReport(request, scen);
      setReloadKey((k) => k + 1);
      flash("Report generated and stored.");
    } catch {
      flash("Could not generate report.");
    } finally {
      setBusy(false);
    }
  }

  async function copyMarkdown() {
    if (!preview.data) return;
    await navigator.clipboard.writeText(preview.data.markdown_summary);
    flash("Markdown summary copied.");
  }

  function clientDownload(filename: string, content: string, type: string) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyStored(id: string) {
    const detail = await api.report(id, scen);
    await navigator.clipboard.writeText(detail.markdown_summary);
    flash("Stored report markdown copied.");
  }

  async function deleteStored(id: string) {
    await api.deleteReport(id);
    setReloadKey((k) => k + 1);
    flash("Report deleted.");
  }

  const report = preview.data;

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Reports</h1>
        <p className="mt-1 text-zl-muted">
          Build a safe, shareable diagnostic snapshot for GitHub issues, Home Assistant community
          posts, Zigbee2MQTT discussions, or your own notes.
        </p>
      </div>

      <div className="rounded-lg border border-zl-border bg-zl-surface-2/40 p-4 text-sm text-zl-muted">
        <p>
          Reports are generated from ZigbeeLens&rsquo; observed MQTT and diagnostic history. They
          are <strong className="text-zl-text">evidence-backed snapshots, not root-cause proof.</strong>
        </p>
        <p className="mt-1">
          Secrets &mdash; MQTT passwords, tokens, and network keys &mdash; are redacted before any
          report is stored or downloaded.
        </p>
      </div>

      {toast && (
        <div className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-2 text-sm text-zl-accent">
          {toast}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <Card title="Report type">
            <div className="space-y-4">
              <Field label="Scope">
                <Segmented
                  options={SCOPES}
                  value={scope}
                  onChange={(v) => setScope(v as ReportScope)}
                />
              </Field>

              {scope === "network" && (
                <Field label="Network">
                  <NativeSelect
                    value={networkId}
                    onChange={setNetworkId}
                    placeholder="Select a network"
                    options={(selectors.data?.networks ?? []).map((n) => ({
                      value: n.id,
                      label: `${n.name} (${n.id})`,
                    }))}
                  />
                </Field>
              )}
              {scope === "incident" && (
                <Field label="Incident">
                  <NativeSelect
                    value={incidentId}
                    onChange={setIncidentId}
                    placeholder="Select an incident"
                    options={(selectors.data?.incidents ?? []).map((i) => ({
                      value: i.id,
                      label: i.title,
                    }))}
                  />
                </Field>
              )}
              {scope === "device" && (
                <Field label="Device">
                  <NativeSelect
                    value={deviceKey}
                    onChange={setDeviceKey}
                    placeholder="Select a device"
                    options={(selectors.data?.devices ?? []).map((d) => ({
                      value: `${d.network_id}|${d.ieee_address}`,
                      label: `${d.friendly_name} · ${d.network_id}`,
                    }))}
                  />
                </Field>
              )}

              <Field label="Format">
                <Segmented
                  options={FORMATS}
                  value={format}
                  onChange={(v) => setFormat(v as ReportFormat)}
                />
              </Field>
            </div>
          </Card>

          <Card title="Redaction profile" subtitle="Standard is safe by default.">
            <div className="space-y-2">
              {PROFILES.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setProfile(p.value)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${
                    profile === p.value
                      ? "border-zl-accent bg-zl-accent/10 text-zl-text"
                      : "border-zl-border text-zl-muted hover:bg-zl-surface-2"
                  }`}
                >
                  <span className="font-medium">{p.label}</span>
                  <span className="text-xs text-zl-muted">{p.hint}</span>
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-2 border-t border-zl-border/60 pt-4">
              <Toggle
                label="Preserve friendly names"
                checked={options.preserveFriendly}
                onChange={(v) => setOptions((o) => ({ ...o, preserveFriendly: v }))}
              />
              <Toggle
                label="Hash IEEE addresses"
                checked={options.hashIeee}
                onChange={(v) => setOptions((o) => ({ ...o, hashIeee: v }))}
              />
              <Toggle
                label="Redact hostnames"
                checked={options.redactHostnames}
                onChange={(v) => setOptions((o) => ({ ...o, redactHostnames: v }))}
              />
              <Toggle
                label="Redact IP addresses"
                checked={options.redactIp}
                onChange={(v) => setOptions((o) => ({ ...o, redactIp: v }))}
              />
              <Toggle
                label="Redact network names"
                checked={options.redactNetworkNames}
                onChange={(v) => setOptions((o) => ({ ...o, redactNetworkNames: v }))}
              />
              <Toggle
                label="Include recent timeline"
                checked={options.includeTimeline}
                onChange={(v) => setOptions((o) => ({ ...o, includeTimeline: v }))}
              />
              <Toggle
                label="Include raw redacted payload snippets"
                checked={options.includeRaw}
                onChange={(v) => setOptions((o) => ({ ...o, includeRaw: v }))}
              />
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title="Preview"
            subtitle="Live preview reflects the selected scope and redaction profile."
            actions={
              report ? (
                <Badge severity={report.redaction.applied ? "healthy" : "watch"}>
                  {report.redaction.profile}
                </Badge>
              ) : undefined
            }
          >
            {!targetReady ? (
              <EmptyState
                title="Choose a target"
                detail="Select a network, incident, or device to preview a scoped report."
              />
            ) : preview.error ? (
              <ErrorState message={preview.error} onRetry={preview.refetch} />
            ) : preview.loading || !report ? (
              <LoadingState label="Building preview…" />
            ) : (
              <div className="space-y-5">
                {report.summary && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={report.summary.overall_state} />
                      <span className="text-sm text-zl-muted">
                        {report.scope} report · v{report.version}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed text-zl-text">
                      {report.summary.current_finding}
                    </p>
                    <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                      <Stat label="Networks" value={report.summary.networks_monitored} />
                      <Stat label="Devices" value={report.summary.total_devices} />
                      <Stat label="Active incidents" value={report.summary.active_incidents} />
                      <Stat label="Router risks" value={report.summary.router_risks} />
                      <Stat label="Unavailable" value={report.summary.unavailable_devices} />
                      <Stat label="Stale" value={report.summary.stale_devices} />
                      <Stat label="Weak links" value={report.summary.weak_links} />
                      <Stat label="Low battery" value={report.summary.low_battery_devices} />
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={generate}
                    disabled={busy}
                    className="rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-zl-bg hover:opacity-90 disabled:opacity-50"
                  >
                    {busy ? "Generating…" : "Generate & store report"}
                  </button>
                  <button
                    type="button"
                    onClick={copyMarkdown}
                    className="rounded-lg bg-zl-accent/20 px-4 py-2 text-sm font-medium text-zl-accent hover:bg-zl-accent/30"
                  >
                    Copy Markdown summary
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      clientDownload(
                        "zigbeelens-report.json",
                        JSON.stringify(report, null, 2),
                        "application/json",
                      )
                    }
                    className="rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
                  >
                    Download JSON
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      clientDownload(
                        "zigbeelens-report.md",
                        report.markdown_summary,
                        "text/markdown",
                      )
                    }
                    className="rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
                  >
                    Download Markdown
                  </button>
                </div>

                <RedactionSummary report={report} />

                {report.limitations.length > 0 && (
                  <div>
                    <h3 className="mb-2 text-sm font-medium text-zl-text">Limitations</h3>
                    <LimitationsList items={report.limitations} />
                  </div>
                )}

                <div>
                  <h3 className="mb-2 text-sm font-medium text-zl-text">Markdown preview</h3>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-zl-border bg-zl-bg p-3 font-mono text-xs text-zl-muted">
                    {report.markdown_summary}
                  </pre>
                </div>
              </div>
            )}
          </Card>

          <Card title="Stored reports" subtitle="Locally saved snapshots. Nothing leaves your machine automatically.">
            {stored.error ? (
              <ErrorState message={stored.error} onRetry={stored.refetch} />
            ) : stored.loading ? (
              <LoadingState label="Loading reports…" />
            ) : (stored.data ?? []).length === 0 ? (
              <EmptyState
                title="No stored reports yet"
                detail="Generate a report to keep a snapshot you can download or copy later."
              />
            ) : (
              <ul className="divide-y divide-zl-border/60">
                {(stored.data ?? []).map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-zl-text">{r.summary}</p>
                      <p className="text-xs text-zl-muted" title={r.generated_at}>
                        {r.generated_at} · {r.scope} · {r.format.toUpperCase()} · {r.redaction_profile}
                      </p>
                    </div>
                    <a
                      href={downloadReportUrl(r.id, scen)}
                      className="rounded-lg border border-zl-border px-3 py-1.5 text-xs hover:bg-zl-surface-2"
                    >
                      Download
                    </a>
                    <button
                      type="button"
                      onClick={() => copyStored(r.id)}
                      className="rounded-lg border border-zl-border px-3 py-1.5 text-xs hover:bg-zl-surface-2"
                    >
                      Copy MD
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteStored(r.id)}
                      className="rounded-lg border border-zl-border px-3 py-1.5 text-xs text-zl-muted hover:bg-zl-surface-2"
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function RedactionSummary({ report }: { report: import("@zigbeelens/shared").ReportDetail }) {
  const r = report.redaction;
  const rows: [string, string][] = [
    ["Profile", r.profile],
    ["MQTT credentials", "Redacted"],
    ["Secrets / tokens / keys", "Redacted"],
    ["Hostnames", r.hostnames ? "Redacted" : "Preserved"],
    ["IP addresses", r.ip_addresses ? "Redacted" : "Preserved"],
    ["IEEE addresses", r.ieee_addresses_hashed ? "Hashed" : "Preserved"],
    ["Friendly names", r.friendly_names],
    ["Network names", r.network_names],
  ];
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-zl-text">Redaction summary</h3>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex justify-between gap-4 border-b border-zl-border/40 pb-1"
          >
            <dt className="text-zl-muted">{label}</dt>
            <dd className="capitalize text-zl-text">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-zl-muted">{label}</span>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-sm ${
            value === o.value
              ? "bg-zl-accent text-zl-bg"
              : "border border-zl-border text-zl-muted hover:bg-zl-surface-2"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function NativeSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-zl-text">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-zl-accent"
      />
    </label>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-zl-border/60 bg-zl-bg px-3 py-2">
      <p className="text-lg font-semibold text-zl-text">{value}</p>
      <p className="text-xs text-zl-muted">{label}</p>
    </div>
  );
}
