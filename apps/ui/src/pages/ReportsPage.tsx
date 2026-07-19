import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  Incident,
  RedactionProfile,
  ReportFormat,
  ReportRequest,
  ReportScope,
} from "@zigbeelens/shared";
import {
  api,
  downloadStoredReport,
  triggerBrowserDownload,
  writeProtectedClipboardText,
} from "@/lib/api";
import { authRuntime } from "@/lib/authRuntime";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LimitationsList,
  LoadingState,
} from "@/components/ui";
import { InvestigationPriorityCard } from "@/components/overview/InvestigationPriorityCard";
import { DataCoverageWarningCard } from "@/components/overview/DataCoverageWarningCard";
import { EvidenceCoverageStrip } from "@/components/meshGraph/EvidenceCoverageStrip";
import { buildReportDecisionViewModel } from "@/viewModels/reports/reportDecisionViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

const INCIDENT_PICKER_LIMIT = 100;

/** Opaque session token — identity is by object reference, never by scenario text. */
function createOpaqueSession(): object {
  return Object.create(null);
}

type IncidentPickerKey = {
  readonly scenarioSession: object;
  readonly incidentEntryEpoch: number;
};

interface IncidentPickerPageState {
  pickerKey: IncidentPickerKey;
  options: Incident[];
  nextCursor: string | null;
  loadMoreError: string | null;
  loadingMore: boolean;
}

interface IncidentPickerSelection {
  pickerKey: IncidentPickerKey;
  incidentId: string;
}

interface IncidentPickerResource {
  pickerKey: IncidentPickerKey;
  page: {
    items: Incident[];
    total: number;
    limit?: number | null;
    next_cursor?: string | null;
  };
}

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
  { value: "full", label: "Full evidence" },
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
  const [deviceKey, setDeviceKey] = useState("");
  const [options, setOptions] = useState<OptionState>(PROFILE_DEFAULTS.standard);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // Opaque scenario session changes on every scenario transition (including A→B→A),
  // so returning to a prior scenario text never reuses the old picker identity.
  const [scenarioSession, setScenarioSession] = useState(createOpaqueSession);
  const [trackedScenario, setTrackedScenario] = useState(scenario);
  if (trackedScenario !== scenario) {
    setTrackedScenario(scenario);
    setScenarioSession(createOpaqueSession());
  }
  // Entry epoch changes on each Incident-scope entry so leave/re-enter is fresh
  // even when the scenario session is unchanged.
  const [incidentEntryEpoch, setIncidentEntryEpoch] = useState(0);
  const [incidentPickerState, setIncidentPickerState] =
    useState<IncidentPickerPageState | null>(null);
  const [incidentSelection, setIncidentSelection] =
    useState<IncidentPickerSelection | null>(null);
  const currentPickerKey = useMemo((): IncidentPickerKey | null => {
    if (scope !== "incident") return null;
    return { scenarioSession, incidentEntryEpoch };
  }, [scope, scenarioSession, incidentEntryEpoch]);
  const currentPickerKeyRef = useRef<IncidentPickerKey | null>(currentPickerKey);
  currentPickerKeyRef.current = currentPickerKey;

  useEffect(() => {
    setOptions(PROFILE_DEFAULTS[profile]);
  }, [profile]);

  function changeScope(next: ReportScope) {
    if (next === "incident" && scope !== "incident") {
      // New identity on every Incident-scope entry (including same scenario).
      setIncidentEntryEpoch((epoch) => epoch + 1);
    }
    setScope(next);
    if (next !== "network") setNetworkId("");
    if (next !== "device") setDeviceKey("");
  }

  const networksResource = useLiveResource(
    () => api.networks(scen).then((res) => res.items),
    [scenario, scope],
    {
      enabled: scope === "network",
      refetchOn: ["dashboard_updated", "incidents_updated"],
    },
  );
  const incidentsResource = useLiveResource(
    () => {
      const pickerKeyAtStart = currentPickerKeyRef.current;
      if (!pickerKeyAtStart) {
        return Promise.reject(new Error("Incident picker is not active"));
      }
      return api
        .incidents({ scenario: scen, limit: INCIDENT_PICKER_LIMIT })
        .then(
          (page): IncidentPickerResource => ({
            pickerKey: pickerKeyAtStart,
            page,
          }),
        );
    },
    [scenario, scope, incidentEntryEpoch, scenarioSession],
    {
      enabled: scope === "incident" && currentPickerKey != null,
      refetchOn: ["dashboard_updated", "incidents_updated"],
    },
  );
  useEffect(() => {
    if (!currentPickerKey || !incidentsResource.data) return;
    if (incidentsResource.data.pickerKey !== currentPickerKey) return;
    setIncidentPickerState({
      pickerKey: currentPickerKey,
      options: incidentsResource.data.page.items,
      nextCursor: incidentsResource.data.page.next_cursor ?? null,
      loadMoreError: null,
      loadingMore: false,
    });
  }, [incidentsResource.data, currentPickerKey]);

  const pickerMatches =
    currentPickerKey != null && incidentPickerState?.pickerKey === currentPickerKey;
  const incidentOptions = pickerMatches ? incidentPickerState.options : [];
  const incidentNextCursor = pickerMatches ? incidentPickerState.nextCursor : null;
  const incidentLoadingMore = pickerMatches ? incidentPickerState.loadingMore : false;
  const incidentLoadMoreError = pickerMatches ? incidentPickerState.loadMoreError : null;
  const effectiveIncidentId =
    currentPickerKey != null &&
    incidentSelection?.pickerKey === currentPickerKey &&
    incidentSelection.incidentId
      ? incidentSelection.incidentId
      : "";

  const loadMoreIncidents = useCallback(async () => {
    const pickerKey = currentPickerKeyRef.current;
    if (!pickerKey || !incidentNextCursor || incidentLoadingMore) return;
    const requestScenario = scen;
    const cursor = incidentNextCursor;
    setIncidentPickerState((prev) => {
      if (!prev || prev.pickerKey !== pickerKey) return prev;
      return { ...prev, loadingMore: true, loadMoreError: null };
    });
    try {
      const more = await api.incidents({
        scenario: requestScenario,
        limit: INCIDENT_PICKER_LIMIT,
        cursor,
      });
      if (pickerKey !== currentPickerKeyRef.current) {
        return;
      }
      setIncidentPickerState((prev) => {
        if (!prev || prev.pickerKey !== pickerKey) return prev;
        const seen = new Set(prev.options.map((inc) => inc.id));
        const appended = more.items.filter((inc) => !seen.has(inc.id));
        return {
          ...prev,
          options: [...prev.options, ...appended],
          nextCursor: more.next_cursor ?? null,
          loadingMore: false,
          loadMoreError: null,
        };
      });
    } catch (error) {
      if (pickerKey !== currentPickerKeyRef.current) {
        return;
      }
      setIncidentPickerState((prev) => {
        if (!prev || prev.pickerKey !== pickerKey) return prev;
        return {
          ...prev,
          loadingMore: false,
          loadMoreError: error instanceof Error ? error.message : String(error),
        };
      });
    }
  }, [incidentLoadingMore, incidentNextCursor, scen]);

  const devicesResource = useLiveResource(
    () => api.devices(scen).then((res) => res.items),
    [scenario, scope],
    {
      enabled: scope === "device",
      refetchOn: ["dashboard_updated", "incidents_updated"],
    },
  );

  const [deviceNetwork, deviceIeee] = deviceKey ? deviceKey.split("|") : ["", ""];

  const request: ReportRequest = useMemo(
    () => ({
      format,
      scope,
      network_id: scope === "network" ? networkId : scope === "device" ? deviceNetwork || null : null,
      incident_id: scope === "incident" ? effectiveIncidentId || null : null,
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
    [
      format,
      scope,
      networkId,
      effectiveIncidentId,
      deviceNetwork,
      deviceIeee,
      profile,
      options,
    ],
  );

  const targetReady =
    scope === "full" ||
    (scope === "incident" && !!effectiveIncidentId) ||
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
    const accessGeneration = authRuntime.getAccessGeneration();
    await writeProtectedClipboardText(preview.data.markdown_summary, accessGeneration);
    flash("Markdown summary copied.");
  }

  function clientDownload(filename: string, content: string, type: string) {
    const accessGeneration = authRuntime.getAccessGeneration();
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    try {
      if (accessGeneration !== authRuntime.getAccessGeneration()) return;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function copyStored(id: string) {
    const accessGeneration = authRuntime.getAccessGeneration();
    const detail = await api.report(id, scen);
    await writeProtectedClipboardText(detail.markdown_summary, accessGeneration);
    flash("Stored report markdown copied.");
  }

  async function deleteStored(id: string) {
    await api.deleteReport(id);
    setReloadKey((k) => k + 1);
    flash("Report deleted.");
  }

  async function downloadStored(id: string) {
    const file = await downloadStoredReport(id, scen);
    await triggerBrowserDownload(file);
    flash("Report download started.");
  }

  const report = preview.data;
  const reportVm = useMemo(
    () => (report ? buildReportDecisionViewModel(report) : null),
    [report],
  );

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Reports</h1>
        <p className="mt-1 text-zl-muted">
          Build a redacted evidence report using the same Device Story decisions and investigation
          priorities shown in ZigbeeLens.
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
                  onChange={(v) => changeScope(v as ReportScope)}
                />
              </Field>

              {scope === "network" && (
                <Field label="Network">
                  <NativeSelect
                    value={networkId}
                    onChange={setNetworkId}
                    placeholder="Select a network"
                    options={(networksResource.data ?? []).map((n) => ({
                      value: n.id,
                      label: `${n.name} (${n.id})`,
                    }))}
                  />
                </Field>
              )}
              {scope === "incident" && (
                <Field label="Incident">
                  {incidentsResource.error &&
                  (!incidentsResource.data ||
                    incidentsResource.data.pickerKey === currentPickerKey) ? (
                    <ErrorState
                      message={incidentsResource.error}
                      onRetry={incidentsResource.refetch}
                    />
                  ) : (
                    <>
                      {!pickerMatches &&
                      (incidentsResource.loading || !incidentsResource.data) ? (
                        <LoadingState label="Loading incidents…" />
                      ) : null}
                      <NativeSelect
                        ariaLabel="Incident"
                        value={effectiveIncidentId}
                        onChange={(id) => {
                          if (!currentPickerKey) return;
                          setIncidentSelection({
                            pickerKey: currentPickerKey,
                            incidentId: id,
                          });
                        }}
                        placeholder="Select an incident"
                        options={incidentOptions.map((i) => ({
                          value: i.id,
                          label: i.title,
                        }))}
                      />
                      {incidentNextCursor ? (
                        <div className="mt-2 flex flex-col items-start gap-1">
                          <button
                            type="button"
                            onClick={() => void loadMoreIncidents()}
                            disabled={incidentLoadingMore}
                            className="rounded-lg border border-zl-border bg-zl-panel px-3 py-1.5 text-xs text-zl-text hover:border-zl-accent disabled:opacity-60"
                          >
                            {incidentLoadingMore ? "Loading…" : "Load more incidents"}
                          </button>
                          {incidentLoadMoreError ? (
                            <p className="text-xs text-zl-danger">{incidentLoadMoreError}</p>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  )}
                </Field>
              )}
              {scope === "device" && (
                <Field label="Device">
                  <NativeSelect
                    value={deviceKey}
                    onChange={setDeviceKey}
                    placeholder="Select a device"
                    options={(devicesResource.data ?? []).map((d) => ({
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
            ) : preview.loading || !report || !reportVm ? (
              <LoadingState label="Building preview…" />
            ) : (
              <div className="space-y-5">
                {reportVm.isLegacyFormat ? (
                  <div className="rounded-lg border border-zl-border/70 bg-zl-surface-2/50 p-3 text-sm text-zl-muted">
                    {reportVm.legacyNotice}
                  </div>
                ) : (
                  <>
                    <div className="space-y-3">
                      <p className="text-sm text-zl-muted">
                        {reportVm.scopeLabel} report · format v{reportVm.reportVersion}
                      </p>
                      {reportVm.decisionSummaryItems.length > 0 && (
                        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                          {reportVm.decisionSummaryItems.map((item) => (
                            <Stat key={item.key} label={item.label} value={item.count} />
                          ))}
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                        <Stat label="Networks in scope" value={reportVm.networksInScope} />
                        <Stat label="Devices in scope" value={reportVm.devicesInScope} />
                        <Stat label="Incidents in scope" value={reportVm.incidentsInScope} />
                      </div>
                    </div>

                    {reportVm.investigationPriorities.length > 0 && (
                      <section className="space-y-3" aria-label="What to check first">
                        <h3 className="text-sm font-medium text-zl-text">What to check first</h3>
                        <div className="grid gap-4">
                          {reportVm.investigationPriorities.map((priority, index) => (
                            <InvestigationPriorityCard
                              key={priority.id}
                              priority={priority}
                              emphasized={index === 0}
                              showMeshLink={reportVm.meshNavigationAvailable}
                            />
                          ))}
                        </div>
                      </section>
                    )}

                    {reportVm.deviceStories.length > 0 && (
                      <section className="space-y-3" aria-label="Device stories">
                        <h3 className="text-sm font-medium text-zl-text">Device stories</h3>
                        <div className="space-y-4">
                          {reportVm.deviceStories.map((deviceStory) => (
                            <ReportDeviceStoryPreview
                              key={deviceStory.key}
                              name={deviceStory.name}
                              networkId={deviceStory.networkId}
                              story={deviceStory.story}
                            />
                          ))}
                        </div>
                      </section>
                    )}

                    {reportVm.networkCoverage.length > 0 && (
                      <section className="space-y-3" aria-label="Data coverage">
                        <h3 className="text-sm font-medium text-zl-text">Data coverage</h3>
                        <div className="grid gap-4 md:grid-cols-2">
                          {reportVm.networkCoverage.map((warning) => (
                            <DataCoverageWarningCard
                              key={warning.id}
                              warning={warning}
                              showMeshLink={reportVm.meshNavigationAvailable}
                            />
                          ))}
                        </div>
                      </section>
                    )}
                  </>
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
                    <button
                      type="button"
                      onClick={() => void downloadStored(r.id)}
                      className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 active:bg-zl-surface-2"
                    >
                      Download
                    </button>
                    <button
                      type="button"
                      onClick={() => copyStored(r.id)}
                      className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 active:bg-zl-surface-2"
                    >
                      Copy MD
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteStored(r.id)}
                      className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm text-zl-muted hover:bg-zl-surface-2 active:bg-zl-surface-2"
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

function statusPillClassName(tone: DecisionPillTone): string {
  if (tone === "coverage") {
    return "inline-flex items-center rounded-full border border-zl-unavailable/40 bg-zl-unavailable/10 px-2 py-0.5 text-[11px] font-medium text-zl-unavailable";
  }
  if (tone === "watch") {
    return "inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-2 py-0.5 text-[11px] font-medium text-zl-watch";
  }
  if (tone === "action") {
    return "inline-flex items-center rounded-full border border-zl-accent/40 bg-zl-accent/10 px-2 py-0.5 text-[11px] font-medium text-zl-accent";
  }
  if (tone === "info") {
    return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-text";
  }
  return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-muted";
}

function ReportDeviceStoryPreview({
  name,
  networkId,
  story,
}: {
  name: string;
  networkId: string;
  story: import("@/viewModels/topology/deviceStoryViewModel").DeviceStoryViewModel;
}) {
  return (
    <div
      data-testid="report-device-story"
      className="rounded-lg border border-zl-border/70 bg-zl-bg p-4"
    >
      <p className="text-xs text-zl-muted">
        {name} · {networkId}
      </p>
      <div className="mt-2">
        {story.statusPill && (
          <span className={statusPillClassName(story.statusPill.tone)}>
            {story.statusPill.label}
          </span>
        )}
        <p className="mt-2 text-sm font-semibold text-zl-text">{story.headline}</p>
        <p className="mt-0.5 text-xs text-zl-muted">{story.headlineLead}</p>
      </div>

      {story.reasons.length > 0 && (
        <div className="mt-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
            {story.whyTitle}
          </h4>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
            {story.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {story.limitations.length > 0 && (
        <div className="mt-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
            {story.limitationsTitle}
          </h4>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-muted">
            {story.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}

      {story.suggestedChecks.length > 0 && (
        <div className="mt-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
            {story.checksTitle}
          </h4>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
            {story.suggestedChecks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
      )}

      {story.coverageItems.length > 0 && (
        <div className="mt-3">
          <EvidenceCoverageStrip title={story.coverageTitle} items={story.coverageItems} />
        </div>
      )}
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
          className={`min-h-11 rounded-lg px-4 py-2 text-sm ${
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
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
  ariaLabel?: string;
}) {
  return (
    <select
      aria-label={ariaLabel}
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
