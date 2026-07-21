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
  contextualDialogContextKey,
  contextualRequestKey,
  contextualTargetIdentity,
  scopeLabel,
  targetFromIdentity,
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
  | { kind: "created"; summary: ReportSummary; requestKey: string }
  | { kind: "created_download_failed"; summary: ReportSummary; requestKey: string; message: string }
  | { kind: "create_failed"; message: string };

type PreviewState = {
  requestKey: string | null;
  loading: boolean;
  error: string | null;
  data: Awaited<ReturnType<typeof api.previewReport>> | null;
};

function getFocusable(container: HTMLElement): HTMLElement[] {
  const nodes = container.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
  );
  return Array.from(nodes).filter(
    (el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true",
  );
}

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
  const formatGroupId = useId();
  const profileGroupId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const previewSequenceRef = useRef(0);
  const mutationSequenceRef = useRef(0);
  const mutationInFlightRef = useRef(false);
  const downloadInFlightRef = useRef(false);
  const mountedRef = useRef(true);
  const requestRef = useRef<ReturnType<typeof buildContextualReportRequest> | null>(null);
  const requestKeyRef = useRef("");
  const dialogContextKeyRef = useRef("");
  const onCreatedRef = useRef(onCreated);
  onCreatedRef.current = onCreated;

  const [format, setFormat] = useState<ReportFormat>("json");
  const [profile, setProfile] = useState<RedactionProfile>("standard");
  const [options, setOptions] = useState(
    () => CONTEXTUAL_REPORT_PROFILE_DEFAULTS.standard,
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [phase, setPhase] = useState<DialogPhase>({ kind: "idle" });
  const [mutationInFlight, setMutationInFlight] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>({
    requestKey: null,
    loading: false,
    error: null,
    data: null,
  });

  const targetIdentity = contextualTargetIdentity(target);
  const stableTarget = useMemo(
    () => targetFromIdentity(targetIdentity, target),
    // Intentionally keyed by identity so parent object-literal churn is ignored.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [targetIdentity],
  );
  // Prefer live subjectLabel for full scope (identity omits it).
  const displayTarget: ContextualReportTarget =
    stableTarget.scope === "full"
      ? { scope: "full", subjectLabel: target.subjectLabel }
      : stableTarget;

  const dialogContextKey = contextualDialogContextKey(stableTarget, scenario);
  const reportOptions: ContextualReportOptions = useMemo(
    () => ({ format, profile, ...options }),
    [format, profile, options],
  );
  const requestKey = contextualRequestKey(stableTarget, scenario, reportOptions);
  const request = useMemo(
    () => buildContextualReportRequest(stableTarget, reportOptions),
    [stableTarget, reportOptions],
  );
  requestRef.current = request;
  requestKeyRef.current = requestKey;
  dialogContextKeyRef.current = dialogContextKey;

  const [trackedOpen, setTrackedOpen] = useState(false);
  const [trackedContextKey, setTrackedContextKey] = useState(dialogContextKey);
  const [trackedRequestKey, setTrackedRequestKey] = useState(requestKey);

  if (open !== trackedOpen || dialogContextKey !== trackedContextKey) {
    setTrackedOpen(open);
    setTrackedContextKey(dialogContextKey);
    if (open) {
      setFormat("json");
      setProfile("standard");
      setOptions(CONTEXTUAL_REPORT_PROFILE_DEFAULTS.standard);
      setAdvancedOpen(false);
      setPhase({ kind: "idle" });
      setStatusMessage(null);
      setPreview({ requestKey: null, loading: false, error: null, data: null });
      setTrackedRequestKey(
        contextualRequestKey(stableTarget, scenario, {
          format: "json",
          profile: "standard",
          ...CONTEXTUAL_REPORT_PROFILE_DEFAULTS.standard,
        }),
      );
    }
  } else if (open && requestKey !== trackedRequestKey) {
    setTrackedRequestKey(requestKey);
    // Options/format changed: clear prior created state for this dialog.
    if (
      phase.kind === "created" ||
      phase.kind === "created_download_failed" ||
      phase.kind === "create_failed"
    ) {
      setPhase({ kind: "idle" });
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Preview ownership — never touches mutation sequence/lock.
  useEffect(() => {
    if (!open) return;
    const sequence = ++previewSequenceRef.current;
    const keyForRequest = requestKey;
    const requestForPreview = requestRef.current;
    if (!requestForPreview) return;
    setPreview({ requestKey: keyForRequest, loading: true, error: null, data: null });
    void api
      .previewReport(requestForPreview, scenario)
      .then((data) => {
        if (!mountedRef.current) return;
        if (sequence !== previewSequenceRef.current) return;
        if (keyForRequest !== requestKeyRef.current) return;
        setPreview({ requestKey: keyForRequest, loading: false, error: null, data });
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return;
        if (sequence !== previewSequenceRef.current) return;
        if (keyForRequest !== requestKeyRef.current) return;
        setPreview({
          requestKey: keyForRequest,
          loading: false,
          error: err instanceof Error ? err.message : "Preview unavailable",
          data: null,
        });
      });
    // Only the canonical request key drives preview restart.
  }, [open, requestKey, scenario]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
  }, [open, dialogContextKey]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (mutationInFlightRef.current) return;
        event.preventDefault();
        closeDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable(panel);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      const active = document.activeElement as HTMLElement | null;
      if (!active || !panel.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
        return;
      }
      if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  });

  function closeDialog() {
    if (mutationInFlightRef.current) return;
    onClose();
    queueMicrotask(() => returnFocusRef?.current?.focus());
  }

  function changeProfile(next: RedactionProfile) {
    setProfile(next);
    setOptions(CONTEXTUAL_REPORT_PROFILE_DEFAULTS[next]);
  }

  async function retryPreview() {
    const sequence = ++previewSequenceRef.current;
    const keyForRequest = requestKey;
    const requestForPreview = requestRef.current;
    if (!requestForPreview) return;
    setPreview({ requestKey: keyForRequest, loading: true, error: null, data: null });
    try {
      const data = await api.previewReport(requestForPreview, scenario);
      if (!mountedRef.current) return;
      if (sequence !== previewSequenceRef.current) return;
      if (keyForRequest !== requestKeyRef.current) return;
      setPreview({ requestKey: keyForRequest, loading: false, error: null, data });
    } catch (err) {
      if (!mountedRef.current) return;
      if (sequence !== previewSequenceRef.current) return;
      if (keyForRequest !== requestKeyRef.current) return;
      setPreview({
        requestKey: keyForRequest,
        loading: false,
        error: err instanceof Error ? err.message : "Preview unavailable",
        data: null,
      });
    }
  }

  const previewMatchesCurrent =
    preview.requestKey === requestKey && preview.data != null && !preview.loading && !preview.error;
  const createdForCurrent =
    (phase.kind === "created" || phase.kind === "created_download_failed") &&
    phase.requestKey === requestKey;
  const canCreate =
    open &&
    previewMatchesCurrent &&
    !mutationInFlight &&
    !createdForCurrent;

  async function saveReport(andDownload: boolean) {
    if (mutationInFlightRef.current) return;
    if (!canCreate) return;
    const requestForCreate = requestRef.current;
    if (!requestForCreate) return;

    mutationInFlightRef.current = true;
    setMutationInFlight(true);
    const mutationId = ++mutationSequenceRef.current;
    const capturedRequestKey = requestKey;
    const capturedContextKey = dialogContextKey;
    const capturedScenario = scenario;
    setPhase({ kind: "creating" });
    setStatusMessage(null);

    let summary: ReportSummary | null = null;
    try {
      summary = await api.createReport(requestForCreate, capturedScenario);
      if (!mountedRef.current) return;

      const contextStillCurrent = capturedContextKey === dialogContextKeyRef.current;
      if (!contextStillCurrent) {
        setStatusMessage(
          "A report may have been saved for the previous selection. Check Saved reports.",
        );
        return;
      }

      onCreatedRef.current?.(summary);

      if (capturedRequestKey !== requestKeyRef.current) {
        // Options changed after create started — list refresh only; no current-key created UI.
        setPhase({ kind: "idle" });
        return;
      }

      if (!andDownload) {
        setPhase({ kind: "created", summary, requestKey: capturedRequestKey });
        return;
      }

      try {
        const file = await downloadStoredReport(summary.id, capturedScenario);
        if (!mountedRef.current) return;
        if (capturedContextKey !== dialogContextKeyRef.current) return;
        if (capturedRequestKey !== requestKeyRef.current) {
          setPhase({ kind: "created", summary, requestKey: capturedRequestKey });
          return;
        }
        await triggerBrowserDownload(file);
        if (!mountedRef.current) return;
        if (capturedContextKey !== dialogContextKeyRef.current) return;
        setPhase({ kind: "created", summary, requestKey: capturedRequestKey });
      } catch {
        if (!mountedRef.current) return;
        if (capturedContextKey !== dialogContextKeyRef.current) {
          setStatusMessage(
            "A report may have been saved for the previous selection. Check Saved reports.",
          );
          return;
        }
        setPhase({
          kind: "created_download_failed",
          summary,
          requestKey: capturedRequestKey,
          message: "Report saved, but download could not be started.",
        });
      }
    } catch {
      if (!mountedRef.current) return;
      if (capturedContextKey !== dialogContextKeyRef.current) {
        setStatusMessage("Could not save the previous selection’s report.");
        return;
      }
      if (mutationId !== mutationSequenceRef.current) return;
      setPhase({ kind: "create_failed", message: "Could not save report." });
    } finally {
      mutationInFlightRef.current = false;
      if (mountedRef.current) {
        setMutationInFlight(false);
      }
    }
  }

  async function downloadSaved(summary: ReportSummary, forRequestKey: string) {
    if (downloadInFlightRef.current) return;
    downloadInFlightRef.current = true;
    try {
      const file = await downloadStoredReport(summary.id, scenario);
      if (!mountedRef.current) return;
      if (forRequestKey !== requestKeyRef.current) return;
      await triggerBrowserDownload(file);
      if (!mountedRef.current) return;
      if (forRequestKey !== requestKeyRef.current) return;
      setPhase({ kind: "created", summary, requestKey: forRequestKey });
      setStatusMessage(null);
    } catch {
      if (!mountedRef.current) return;
      if (forRequestKey !== requestKeyRef.current) return;
      setPhase({
        kind: "created_download_failed",
        summary,
        requestKey: forRequestKey,
        message: "Report saved, but download could not be started.",
      });
    } finally {
      downloadInFlightRef.current = false;
    }
  }

  async function copyPreviewMarkdown() {
    if (!previewMatchesCurrent || !preview.data) return;
    try {
      const accessGeneration = authRuntime.getAccessGeneration();
      await writeProtectedClipboardText(preview.data.markdown_summary, accessGeneration);
      if (!mountedRef.current) return;
      setStatusMessage("Preview Markdown copied.");
    } catch {
      if (!mountedRef.current) return;
      setStatusMessage("Could not copy preview Markdown.");
    }
  }

  if (!open) return null;

  const creating = mutationInFlight;
  const showCreatedActions = createdForCurrent;
  const decisionSummary =
    previewMatchesCurrent && preview.data ? preview.data.decision_summary : null;
  const previewReady = previewMatchesCurrent && preview.data;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl border border-zl-border bg-zl-surface p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-zl-text">
              Create {scopeLabel(displayTarget.scope).toLowerCase()} report
            </h2>
            <p id={descId} className="mt-1 text-sm text-zl-muted">
              Export stored evidence for{" "}
              <span className="text-zl-text">{displayTarget.subjectLabel}</span>. Scope and
              target are fixed by this page.
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
          <Badge severity="watch">{scopeLabel(displayTarget.scope)}</Badge>
          <Badge severity="healthy">{displayTarget.subjectLabel}</Badge>
        </div>

        <div className="mt-5 space-y-4">
          <Field labelId={formatGroupId} label="Format">
            <Segmented
              groupLabelId={formatGroupId}
              groupLabel="Format"
              options={FORMATS}
              value={format}
              onChange={setFormat}
              disabled={creating}
            />
          </Field>
          <Field labelId={profileGroupId} label="Redaction profile">
            <div className="space-y-2">
              <Segmented
                groupLabelId={profileGroupId}
                groupLabel="Redaction profile"
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
            {preview.requestKey !== requestKey || (preview.loading && !preview.data) ? (
              <LoadingState label="Loading preview…" />
            ) : preview.error && !preview.data ? (
              <ErrorState message={preview.error} onRetry={() => void retryPreview()} />
            ) : previewReady ? (
              <div className="space-y-3 text-sm">
                <dl className="grid gap-2 sm:grid-cols-2">
                  <PreviewRow label="Scope" value={scopeLabel(displayTarget.scope)} />
                  <PreviewRow label="Subject" value={displayTarget.subjectLabel} />
                  <PreviewRow label="Format" value={preview.data!.format.toUpperCase()} />
                  <PreviewRow
                    label="Report version"
                    value={String(preview.data!.report_version)}
                  />
                  <PreviewRow
                    label="Networks"
                    value={String(
                      preview.data!.raw_counts.networks_included ??
                        preview.data!.domain_details.networks.length,
                    )}
                  />
                  <PreviewRow
                    label="Devices"
                    value={String(
                      preview.data!.raw_counts.devices_included ??
                        preview.data!.domain_details.devices.length,
                    )}
                  />
                  <PreviewRow
                    label="Incidents"
                    value={String(
                      preview.data!.raw_counts.incidents_included ??
                        preview.data!.incidents.length,
                    )}
                  />
                  <PreviewRow label="Redaction" value={preview.data!.redaction.profile} />
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
                  {preview.data!.limitations.length > 0
                    ? `${preview.data!.limitations.length} limitation${
                        preview.data!.limitations.length === 1 ? "" : "s"
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
            <p className="text-sm text-zl-critical" role="status">
              {phase.message}
            </p>
          )}
          {statusMessage && (
            <p className="text-sm text-zl-watch" role="status">
              {statusMessage}
            </p>
          )}
          {showCreatedActions && phase.kind === "created" && (
            <p className="text-sm text-zl-accent" role="status">
              Report saved.
            </p>
          )}
          {showCreatedActions && phase.kind === "created_download_failed" && (
            <div className="space-y-2 text-sm text-zl-watch">
              <p role="status">{phase.message}</p>
              <button
                type="button"
                onClick={() => void downloadSaved(phase.summary, phase.requestKey)}
                className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
              >
                Retry download
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {showCreatedActions ? (
              <>
                <p className="sr-only" role="status">
                  Report saved
                </p>
                <button
                  type="button"
                  disabled={creating}
                  onClick={() => {
                    if (phase.kind === "created" || phase.kind === "created_download_failed") {
                      void downloadSaved(phase.summary, phase.requestKey);
                    }
                  }}
                  className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Download saved report
                </button>
                <button
                  type="button"
                  disabled={creating}
                  onClick={closeDialog}
                  className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                >
                  Close
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  disabled={!canCreate}
                  onClick={() => void saveReport(false)}
                  className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {creating ? "Saving…" : "Save report"}
                </button>
                <button
                  type="button"
                  disabled={!canCreate}
                  onClick={() => void saveReport(true)}
                  className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                >
                  Save and download
                </button>
                {previewReady && (
                  <button
                    type="button"
                    disabled={creating}
                    onClick={() => void copyPreviewMarkdown()}
                    className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                  >
                    Copy preview Markdown summary
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  labelId,
  children,
}: {
  label: string;
  labelId?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span
        id={labelId}
        className="text-xs font-medium uppercase tracking-wide text-zl-muted"
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
  disabled,
  groupLabelId,
  groupLabel,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
  groupLabelId: string;
  groupLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-labelledby={groupLabelId}
      aria-label={groupLabel}
      className="flex flex-wrap gap-1.5"
    >
      {options.map((o) => {
        const selected = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(o.value)}
            className={`min-h-11 rounded-lg px-4 py-2 text-sm disabled:opacity-50 ${
              selected
                ? "bg-zl-accent text-zl-bg"
                : "border border-zl-border text-zl-muted hover:bg-zl-surface-2"
            }`}
          >
            {o.label}
          </button>
        );
      })}
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
