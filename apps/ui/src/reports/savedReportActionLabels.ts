import type { ReportSummary } from "@zigbeelens/shared";
import { formatTime } from "@/lib/format";
import { scopeLabel } from "@/reports/contextualReportTarget";

/**
 * Accessible names for saved-report row actions.
 * Prefer human metadata; fall back to ordinal when rows collide.
 */
export function savedReportActionName(
  action: "Download" | "Copy Markdown" | "Delete",
  report: ReportSummary,
  options: {
    index: number;
    total: number;
    duplicateHumanContext: boolean;
  },
): string {
  const when = formatTime(report.generated_at);
  const scope = scopeLabel(report.scope).toLowerCase();
  const format = report.format.toUpperCase();
  let name: string;
  if (action === "Download") {
    name = `Download ${scope} ${format} report generated ${when}`;
  } else if (action === "Copy Markdown") {
    name = `Copy Markdown from ${scope} report generated ${when}`;
  } else {
    name = `Delete ${scope} report generated ${when}`;
  }
  if (options.duplicateHumanContext) {
    name = `${name}, item ${options.index + 1} of ${options.total}`;
  }
  return name;
}

export function humanReportContextKey(report: ReportSummary): string {
  return [
    report.scope,
    report.format,
    report.generated_at,
    report.summary,
    report.redaction_profile,
  ].join("|");
}
