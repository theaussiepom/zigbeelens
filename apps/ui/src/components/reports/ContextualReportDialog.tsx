import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { RedactionProfile, ReportFormat, ReportSummary } from "@zigbeelens/shared";
import {
  api,
  downloadStoredReport,
  triggerBrowserDownload,
  writeProtectedClipboardText,
} from "@/lib/api";
import { authRuntime } from "@/lib/authRuntime";
import { Badge, Card, ErrorState, LoadingState } from "@/components/ui";
import {
  CONTEXTUAL_REPORT_PROFILE_DEFAULTS,
  buildContextualReportRequest,
  scopeLabel,
  type ContextualReportOptions,
  type ContextualReportTarget,
} from "@/reports/contextualReportTarget";

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

type DialogPhase =
  | { kind: "idle" }
  | { kind: "creating" }
  | { kind: "created"; summary: ReportSummary }
  | { kind: "created_download_failed"; summary: ReportSummary; message: string }
  | { kind: "create_failed"; message: string };

export function ContextualReportDialog({
  target,
  scenario,
  open,
  onClose,
  onCreated,
  returnFocusRef,
}: {
  target: ContextualReportTarget;
  scenario?: string;
  open: boolean;
  onClose: () => void;
  onCreated?: (summary: ReportSummary) => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const titleId = useId();
  const descId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const operationIdRef = useRef(0);
  const creatingRef = useRef(false);

  const [format, setFormat] = useState<ReportFormat>("json");
  const [profile, setProfile] = useState<RedactionProfile>("standard");
  const [options, setOptions] = useState(
    () => CONTEXTUAL_REPORT_PROFILE_DEFAULTS.standard,
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [phase, setPhase] = useState<DialogPhase>({ kind: "idle" });
  const [preview, setPreview] = useState<{
    loading: boolean;
    error: string | null;
    data: Awaited<ReturnType<typeof api.previewReport>> | null;
  }>({ loading: false, error: null, data: null });

  const reportOptions: ContextualReportOptions = useMemo(
    () => ({ format, profile, ...options }),
    [format, profile, options],
  );
  const request = useMemo(
    () => buildContextualReportRequest(target, reportOptions),
    [target, reportOptions],
  );
  const requestKey = useMemo(
    () => JSON.stringify({ target, scenario, request }),
    [target, scenario, request],
  );

  const targetKey = useMemo(() => JSON.stringify(target), [target]);
  const [openEpoch, setOpenEpoch] = useState(0);
  const [trackedOpen, setTrackedOpen] = useState(false);
  const [trackedTargetKey, setTrackedTargetKey] = useState(targetKey);
  const [trackedScenario, setTrackedScenario] = useState(scenario);

  if (open !== trackedOpen || targetKey !== trackedTargetKey || scenario !== trackedScenario) {
    setTrackedOpen(open);
    setTrackedTargetKey(targetKey);
    setTrackedScenario(scenario);
    if (open) {
      setOpenEpoch((n) => n + 1);
      setFormat("json");
      setProfile("standard");
      setOptions(CONTEXTUAL_REPORT_PROFILE_DEFAULTS.standard);
      setAdvancedOpen(false);
      setPhase({ kind: "idle" });
    }
  }

  // One preview request while open; invalidated by target/scenario/options changes.
  useEffect(() => {
    if (!open) return;
    operationIdRef.current += 1;
    creatingRef.current = false;
    const op = operationIdRef.current;
    setPreview({ loading: true, error: null, data: null });
    void api
      .previewReport(request, scenario)
      .then((data) => {
        if (op !== operationIdRef.current) return;
        setPreview({ loading: false, error: null, data });
      })
      .catch((err: unknown) => {
        if (op !== operationIdRef.current) return;
        setPreview({
          loading: false,
          error: err instanceof Error ? err.message : "Preview unavailable",
          data: null,
        });
      });
  }, [open, openEpoch, requestKey, request, scenario]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (creatingRef.current) return;
      event.preventDefault();
      closeDialog();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  });

  function closeDialog() {
    if (creatingRef.current) return;
    onClose();
    queueMicrotask(() => returnFocusRef?.current?.focus());
  }

  function changeProfile(next: RedactionProfile) {
    setProfile(next);
    setOptions(CONTEXTUAL_REPORT_PROFILE_DEFAULTS[next]);
  }

  async function retryPreview() {
    const op = operationIdRef.current;
    setPreview({ loading: true, error: null, data: null });
    try {
      const data = await api.previewReport(request, scenario);
      if (op !== operationIdRef.current) return;
      setPreview({ loading: false, error: null, data });
    } catch (err) {
      if (op !== operationIdRef.current) return;
      setPreview({
        loading: false,
        error: err instanceof Error ? err.message : "Preview unavailable",
        data: null,
      });
    }
  }

  async function saveReport(andDownload: boolean) {
    if (creatingRef.current) return;
    creatingRef.current = true;
    const op = operationIdRef.current;
    setPhase({ kind: "creating" });
    try {
      const summary = await api.createReport(request, scenario);
      if (op !== operationIdRef.current) return;
      onCreated?.(summary);
      if (!andDownload) {
        setPhase({ kind: "created", summary });
        return;
      }
      try {
        const file = await downloadStoredReport(summary.id, scenario);
        if (op !== operationIdRef.current) return;
        await triggerBrowserDownload(file);
        if (op !== operationIdRef.current) return;
        setPhase({ kind: "created", summary });
      } catch {
        if (op !== operationIdRef.current) return;
        setPhase({
          kind: "created_download_failed",
          summary,
          message: "Report saved, but download could not be started.",
        });
      }
    } catch {
      if (op !== operationIdRef.current) return;
      setPhase({ kind: "create_failed", message: "Could not save report." });
    } finally {
      if (op === operationIdRef.current) {
        creatingRef.current = false;
      }
    }
  }

  async function retryDownload(summary: ReportSummary) {
    const op = operationIdRef.current;
    try {
      const file = await downloadStoredReport(summary.id, scenario);
      if (op !== operationIdRef.current) return;
      await triggerBrowserDownload(file);
      if (op !== operationIdRef.current) return;
      setPhase({ kind: "created", summary });
    } catch {
      if (op !== operationIdRef.current) return;
      setPhase({
        kind: "created_download_failed",
        summary,
        message: "Report saved, but download could not be started.",
      });
    }
  }

  async function copyPreviewMarkdown() {
    if (!preview.data) return;
    const accessGeneration = authRuntime.getAccessGeneration();
    await writeProtectedClipboardText(preview.data.markdown_summary, accessGeneration);
  }

  if (!open) return null;

  const creating = phase.kind === "creating";
  const decisionSummary = preview.data?.decision_summary;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl border border-zl-border bg-zl-surface p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-zl-text">
              Create {scopeLabel(target.scope).toLowerCase()} report
            </h2>
            <p id={descId} className="mt-1 text-sm text-zl-muted">
              Export stored evidence for <span className="text-zl-text">{target.subjectLabel}</span>.
              Scope and target are fixed by this page.
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={closeDialog}
            disabled={creating}
            className="min-h-11 rounded-lg border border-zl-border px-3 py-2 text-sm disabled:opacity-50"
          >
            Close
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Badge severity="watch">{scopeLabel(target.scope)}</Badge>
          <Badge severity="healthy">{target.subjectLabel}</Badge>
        </div>

        <div className="mt-5 space-y-4">
          <Field label="Format">
            <Segmented options={FORMATS} value={format} onChange={setFormat} disabled={creating} />
          </Field>
          <Field label="Redaction profile">
            <div className="space-y-2">
              <Segmented
                options={PROFILES.map((p) => ({ value: p.value, label: p.label }))}
                value={profile}
                onChange={(v) => changeProfile(v as RedactionProfile)}
                disabled={creating}
              />
              <p className="text-xs text-zl-muted">
                {PROFILES.find((p) => p.value === profile)?.hint}
              </p>
            </div>
          </Field>

          <details
            open={advancedOpen}
            onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary className="cursor-pointer text-sm font-medium text-zl-accent">
              Advanced redaction
            </summary>
            <div className="mt-3 space-y-2 rounded-lg border border-zl-border p-3">
              <Toggle
                label="Preserve friendly names"
                checked={options.preserveFriendly}
                onChange={(v) => setOptions((o) => ({ ...o, preserveFriendly: v }))}
                disabled={creating}
              />
              <Toggle
                label="Hash IEEE addresses"
                checked={options.hashIeee}
                onChange={(v) => setOptions((o) => ({ ...o, hashIeee: v }))}
                disabled={creating}
              />
              <Toggle
                label="Redact hostnames"
                checked={options.redactHostnames}
                onChange={(v) => setOptions((o) => ({ ...o, redactHostnames: v }))}
                disabled={creating}
              />
              <Toggle
                label="Redact IP addresses"
                checked={options.redactIp}
                onChange={(v) => setOptions((o) => ({ ...o, redactIp: v }))}
                disabled={creating}
              />
              <Toggle
                label="Redact network names"
                checked={options.redactNetworkNames}
                onChange={(v) => setOptions((o) => ({ ...o, redactNetworkNames: v }))}
                disabled={creating}
              />
              <Toggle
                label="Include recent timeline"
                checked={options.includeTimeline}
                onChange={(v) => setOptions((o) => ({ ...o, includeTimeline: v }))}
                disabled={creating}
              />
              <Toggle
                label="Include raw redacted payload snippets"
                checked={options.includeRaw}
                onChange={(v) => setOptions((o) => ({ ...o, includeRaw: v }))}
                disabled={creating}
              />
            </div>
          </details>

          <Card title="Export preview">
            {preview.loading && !preview.data ? (
              <LoadingState label="Loading preview…" />
            ) : preview.error && !preview.data ? (
              <ErrorState message={preview.error} onRetry={() => void retryPreview()} />
            ) : preview.data ? (
              <div className="space-y-3 text-sm">
                <dl className="grid gap-2 sm:grid-cols-2">
                  <PreviewRow label="Scope" value={scopeLabel(target.scope)} />
                  <PreviewRow label="Subject" value={target.subjectLabel} />
                  <PreviewRow label="Format" value={preview.data.format.toUpperCase()} />
                  <PreviewRow label="Report version" value={String(preview.data.report_version)} />
                  <PreviewRow
                    label="Networks"
                    value={String(
                      preview.data.raw_counts.networks_included ??
                        preview.data.domain_details.networks.length,
                    )}
                  />
                  <PreviewRow
                    label="Devices"
                    value={String(
                      preview.data.raw_counts.devices_included ??
                        preview.data.domain_details.devices.length,
                    )}
                  />
                  <PreviewRow
                    label="Incidents"
                    value={String(
                      preview.data.raw_counts.incidents_included ?? preview.data.incidents.length,
                    )}
                  />
                  <PreviewRow label="Redaction" value={preview.data.redaction.profile} />
                </dl>
                {decisionSummary && (
                  <p className="text-xs text-zl-muted">
                    Decision summary: {decisionSummary.subject_count} subjects ·{" "}
                    {Object.entries(decisionSummary.status_counts)
                      .filter(([, n]) => (n ?? 0) > 0)
                      .map(([status, n]) => `${status} ${n}`)
                      .join(" · ") || "no status counts"}
                  </p>
                )}
                <p className="text-xs text-zl-muted">
                  {preview.data.limitations.length > 0
                    ? `${preview.data.limitations.length} limitation${
                        preview.data.limitations.length === 1 ? "" : "s"
                      } will be included in the saved report.`
                    : "No limitations listed for this export preview."}
                </p>
                <p className="text-xs text-zl-muted">
                  Secrets — MQTT passwords, tokens, and network keys — are redacted before storage
                  or download.
                </p>
              </div>
            ) : null}
          </Card>

          {phase.kind === "create_failed" && (
            <p className="text-sm text-zl-critical">{phase.message}</p>
          )}
          {phase.kind === "created" && (
            <p className="text-sm text-zl-accent">Report saved.</p>
          )}
          {phase.kind === "created_download_failed" && (
            <div className="space-y-2 text-sm text-zl-watch">
              <p>{phase.message}</p>
              <button
                type="button"
                onClick={() => void retryDownload(phase.summary)}
                className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
              >
                Retry download
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={creating}
              onClick={() => void saveReport(false)}
              className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {creating ? "Saving…" : "Save report"}
            </button>
            <button
              type="button"
              disabled={creating}
              onClick={() => void saveReport(true)}
              className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
            >
              Save and download
            </button>
            {preview.data && (
              <button
                type="button"
                disabled={creating}
                onClick={() => void copyPreviewMarkdown()}
                className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
              >
                Copy preview Markdown summary
              </button>
            )}
          </div>
        </div>
      </div>
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
  disabled,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`min-h-11 rounded-lg px-4 py-2 text-sm disabled:opacity-50 ${
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

function Toggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-zl-text">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-zl-accent"
      />
    </label>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-zl-border/40 pb-1">
      <dt className="text-zl-muted">{label}</dt>
      <dd className="text-right text-zl-text">{value}</dd>
    </div>
  );
}
