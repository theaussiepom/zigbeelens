import { useState } from "react";
import type { SnapshotCompareChange, SnapshotCompareDetail } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import {
  COMPARE_CLEAR_LABEL,
  COMPARE_GROUP_TITLES,
  COMPARE_NO_CHANGES_COPY,
  COMPARE_NOT_ENOUGH_HISTORY_COPY,
  COMPARE_PANEL_TITLE,
} from "@/lib/meshGraphCopy";

/**
 * "What changed" — snapshot comparison panel.
 *
 * Renders the backend snapshot comparison: which snapshot pair was compared,
 * a summary of non-zero change categories, and grouped changes. Selecting a
 * change drives the visual graph focus and opens the relevant details panel.
 * Compare is an overlay on existing evidence — it never moves nodes, never
 * changes connection-control choices, and never invents evidence classes.
 */

/** Deterministic group ordering, matching backend category priority. */
const GROUP_ORDER = [
  "new_route_hint",
  "missing_route_hint",
  "changed_route_hint",
  "newly_observed_device",
  "device_no_topology_evidence",
  "missing_neighbour_link",
  "new_neighbour_link",
  "changed_neighbour_link",
] as const;

/** Groups larger than this start collapsed to keep the panel scannable. */
const GROUP_COLLAPSED_THRESHOLD = 6;

function snapshotLabel(
  kind: "latest" | "previous",
  snapshot: { captured_at?: string | null } | null,
): string {
  const prefix = kind === "latest" ? "Latest snapshot" : "Previous snapshot";
  if (!snapshot?.captured_at) return prefix;
  return `${prefix} — captured ${relativeTime(snapshot.captured_at)}`;
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
  const groups =
    compare?.has_comparison && compare.changes.length > 0
      ? GROUP_ORDER.map((type) => ({
          type,
          title: COMPARE_GROUP_TITLES[type],
          changes: compare.changes.filter((change) => change.type === type),
        })).filter((group) => group.changes.length > 0)
      : [];

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
          <div className="space-y-0.5 text-[11px] leading-snug text-zl-muted">
            <p>{snapshotLabel("latest", compare.compare_snapshot)}</p>
            <p>{snapshotLabel("previous", compare.base_snapshot)}</p>
          </div>

          {compare.changes.length === 0 ? (
            <p className="text-[11px] leading-snug text-zl-muted" data-testid="compare-empty">
              {COMPARE_NO_CHANGES_COPY}
            </p>
          ) : (
            <>
              <div data-testid="compare-summary">
                <p className="text-[11px] leading-snug text-zl-text">{compare.summary}</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-snug text-zl-muted">
                  {compare.summary_items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="space-y-2">
                {groups.map((group) => (
                  <ChangeGroup
                    key={group.type}
                    title={group.title}
                    changes={group.changes}
                    activeChangeId={activeChangeId}
                    onSelectChange={onSelectChange}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
