import { useEffect, useRef, useState } from "react";
import type { MeshEvidenceReport } from "@/lib/meshEvidenceReport";
import {
  REPORT_COPIED_MESSAGE,
  REPORT_COPY_FAILED_MESSAGE,
  REPORT_COPY_LABEL,
  REPORT_DOWNLOAD_JSON_LABEL,
  REPORT_DOWNLOAD_MARKDOWN_LABEL,
  REPORT_MENU_LABEL,
} from "@/lib/meshGraphCopy";

/**
 * "Create report" — evidence summary export controls.
 *
 * Read-only export of what the graph already shows: copy the Markdown
 * evidence summary to the clipboard, or download it as a .md (or .json)
 * file, generated entirely client-side. Nothing is persisted server-side
 * and nothing new is collected.
 */

function downloadFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function EvidenceReportMenu({
  buildReport,
}: {
  /** Builds the report from current evidence state at action time. */
  buildReport: () => MeshEvidenceReport;
}) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  // The success/failure note is transient; it clears itself quietly.
  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(null), 4000);
    return () => clearTimeout(timer);
  }, [status]);

  const copySummary = async () => {
    const report = buildReport();
    try {
      await navigator.clipboard.writeText(report.markdown);
      setStatus(REPORT_COPIED_MESSAGE);
    } catch {
      setStatus(REPORT_COPY_FAILED_MESSAGE);
    }
    setOpen(false);
  };

  const downloadMarkdown = () => {
    const report = buildReport();
    downloadFile(`${report.filenameBase}.md`, report.markdown, "text/markdown");
    setOpen(false);
  };

  const downloadJson = () => {
    const report = buildReport();
    downloadFile(
      `${report.filenameBase}.json`,
      JSON.stringify(report.jsonSummary, null, 2),
      "application/json",
    );
    setOpen(false);
  };

  const itemClass =
    "block w-full px-3 py-1.5 text-left text-sm text-zl-text hover:bg-zl-surface-2";

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={toggleRef}
        type="button"
        aria-label={REPORT_MENU_LABEL}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-zl-border bg-zl-surface-2 px-3 py-1.5 text-sm text-zl-text hover:border-zl-accent/40"
      >
        {REPORT_MENU_LABEL}
      </button>
      {open && (
        <div
          role="menu"
          aria-label={REPORT_MENU_LABEL}
          className="absolute left-0 top-full z-20 mt-1 w-64 overflow-hidden rounded-lg border border-zl-border bg-zl-surface shadow-lg"
        >
          <button type="button" role="menuitem" onClick={copySummary} className={itemClass}>
            {REPORT_COPY_LABEL}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={downloadMarkdown}
            className={itemClass}
          >
            {REPORT_DOWNLOAD_MARKDOWN_LABEL}
          </button>
          <button type="button" role="menuitem" onClick={downloadJson} className={itemClass}>
            {REPORT_DOWNLOAD_JSON_LABEL}
          </button>
        </div>
      )}
      {status && (
        <p
          role="status"
          className="absolute left-0 top-full z-10 mt-1 whitespace-nowrap rounded-lg border border-zl-border bg-zl-surface px-2 py-1 text-[11px] text-zl-muted shadow"
        >
          {status}
        </p>
      )}
    </div>
  );
}
