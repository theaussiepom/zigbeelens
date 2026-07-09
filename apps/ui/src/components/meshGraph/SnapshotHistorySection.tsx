import { useEffect, useState } from "react";
import {
  api,
  type DeviceSnapshotComparison,
  type DeviceSnapshotHistoryDetail,
  type DeviceSnapshotHistoryRow,
} from "@/lib/api";
import { formatTime, relativeTime } from "@/lib/format";
import {
  AVAILABILITY_PILL_BUILDING,
  AVAILABILITY_PILL_BUILDING_HELPER,
  AVAILABILITY_PILL_OFF,
  AVAILABILITY_PILL_OFF_HELPER,
  AVAILABILITY_PILL_UNKNOWN,
  AVAILABILITY_PILL_UNKNOWN_HELPER,
  SNAPSHOT_COMPARE_MEANING,
  SNAPSHOT_COMPARE_ROW_STATUS_LABELS,
  SNAPSHOT_COMPARE_STATUS_LABELS,
  SNAPSHOT_COMPARE_STATUS_LEADS,
  SNAPSHOT_HISTORY_CHECKS_TITLE,
  SNAPSHOT_HISTORY_COMPARE_WITH_LABEL,
  SNAPSHOT_HISTORY_EMPTY_COPY,
  SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE,
  SNAPSHOT_HISTORY_LATEST_LABEL,
  SNAPSHOT_HISTORY_MEANING_TITLE,
  SNAPSHOT_HISTORY_ROUTE_HINT_NOTE,
  SNAPSHOT_HISTORY_SECTION_TITLE,
  SNAPSHOT_HISTORY_SELECTED_ONLY_NOTE,
  SNAPSHOT_HISTORY_SOURCE_NOTE,
  SNAPSHOT_HISTORY_UNAVAILABLE_COPY,
  SNAPSHOT_HISTORY_WHY_TITLE,
} from "@/lib/meshGraphCopy";
import { DrawerSection } from "@/components/meshGraph/DrawerShell";

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** "7 links shown · 2 route hints" — plain language, never raw field names. */
function rowCountsCopy(row: DeviceSnapshotHistoryRow): string {
  const links = `${plural(row.links_for_device_count, "link")} shown`;
  const routes =
    row.route_hints_for_device_count > 0
      ? plural(row.route_hints_for_device_count, "route hint")
      : "no route hints";
  return `${links} · ${routes}`;
}

function availabilityStateCopy(row: DeviceSnapshotHistoryRow): string | null {
  if (row.availability_state_near_snapshot === "online") return "Online";
  if (row.availability_state_near_snapshot === "offline") return "Offline";
  return null;
}

/** Availability coverage pill for a snapshot period, or null when coverage
 * is adequate (no badge is fine when the evidence is there). */
function AvailabilityPill({ status }: { status: DeviceSnapshotHistoryRow["availability_coverage_status"] }) {
  if (status === "off") {
    return (
      <span
        className="inline-flex items-center rounded-full border border-zl-unavailable/40 bg-zl-unavailable/10 px-2 py-0.5 text-[11px] font-medium text-zl-unavailable"
        title={AVAILABILITY_PILL_OFF_HELPER}
      >
        {AVAILABILITY_PILL_OFF}
      </span>
    );
  }
  if (status === "building") {
    return (
      <span
        className="inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-2 py-0.5 text-[11px] font-medium text-zl-watch"
        title={AVAILABILITY_PILL_BUILDING_HELPER}
      >
        {AVAILABILITY_PILL_BUILDING}
      </span>
    );
  }
  if (status === "unknown") {
    return (
      <span
        className="inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-muted"
        title={AVAILABILITY_PILL_UNKNOWN_HELPER}
      >
        {AVAILABILITY_PILL_UNKNOWN}
      </span>
    );
  }
  return null;
}

/** Evidence-details count lines in plain "links shown / selected snapshot"
 * language. Zero-difference lines are summarised, not listed. */
function evidenceDetailLines(comparison: DeviceSnapshotComparison): {
  links: string[];
  routes: string[];
} {
  const link = comparison.link_counts;
  const links = [
    `${plural(link.latest_count, "link")} shown in latest snapshot`,
    `${plural(link.selected_count, "link")} shown in selected snapshot`,
  ];
  if (link.latest_only_count > 0)
    links.push(`${plural(link.latest_only_count, "link")} only in latest snapshot`);
  if (link.selected_only_count > 0)
    links.push(`${plural(link.selected_only_count, "link")} only in selected snapshot`);
  if (link.changed_count > 0) links.push(`${plural(link.changed_count, "link")} changed`);

  const route = comparison.route_hint_counts;
  const routes = [
    `${plural(route.latest_count, "route hint")} in latest snapshot`,
    `${plural(route.selected_count, "route hint")} in selected snapshot`,
  ];
  const routeDifferences =
    route.latest_only_count + route.selected_only_count + route.changed_count;
  if (routeDifferences === 0) {
    routes.push("No route-hint difference");
  } else {
    if (route.latest_only_count > 0)
      routes.push(`${plural(route.latest_only_count, "route hint")} only in latest snapshot`);
    if (route.selected_only_count > 0)
      routes.push(
        `${plural(route.selected_only_count, "route hint")} only in selected snapshot`,
      );
    if (route.changed_count > 0)
      routes.push(`${plural(route.changed_count, "route hint")} changed`);
  }
  return { links, routes };
}

/** The comparison card: status first, then why, meaning, suggested checks,
 * and raw counts collapsed behind Evidence details. */
function ComparisonCard({ comparison }: { comparison: DeviceSnapshotComparison }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const details = evidenceDetailLines(comparison);
  const showSelectedOnlyNote = comparison.link_counts.selected_only_count > 0;
  const showRouteNote =
    comparison.route_hint_counts.latest_only_count +
      comparison.route_hint_counts.selected_only_count +
      comparison.route_hint_counts.changed_count >
    0;

  return (
    <div className="space-y-3" data-testid="snapshot-comparison-card">
      <div>
        <p className="text-sm font-semibold text-zl-text">
          {SNAPSHOT_COMPARE_STATUS_LABELS[comparison.status]}
        </p>
        <p className="mt-0.5 text-xs text-zl-muted">
          {SNAPSHOT_COMPARE_STATUS_LEADS[comparison.status]}
        </p>
      </div>

      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
          {SNAPSHOT_HISTORY_WHY_TITLE}
        </h4>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
          {comparison.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
          {SNAPSHOT_HISTORY_MEANING_TITLE}
        </h4>
        <p className="mt-1 text-xs text-zl-muted">
          {SNAPSHOT_COMPARE_MEANING[comparison.status]}
        </p>
      </div>

      {comparison.suggested_checks.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
            {SNAPSHOT_HISTORY_CHECKS_TITLE}
          </h4>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
            {comparison.suggested_checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <button
          type="button"
          aria-expanded={detailsOpen}
          aria-label={SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE}
          onClick={() => setDetailsOpen((open) => !open)}
          className="text-[11px] font-semibold uppercase tracking-wide text-zl-accent hover:underline"
        >
          {SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE} {detailsOpen ? "▾" : "▸"}
        </button>
        {detailsOpen && (
          <div className="mt-2 space-y-2 text-xs" data-testid="snapshot-evidence-details">
            <div>
              <p className="font-medium text-zl-text">Links</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-zl-muted">
                {details.links.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-zl-text">Route hints</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-zl-muted">
                {details.routes.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            {showSelectedOnlyNote && (
              <p className="text-zl-muted">{SNAPSHOT_HISTORY_SELECTED_ONLY_NOTE}</p>
            )}
            {showRouteNote && <p className="text-zl-muted">{SNAPSHOT_HISTORY_ROUTE_HINT_NOTE}</p>}
            <p className="text-zl-muted">{SNAPSHOT_HISTORY_SOURCE_NOTE}</p>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Device-led snapshot compare inside the Device details panel.
 *
 * Answers "how does this device look in the latest snapshot compared with
 * earlier snapshots?" — a list of recent usable snapshots (previous usable
 * selected by default, older ones selectable) and an actionable comparison
 * card. Selecting a snapshot only updates this panel: it never moves nodes,
 * never recomputes layout and never touches connection controls.
 */
export function SnapshotHistorySection({
  networkId,
  deviceIeee,
}: {
  networkId: string;
  deviceIeee: string;
}) {
  const [history, setHistory] = useState<DeviceSnapshotHistoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHistory(null);
    setLoading(true);
    setError(false);
    setSelectedSnapshotId(null);
    api.topologyDeviceSnapshotHistory(networkId, deviceIeee).then(
      (data) => {
        if (cancelled) return;
        setHistory(data);
        // Default comparison: the previous usable snapshot.
        setSelectedSnapshotId(data.snapshots[0]?.snapshot_id ?? null);
        setLoading(false);
      },
      () => {
        if (cancelled) return;
        setError(true);
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [networkId, deviceIeee]);

  const selectedRow =
    history?.snapshots.find((row) => row.snapshot_id === selectedSnapshotId) ?? null;

  return (
    <DrawerSection title={SNAPSHOT_HISTORY_SECTION_TITLE}>
      <div data-testid="snapshot-history-section" className="space-y-3">
        {loading ? (
          <p className="text-xs text-zl-muted">Loading snapshot history…</p>
        ) : error || !history ? (
          <p className="text-xs text-zl-muted">{SNAPSHOT_HISTORY_UNAVAILABLE_COPY}</p>
        ) : (
          <>
            {!history.availability_tracking.enabled && (
              <div className="space-y-1">
                <AvailabilityPill status="off" />
                <p className="text-[11px] leading-snug text-zl-muted">
                  {AVAILABILITY_PILL_OFF_HELPER}
                </p>
              </div>
            )}
            {history.availability_tracking.enabled &&
              selectedRow?.availability_coverage_status === "building" && (
                <div className="space-y-1">
                  <AvailabilityPill status="building" />
                  <p className="text-[11px] leading-snug text-zl-muted">
                    {AVAILABILITY_PILL_BUILDING_HELPER}
                  </p>
                </div>
              )}
            {history.availability_tracking.enabled &&
              selectedRow?.availability_coverage_status === "unknown" && (
                <div className="space-y-1">
                  <AvailabilityPill status="unknown" />
                  <p className="text-[11px] leading-snug text-zl-muted">
                    {AVAILABILITY_PILL_UNKNOWN_HELPER}
                  </p>
                </div>
              )}

            {history.latest_snapshot && (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {SNAPSHOT_HISTORY_LATEST_LABEL}
                </p>
                <p
                  className="mt-0.5 text-xs text-zl-text"
                  title={formatTime(history.latest_snapshot.captured_at ?? undefined)}
                >
                  {relativeTime(history.latest_snapshot.captured_at ?? undefined)} ·{" "}
                  {rowCountsCopy(history.latest_snapshot)}
                  {availabilityStateCopy(history.latest_snapshot)
                    ? ` · ${availabilityStateCopy(history.latest_snapshot)}`
                    : ""}
                </p>
              </div>
            )}

            {history.snapshots.length === 0 ? (
              <p className="text-xs text-zl-muted">{SNAPSHOT_HISTORY_EMPTY_COPY}</p>
            ) : (
              <>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                    {SNAPSHOT_HISTORY_COMPARE_WITH_LABEL}
                  </p>
                  <ul className="mt-1 space-y-1" data-testid="snapshot-history-list">
                    {history.snapshots.map((row) => {
                      const selected = row.snapshot_id === selectedSnapshotId;
                      const statusLabel = row.comparison_to_latest
                        ? SNAPSHOT_COMPARE_ROW_STATUS_LABELS[row.comparison_to_latest.status]
                        : null;
                      const coveragePill =
                        row.availability_coverage_status !== "tracked" ? (
                          <AvailabilityPill status={row.availability_coverage_status} />
                        ) : null;
                      const stateCopy = availabilityStateCopy(row);
                      return (
                        <li key={row.snapshot_id}>
                          <button
                            type="button"
                            aria-pressed={selected}
                            onClick={() => setSelectedSnapshotId(row.snapshot_id)}
                            title={formatTime(row.captured_at ?? undefined)}
                            className={`w-full rounded-lg border px-2.5 py-1.5 text-left text-xs ${
                              selected
                                ? "border-zl-accent bg-zl-accent/10 text-zl-text"
                                : "border-zl-border bg-zl-surface-2 text-zl-text hover:border-zl-accent/40"
                            }`}
                          >
                            <span className="font-medium">
                              {relativeTime(row.captured_at ?? undefined)}
                            </span>
                            <span className="block text-zl-muted">
                              {rowCountsCopy(row)}
                              {statusLabel ? ` · ${statusLabel}` : ""}
                              {stateCopy ? ` · ${stateCopy}` : ""}
                            </span>
                            {coveragePill && <span className="mt-1 block">{coveragePill}</span>}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>

                {selectedRow?.comparison_to_latest && (
                  <ComparisonCard comparison={selectedRow.comparison_to_latest} />
                )}
              </>
            )}
          </>
        )}
      </div>
    </DrawerSection>
  );
}
