import type { ReportSummary } from "@zigbeelens/shared";
import { formatTime } from "@/lib/format";
import { scopeLabel } from "@/reports/contextualReportTarget";

/**
 * Exact human context used for both accessible action names and duplicate grouping.
 * Uses formatted time (not raw ISO), so millisecond-only timestamp drift groups together.
 */
export function savedReportHumanContext(report: ReportSummary): string {
  const when = formatTime(report.generated_at);
  const scope = scopeLabel(report.scope).toLowerCase();
  const format = report.format.toUpperCase();
  const profile = report.redaction_profile;
  const summary = report.summary.trim();
  const parts = [`${scope} ${format} report generated ${when}`, profile];
  if (summary.length > 0) {
    parts.push(summary);
  }
  return parts.join(", ");
}

/** @deprecated Prefer savedReportHumanContext — kept for existing import sites. */
export function humanReportContextKey(report: ReportSummary): string {
  return savedReportHumanContext(report);
}

export interface SavedReportActionGroup {
  groupIndex: number;
  groupSize: number;
}

/**
 * Group-local ordinals by exact human context (not full-list index).
 * Unrelated intervening rows do not affect a duplicate group's numbering.
 */
export function assignSavedReportActionGroups(
  reports: readonly ReportSummary[],
): SavedReportActionGroup[] {
  const counts = new Map<string, number>();
  for (const report of reports) {
    const key = savedReportHumanContext(report);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const seen = new Map<string, number>();
  return reports.map((report) => {
    const key = savedReportHumanContext(report);
    const groupSize = counts.get(key) ?? 1;
    const groupIndex = seen.get(key) ?? 0;
    seen.set(key, groupIndex + 1);
    return { groupIndex, groupSize };
  });
}

/**
 * Accessible names for saved-report row actions.
 * Group of one: no ordinal. Group of N: item k of N (group-local).
 */
export function savedReportActionName(
  action: "Download" | "Copy Markdown" | "Delete",
  report: ReportSummary,
  group: SavedReportActionGroup,
): string {
  const context = savedReportHumanContext(report);
  let name: string;
  if (action === "Download") {
    name = `Download ${context}`;
  } else if (action === "Copy Markdown") {
    name = `Copy Markdown from ${context}`;
  } else {
    name = `Delete ${context}`;
  }
  if (group.groupSize > 1) {
    name = `${name}, item ${group.groupIndex + 1} of ${group.groupSize}`;
  }
  return name;
}
