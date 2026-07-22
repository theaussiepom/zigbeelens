import { useEffect, useMemo, useRef, useState } from "react";
import type { ReportSummary } from "@zigbeelens/shared";
import {
  api,
  downloadStoredReport,
  triggerBrowserDownload,
  writeProtectedClipboardText,
} from "@/lib/api";
import { authRuntime } from "@/lib/authRuntime";
import { useScenario } from "@/context/ScenarioContext";
import { useLiveResource } from "@/hooks/useLiveResource";
import { ContextualReportDialog } from "@/components/reports/ContextualReportDialog";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { formatTime } from "@/lib/format";
import { scopeLabel } from "@/reports/contextualReportTarget";
import {
  ReportRowOperationRegistry,
  type ReportRowOperation,
} from "@/reports/reportRowOperations";
import {
  assignSavedReportActionGroups,
  savedReportActionName,
} from "@/reports/savedReportActionLabels";

const FULL_REPORT_TARGET = {
  scope: "full" as const,
  subjectLabel: "Full ZigbeeLens evidence",
};

export function ReportsPage() {
  const { scenario } = useScenario();
  const scen = scenario || undefined;
  const [reloadKey, setReloadKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyReportIds, setBusyReportIds] = useState<ReadonlySet<string>>(() => new Set());
  const headerCreateRef = useRef<HTMLButtonElement>(null);
  const emptyCreateRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const registryRef = useRef(new ReportRowOperationRegistry());
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    const registry = registryRef.current;
    return () => {
      mountedRef.current = false;
      registry.clear();
    };
  }, []);

  const stored = useLiveResource(() => api.listReports(), [reloadKey], {
    refetchOn: ["reports_updated"],
  });

  const hasAcceptedList = stored.data !== null;
  const reports = stored.data ?? [];
  const actionGroups = useMemo(
    () => assignSavedReportActionGroups(reports),
    [reports],
  );

  function flash(message: string) {
    if (!mountedRef.current) return;
    setToast(message);
    window.setTimeout(() => {
      if (mountedRef.current) setToast(null);
    }, 2500);
  }

  function beginReportOperation(reportId: string, operation: ReportRowOperation): boolean {
    const started = registryRef.current.begin(reportId, operation);
    if (started && mountedRef.current) {
      setBusyReportIds(registryRef.current.snapshot());
    }
    return started;
  }

  function endReportOperation(reportId: string): void {
    registryRef.current.end(reportId);
    if (mountedRef.current) {
      setBusyReportIds(registryRef.current.snapshot());
    }
  }

  function openFullReport(launcher: HTMLButtonElement | null) {
    returnFocusRef.current = launcher;
    setReportOpen(true);
  }

  async function copyStored(report: ReportSummary) {
    if (!beginReportOperation(report.id, "copy")) return;
    try {
      const accessGeneration = authRuntime.getAccessGeneration();
      const detail = await api.report(report.id, scen);
      if (!mountedRef.current) return;
      const raw =
        detail && typeof detail === "object" && "markdown_summary" in detail
          ? (detail as { markdown_summary?: unknown }).markdown_summary
          : undefined;
      const markdown = typeof raw === "string" ? raw.trim() : "";
      if (!markdown) {
        flash("Markdown summary is not available for this stored report.");
        return;
      }
      await writeProtectedClipboardText(markdown, accessGeneration);
      flash("Stored report markdown copied.");
    } catch {
      flash("Could not copy report markdown.");
    } finally {
      endReportOperation(report.id);
    }
  }

  async function deleteStored(report: ReportSummary) {
    if (!beginReportOperation(report.id, "delete")) return;
    try {
      await api.deleteReport(report.id);
      if (!mountedRef.current) return;
      setConfirmDeleteId(null);
      setReloadKey((k) => k + 1);
      flash("Report deleted.");
    } catch {
      flash("Could not delete report.");
    } finally {
      endReportOperation(report.id);
    }
  }

  async function downloadStored(report: ReportSummary) {
    if (!beginReportOperation(report.id, "download")) return;
    try {
      const file = await downloadStoredReport(report.id, scen);
      if (!mountedRef.current) return;
      await triggerBrowserDownload(file);
      flash("Report download started.");
    } catch {
      flash("Could not download report.");
    } finally {
      endReportOperation(report.id);
    }
  }

  const initialError = Boolean(stored.error && !hasAcceptedList);
  const refreshWarning = Boolean(stored.error && hasAcceptedList);

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="mt-1 text-zl-muted">
            Saved redacted evidence exports. Create device, incident, or network reports from
            those pages — or generate a full-estate report here.
          </p>
        </div>
        <button
          ref={headerCreateRef}
          type="button"
          onClick={() => openFullReport(headerCreateRef.current)}
          className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        >
          Create full report
        </button>
      </div>

      <div className="rounded-lg border border-zl-border bg-zl-surface-2/40 p-4 text-sm text-zl-muted">
        <p>
          Reports are generated from ZigbeeLens&rsquo; observed MQTT and diagnostic history. They
          are <strong className="text-zl-text">evidence-backed snapshots, not root-cause proof.</strong>
        </p>
        <p className="mt-1">
          Secrets &mdash; MQTT passwords, tokens, and network keys &mdash; are redacted before any
          report is stored or downloaded. Historical snapshot evidence is included when available.
          Saved reports use the current report format.
        </p>
      </div>

      {toast && (
        <div
          role="status"
          className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-4 py-2 text-sm text-zl-accent"
        >
          {toast}
        </div>
      )}

      <ContextualReportDialog
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        scenario={scen}
        returnFocusRef={returnFocusRef}
        target={FULL_REPORT_TARGET}
        onCreated={() => setReloadKey((k) => k + 1)}
      />

      <Card
        title="Saved reports"
        subtitle="Locally saved snapshots. Nothing leaves your machine automatically."
      >
        {initialError ? (
          <ErrorState message={stored.error!} onRetry={stored.refetch} />
        ) : stored.loading && !hasAcceptedList ? (
          <LoadingState label="Loading reports…" />
        ) : (
          <div className="space-y-3">
            {refreshWarning && (
              <div
                role="status"
                className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-3 py-2 text-sm text-zl-watch"
              >
                <p>Saved reports could not be refreshed. Showing the last loaded list.</p>
                <button
                  type="button"
                  onClick={() => stored.refetch()}
                  className="mt-2 min-h-11 rounded-lg border border-zl-border px-3 py-1.5 text-sm text-zl-text hover:bg-zl-surface-2"
                >
                  Retry
                </button>
              </div>
            )}
            {reports.length === 0 ? (
              <div className="space-y-3">
                <EmptyState
                  title="No saved reports yet."
                  detail="Create reports from a device, incident, network, or Mesh investigation."
                />
                <button
                  ref={emptyCreateRef}
                  type="button"
                  onClick={() => openFullReport(emptyCreateRef.current)}
                  className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white"
                >
                  Create full report
                </button>
              </div>
            ) : (
              <ul className="divide-y divide-zl-border/60">
                {reports.map((report, index) => {
                  const group = actionGroups[index] ?? { groupIndex: 0, groupSize: 1 };
                  const busy = busyReportIds.has(report.id);
                  const confirming = confirmDeleteId === report.id;
                  return (
                    <li key={report.id} className="flex flex-wrap items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-zl-text">{report.summary}</p>
                        <p className="text-xs text-zl-muted" title={report.generated_at}>
                          {formatTime(report.generated_at)} · {scopeLabel(report.scope)} ·{" "}
                          {report.format.toUpperCase()} · {report.redaction_profile}
                        </p>
                      </div>
                      {confirming ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm text-zl-watch">
                            Delete this {scopeLabel(report.scope).toLowerCase()} report generated{" "}
                            {formatTime(report.generated_at)}?
                          </p>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void deleteStored(report)}
                            className="min-h-11 rounded-lg border border-zl-critical/40 px-4 py-2 text-sm text-zl-critical hover:bg-zl-surface-2 disabled:opacity-50"
                          >
                            Confirm delete
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setConfirmDeleteId(null)}
                            className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={savedReportActionName("Download", report, group)}
                            onClick={() => void downloadStored(report)}
                            className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                          >
                            Download
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={savedReportActionName("Copy Markdown", report, group)}
                            onClick={() => void copyStored(report)}
                            className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                          >
                            Copy Markdown
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={savedReportActionName("Delete", report, group)}
                            onClick={() => setConfirmDeleteId(report.id)}
                            className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm text-zl-muted hover:bg-zl-surface-2 disabled:opacity-50"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
