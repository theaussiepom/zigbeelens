import { useState, type ReactNode } from "react";
import type {
  SnapshotCompareChange,
  SnapshotCompareChangeType,
  SnapshotCompareDetail,
} from "@/lib/api";
import { formatTime, relativeTime } from "@/lib/format";
import {
  COMPARE_CHURN_CAVEAT,
  COMPARE_CHURN_GROUP_NEIGHBOUR,
  COMPARE_CHURN_GROUP_ROUTE,
  COMPARE_CLEAR_LABEL,
  COMPARE_FOCUS_LABEL_PREFIX,
  COMPARE_GROUP_TITLES,
  COMPARE_NO_CHANGES_COPY,
  COMPARE_NOT_ENOUGH_HISTORY_COPY,
  COMPARE_PANEL_TITLE,
  COMPARE_POINT_IN_TIME_CAVEAT,
  COMPARE_SECTION_CHURN,
  COMPARE_SECTION_DETAILS,
  COMPARE_SECTION_SUMMARY,
  COMPARE_SECTION_WORTH_REVIEWING,
  COMPARE_WORTH_REVIEWING_EMPTY,
} from "@/lib/meshGraphCopy";

/**
 * "Snapshot compare" — investigation-first snapshot comparison panel.
 *
 * Compares two point-in-time evidence captures and leads with what is worth
 * reviewing, not a raw diff. Structure: snapshot pair, calm change summary
 * (churn level), device-centric worth-reviewing insights, the aggregate
 * churn counts under their own clearly-labelled section, and clickable
 * detail categories collapsed by default. Selecting an item drives the
 * visual graph focus and opens the relevant details panel. Compare is an
 * overlay on existing evidence — it never moves nodes, never changes
 * connection-control choices, and never invents evidence classes.
 */

/** Deterministic detail group ordering: worth-reviewing first, then route,
 * then device, then neighbour categories. */
const DETAIL_GROUP_ORDER: SnapshotCompareChangeType[] = [
  "new_route_hint",
  "missing_route_hint",
  "changed_route_hint",
  "newly_observed_device",
  "device_no_topology_evidence",
  "missing_neighbour_link",
  "new_neighbour_link",
  "changed_neighbour_link",
];

const INSIGHT_GROUP_ORDER: SnapshotCompareChangeType[] = [
  "issue_linked_topology_change",
  "no_latest_neighbour_evidence_after_previous",
  "large_router_evidence_change",
];

/** Groups larger than this start collapsed to keep the panel scannable. */
const GROUP_COLLAPSED_THRESHOLD = 6;

function snapshotLabel(
  kind: "latest" | "previous",
  snapshot: { captured_at?: string | null } | null,
): string {
  const prefix =
    kind === "latest" ? "Latest usable snapshot" : "Previous usable snapshot";
  if (!snapshot?.captured_at) return prefix;
  return `${prefix} — captured ${relativeTime(snapshot.captured_at)}`;
}

function Section({
  title,
  defaultOpen,
  children,
}: {
  title: string;
  defaultOpen: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section aria-label={title}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={title}
        className="flex w-full items-baseline justify-between gap-2 text-left"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
          {title}
        </span>
        <span className="shrink-0 text-[10px] text-zl-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="mt-1.5 space-y-2">{children}</div>}
    </section>
  );
}

function ChangeGroup({
  title,
  changes,
  activeChangeId,
  onSelectChange,
}: {
  title: string;
  changes: SnapshotCompareChange[];
  activeChangeId: string | null;
  onSelectChange: (change: SnapshotCompareChange) => void;
}) {
  const [open, setOpen] = useState(changes.length <= GROUP_COLLAPSED_THRESHOLD);
  return (
    <div data-testid="compare-change-group">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`View ${title.toLowerCase()}, ${changes.length} ${
          changes.length === 1 ? "item" : "items"
        }`}
        className="flex w-full items-baseline justify-between gap-2 text-left"
      >
        <span className="text-[11px] font-semibold text-zl-text">{title}</span>
        <span className="shrink-0 text-[10px] text-zl-muted">
          {changes.length} {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {changes.map((change) => {
            const active = change.id === activeChangeId;
            return (
              <li key={change.id}>
                <button
                  type="button"
                  data-testid="compare-change"
                  onClick={() => onSelectChange(change)}
                  aria-pressed={active}
                  className={`w-full rounded-lg border p-2 text-left text-[11px] leading-snug ${
                    active
                      ? "border-zl-accent bg-zl-accent/10 text-zl-text"
                      : "border-zl-border bg-zl-surface-2 text-zl-muted hover:border-zl-accent/40"
                  }`}
                >
                  <span className="block font-medium text-zl-text">{change.title}</span>
                  {active && (
                    <span className="mt-1 block space-y-1">
                      <span className="block">{change.summary}</span>
                      {change.supporting_evidence.length > 0 && (
                        <span className="block">
                          {change.supporting_evidence.map((item) => (
                            <span key={item} className="block">
                              {item}
                            </span>
                          ))}
                        </span>
                      )}
                      <span className="block text-zl-muted">{change.practical_note}</span>
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Non-zero churn count rows for one evidence type; zero rows stay silent. */
function ChurnGroup({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; count: number }>;
}) {
  const visible = rows.filter((row) => row.count > 0);
  if (visible.length === 0) return null;
  return (
    <div>
      <p className="text-[11px] font-semibold text-zl-text">{title}</p>
      <ul className="mt-0.5 space-y-0.5 text-[11px] leading-snug text-zl-muted">
        {visible.map((row) => (
          <li key={row.label}>
            {row.count.toLocaleString("en-US")} {row.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Aggregated worth-reviewing summary lines, one per insight type present. */
function worthReviewingSummaryLines(insights: SnapshotCompareChange[]): string[] {
  const countOf = (type: SnapshotCompareChangeType) =>
    insights.filter((insight) => insight.type === type).length;
  const lines: string[] = [];
  const issueLinked = countOf("issue_linked_topology_change");
  if (issueLinked > 0) {
    lines.push(
      `${issueLinked} ${issueLinked === 1 ? "device" : "devices"} with current issues also changed topology evidence.`,
    );
  }
  const noLatest = countOf("no_latest_neighbour_evidence_after_previous");
  if (noLatest > 0) {
    lines.push(
      `${noLatest} ${noLatest === 1 ? "device" : "devices"} had neighbour evidence in the previous snapshot but none in the latest usable snapshot.`,
    );
  }
  const largeRouter = countOf("large_router_evidence_change");
  if (largeRouter > 0) {
    lines.push(
      `${largeRouter} ${largeRouter === 1 ? "router has" : "routers have"} a large change in observed neighbour evidence.`,
    );
  }
  return lines;
}

export function SnapshotComparePanel({
  compare,
  loading,
  error,
  activeChangeId,
  onSelectChange,
  onClearCompare,
}: {
  compare: SnapshotCompareDetail | null;
  loading: boolean;
  error: string | null;
  activeChangeId: string | null;
  onSelectChange: (change: SnapshotCompareChange) => void;
  onClearCompare: () => void;
}) {
  const changes = compare?.has_comparison ? compare.changes : [];
  const insights = compare?.has_comparison ? (compare.worth_reviewing ?? []) : [];
  const counts = compare?.counts;

  const detailGroups = DETAIL_GROUP_ORDER.map((type) => ({
    type,
    title: COMPARE_GROUP_TITLES[type],
    changes: changes.filter((change) => change.type === type),
  })).filter((group) => group.changes.length > 0);

  const insightGroups = INSIGHT_GROUP_ORDER.map((type) => ({
    type,
    title: COMPARE_GROUP_TITLES[type],
    changes: insights.filter((insight) => insight.type === type),
  })).filter((group) => group.changes.length > 0);

  const neighbourChurn = counts
    ? [
        { label: "seen in latest snapshot only", count: counts.new_neighbour_links },
        {
          label: "seen in previous snapshot only",
          count: counts.neighbour_links_not_present_latest,
        },
        { label: "with changed evidence", count: counts.changed_neighbour_links },
      ]
    : [];
  const routeChurn = counts
    ? [
        { label: "seen in latest snapshot only", count: counts.new_route_hints },
        {
          label: "seen in previous snapshot only",
          count: counts.route_hints_not_present_latest,
        },
        { label: "with changed evidence", count: counts.changed_route_hints },
      ]
    : [];
  const hasLinkChurn = [...neighbourChurn, ...routeChurn].some((row) => row.count > 0);

  const activeItem =
    activeChangeId !== null
      ? ([...changes, ...insights].find((item) => item.id === activeChangeId) ?? null)
      : null;

  return (
    <div role="region" aria-label={COMPARE_PANEL_TITLE} className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
          {COMPARE_PANEL_TITLE}
        </h3>
        <button
          type="button"
          onClick={onClearCompare}
          aria-label={COMPARE_CLEAR_LABEL}
          className="text-[11px] text-zl-accent hover:underline"
        >
          {COMPARE_CLEAR_LABEL}
        </button>
      </div>

      {loading ? (
        <p className="text-[11px] text-zl-muted">Comparing snapshots…</p>
      ) : error ? (
        <p className="text-[11px] text-zl-muted">{error}</p>
      ) : !compare || !compare.has_comparison ? (
        <p className="text-[11px] leading-snug text-zl-muted" data-testid="compare-empty">
          {COMPARE_NOT_ENOUGH_HISTORY_COPY}
        </p>
      ) : (
        <>
          {activeItem && (
            <p
              data-testid="compare-focus-label"
              className="rounded-lg border border-zl-accent/40 bg-zl-accent/10 px-2 py-1 text-[11px] leading-snug text-zl-text"
            >
              {COMPARE_FOCUS_LABEL_PREFIX}
              {COMPARE_GROUP_TITLES[activeItem.type] ?? activeItem.title}
            </p>
          )}

          <div className="space-y-0.5 text-[11px] leading-snug text-zl-muted">
            <p title={formatTime(compare.compare_snapshot?.captured_at ?? undefined)}>
              {snapshotLabel("latest", compare.compare_snapshot)}
            </p>
            <p title={formatTime(compare.base_snapshot?.captured_at ?? undefined)}>
              {snapshotLabel("previous", compare.base_snapshot)}
            </p>
          </div>

          <p className="border-l-2 border-zl-border pl-2 text-[11px] leading-snug text-zl-muted">
            {COMPARE_POINT_IN_TIME_CAVEAT}
          </p>

          {compare.limitations.map((limitation) => (
            <p
              key={limitation}
              className="border-l-2 border-zl-watch/40 pl-2 text-[11px] leading-snug text-zl-muted"
            >
              {limitation}
            </p>
          ))}

          {changes.length === 0 ? (
            <p className="text-[11px] leading-snug text-zl-muted" data-testid="compare-empty">
              {COMPARE_NO_CHANGES_COPY}
            </p>
          ) : (
            <>
              <div data-testid="compare-summary">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {COMPARE_SECTION_SUMMARY}
                </p>
                <p className="mt-0.5 text-[11px] leading-snug text-zl-text">
                  {compare.summary}
                </p>
              </div>

              <Section title={COMPARE_SECTION_WORTH_REVIEWING} defaultOpen>
                {insights.length === 0 ? (
                  <p
                    className="text-[11px] leading-snug text-zl-muted"
                    data-testid="compare-worth-reviewing-empty"
                  >
                    {COMPARE_WORTH_REVIEWING_EMPTY}
                  </p>
                ) : (
                  <>
                    <ul
                      className="space-y-0.5 text-[11px] leading-snug text-zl-text"
                      data-testid="compare-worth-reviewing-summary"
                    >
                      {worthReviewingSummaryLines(insights).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                    {insightGroups.map((group) => (
                      <ChangeGroup
                        key={group.type}
                        title={group.title}
                        changes={group.changes}
                        activeChangeId={activeChangeId}
                        onSelectChange={onSelectChange}
                      />
                    ))}
                  </>
                )}
              </Section>

              {hasLinkChurn && (
                <Section title={COMPARE_SECTION_CHURN} defaultOpen>
                  <div data-testid="compare-churn" className="space-y-2">
                    <p className="text-[11px] leading-snug text-zl-muted">
                      {COMPARE_CHURN_CAVEAT}
                    </p>
                    <ChurnGroup
                      title={COMPARE_CHURN_GROUP_NEIGHBOUR}
                      rows={neighbourChurn}
                    />
                    <ChurnGroup title={COMPARE_CHURN_GROUP_ROUTE} rows={routeChurn} />
                  </div>
                </Section>
              )}

              <Section title={COMPARE_SECTION_DETAILS} defaultOpen={false}>
                {detailGroups.map((group) => (
                  <ChangeGroup
                    key={group.type}
                    title={group.title}
                    changes={group.changes}
                    activeChangeId={activeChangeId}
                    onSelectChange={onSelectChange}
                  />
                ))}
              </Section>
            </>
          )}
        </>
      )}
    </div>
  );
}
