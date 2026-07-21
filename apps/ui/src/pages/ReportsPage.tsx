import { useMemo, useRef, useState } from "react";
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
  humanReportContextKey,
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
  const [rowBusyId, setRowBusyId] = useState<string | null>(null);
  const createButtonRef = useRef<HTMLButtonElement>(null);
  const deletingRef = useRef(false);

  const stored = useLiveResource(() => api.listReports(), [reloadKey], {
    refetchOn: ["reports_updated"],
  });

  const duplicateKeys = useMemo(() => {
    const counts = new Map<string, number>();
    for (const report of stored.data ?? []) {
      const key = humanReportContextKey(report);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [stored.data]);

  function flash(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 2500);
  }

  async function copyStored(report: ReportSummary) {
    setRowBusyId(report.id);
    try {
      const accessGeneration = authRuntime.getAccessGeneration();
      const detail = await api.report(report.id, scen);
      const markdown =
        typeof detail.markdown_summary === "string" ? detail.markdown_summary : "";
      await writeProtectedClipboardText(markdown, accessGeneration);
      flash("Stored report markdown copied.");
    } catch {
      flash("Could not copy report markdown.");
    } finally {
      setRowBusyId(null);
    }
  }

  async function deleteStored(report: ReportSummary) {
    if (deletingRef.current) return;
    deletingRef.current = true;
    setRowBusyId(report.id);
    try {
      await api.deleteReport(report.id);
      setConfirmDeleteId(null);
      setReloadKey((k) => k + 1);
      flash("Report deleted.");
    } catch {
      flash("Could not delete report.");
    } finally {
      deletingRef.current = false;
      setRowBusyId(null);
    }
  }

  async function downloadStored(report: ReportSummary) {
    setRowBusyId(report.id);
    try {
      const file = await downloadStoredReport(report.id, scen);
      await triggerBrowserDownload(file);
      flash("Report download started.");
    } catch {
      flash("Could not download report.");
    } finally {
      setRowBusyId(null);
    }
  }

  const reports = stored.data ?? [];

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
          ref={createButtonRef}
          type="button"
          onClick={() => setReportOpen(true)}
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
          Legacy v1/v2 stored reports remain unchanged and downloadable as originally saved.
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
        returnFocusRef={createButtonRef}
        target={FULL_REPORT_TARGET}
        onCreated={() => setReloadKey((k) => k + 1)}
      />

      <Card
        title="Saved reports"
        subtitle="Locally saved snapshots. Nothing leaves your machine automatically."
      >
        {stored.error ? (
          <ErrorState message={stored.error} onRetry={stored.refetch} />
        ) : stored.loading && !stored.data ? (
          <LoadingState label="Loading reports…" />
        ) : reports.length === 0 ? (
          <div className="space-y-3">
            <EmptyState
              title="No saved reports yet."
              detail="Create reports from a device, incident, network, or Mesh investigation."
            />
            <button
              type="button"
              onClick={() => setReportOpen(true)}
              className="min-h-11 rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-white"
            >
              Create full report
            </button>
          </div>
        ) : (
          <ul className="divide-y divide-zl-border/60">
            {reports.map((report, index) => {
              const duplicate =
                (duplicateKeys.get(humanReportContextKey(report)) ?? 0) > 1;
              const busy = rowBusyId === report.id;
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
                        aria-label={savedReportActionName("Download", report, {
                          index,
                          total: reports.length,
                          duplicateHumanContext: duplicate,
                        })}
                        onClick={() => void downloadStored(report)}
                        className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                      >
                        Download
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={savedReportActionName("Copy Markdown", report, {
                          index,
                          total: reports.length,
                          duplicateHumanContext: duplicate,
                        })}
                        onClick={() => void copyStored(report)}
                        className="min-h-11 rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50"
                      >
                        Copy Markdown
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={savedReportActionName("Delete", report, {
                          index,
                          total: reports.length,
                          duplicateHumanContext: duplicate,
                        })}
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
      </Card>
    </div>
  );
}
