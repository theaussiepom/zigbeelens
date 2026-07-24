import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useLiveResource } from "@/hooks/useLiveResource";
import { RAW_TOPOLOGY_HISTORY_EVENTS } from "@/lib/liveResourceEvents";
import {
  SNAPSHOT_HISTORY_REFRESH_FAILED_COPY,
} from "@/lib/meshGraphCopy";
import { topologySnapshotPath } from "@/lib/routes";
import {
  buildSnapshotHistoryViewModel,
  defaultSelectedSnapshotId,
  errorSnapshotHistoryViewModel,
  loadingSnapshotHistoryViewModel,
  type AvailabilityPillViewModel,
  type SnapshotComparisonViewModel,
  type SnapshotHistoryRowViewModel,
  type SnapshotHistoryViewModel,
} from "@/viewModels/topology/snapshotHistoryViewModel";

function pillClassName(tone: AvailabilityPillViewModel["tone"]): string {
  if (tone === "coverage") {
    return "inline-flex items-center rounded-full border border-zl-unavailable/40 bg-zl-unavailable/10 px-2 py-0.5 text-[11px] font-medium text-zl-unavailable";
  }
  if (tone === "watch") {
    return "inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-2 py-0.5 text-[11px] font-medium text-zl-watch";
  }
  return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-muted";
}

function AvailabilityPill({ pill }: { pill: AvailabilityPillViewModel }) {
  return (
    <span className={pillClassName(pill.tone)} title={pill.helper}>
      {pill.label}
    </span>
  );
}

function CoverageBanner({ pill }: { pill: AvailabilityPillViewModel }) {
  return (
    <div className="space-y-1">
      <AvailabilityPill pill={pill} />
      <p className="text-[11px] leading-snug text-zl-muted">{pill.helper}</p>
    </div>
  );
}

function ComparisonCard({ comparison }: { comparison: SnapshotComparisonViewModel }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const { evidenceDetails } = comparison;

  return (
    <div className="space-y-3" data-testid="snapshot-comparison-card">
      <div>
        <p className="text-sm font-semibold text-zl-text">{comparison.statusLabel}</p>
        <p className="mt-0.5 text-xs text-zl-muted">{comparison.statusLead}</p>
      </div>

      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
          {comparison.whyTitle}
        </h4>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
          {comparison.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
          {comparison.meaningTitle}
        </h4>
        <p className="mt-1 text-xs text-zl-muted">{comparison.meaningText}</p>
      </div>

      {comparison.suggestedChecks.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
            {comparison.checksTitle}
          </h4>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
            {comparison.suggestedChecks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <button
          type="button"
          aria-expanded={detailsOpen}
          aria-label={comparison.evidenceDetailsTitle}
          onClick={() => setDetailsOpen((open) => !open)}
          className="text-[11px] font-semibold uppercase tracking-wide text-zl-accent hover:underline"
        >
          {comparison.evidenceDetailsTitle} {detailsOpen ? "▾" : "▸"}
        </button>
        {detailsOpen && (
          <div className="mt-2 space-y-2 text-xs" data-testid="snapshot-evidence-details">
            <div>
              <p className="font-medium text-zl-text">Links</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-zl-muted">
                {evidenceDetails.linkLines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-zl-text">Route hints</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-zl-muted">
                {evidenceDetails.routeLines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            {evidenceDetails.showSelectedOnlyNote && (
              <p className="text-zl-muted">{evidenceDetails.selectedOnlyNote}</p>
            )}
            {evidenceDetails.showRouteNote && (
              <p className="text-zl-muted">{evidenceDetails.routeHintNote}</p>
            )}
            <p className="text-zl-muted">{evidenceDetails.sourceNote}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function SnapshotHistoryRowButton({
  row,
  onSelect,
}: {
  row: SnapshotHistoryRowViewModel;
  onSelect: (snapshotId: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-pressed={row.selected}
        onClick={() => onSelect(row.snapshotId)}
        title={row.capturedAtTitle}
        className={`w-full rounded-lg border px-2.5 py-1.5 text-left text-xs ${
          row.selected
            ? "border-zl-accent bg-zl-accent/10 text-zl-text"
            : "border-zl-border bg-zl-surface-2 text-zl-text hover:border-zl-accent/40"
        }`}
      >
        <span className="font-medium">{row.relativeLabel}</span>
        <span className="block text-zl-muted">
          {row.countsText}
          {row.statusLabel ? ` · ${row.statusLabel}` : ""}
          {row.availabilityStateText ? ` · ${row.availabilityStateText}` : ""}
        </span>
        {row.coveragePill && (
          <span className="mt-1 block">
            <AvailabilityPill pill={row.coveragePill} />
          </span>
        )}
      </button>
    </li>
  );
}

function RefreshWarning({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      data-testid="snapshot-history-refresh-warning"
      className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-3 py-2 text-xs text-zl-watch"
    >
      <p>{SNAPSHOT_HISTORY_REFRESH_FAILED_COPY}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 min-h-11 text-sm font-medium text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
      >
        Retry
      </button>
    </div>
  );
}

/**
 * Renders snapshot-history loading/error/ready content only.
 * Does not own fetching, selection, or page/drawer chrome.
 */
export function SnapshotHistoryContent({
  viewModel,
  onSelectSnapshot,
  refreshFailed = false,
  onRetryRefresh,
}: {
  viewModel: SnapshotHistoryViewModel;
  onSelectSnapshot: (snapshotId: string) => void;
  refreshFailed?: boolean;
  onRetryRefresh?: () => void;
}) {
  return (
    <div data-testid="snapshot-history-section" className="space-y-3">
      {viewModel.loadState === "loading" ? (
        <p className="text-xs text-zl-muted">Loading snapshot history…</p>
      ) : viewModel.loadState === "error" ? (
        <p className="text-xs text-zl-muted">{viewModel.unavailableCopy}</p>
      ) : (
        <>
          {refreshFailed && onRetryRefresh && <RefreshWarning onRetry={onRetryRefresh} />}
          {viewModel.trackingOffBanner && (
            <CoverageBanner pill={viewModel.trackingOffBanner} />
          )}
          {viewModel.selectedCoverageBanner && (
            <CoverageBanner pill={viewModel.selectedCoverageBanner} />
          )}

          {viewModel.latest && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                {viewModel.latestLabel}
              </p>
              <p
                className="mt-0.5 text-xs text-zl-text"
                title={viewModel.latest.capturedAtTitle}
              >
                {viewModel.latest.relativeLabel} · {viewModel.latest.summaryText}
              </p>
            </div>
          )}

          {viewModel.rows.length === 0 ? (
            <p className="text-xs text-zl-muted">{viewModel.emptyCopy}</p>
          ) : (
            <>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.compareWithLabel}
                </p>
                <ul className="mt-1 space-y-1" data-testid="snapshot-history-list">
                  {viewModel.rows.map((row) => (
                    <SnapshotHistoryRowButton
                      key={row.snapshotId}
                      row={row}
                      onSelect={onSelectSnapshot}
                    />
                  ))}
                </ul>
              </div>

              {viewModel.comparison && <ComparisonCard comparison={viewModel.comparison} />}
            </>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Owns snapshot-history fetching, selection, and ViewModel construction.
 * Parent surfaces supply chrome (Card, DrawerSection, etc.).
 */
export function DeviceSnapshotHistory({
  networkId,
  deviceIeee,
  showHeading = false,
  showRawSnapshotLink = false,
}: {
  networkId: string;
  deviceIeee: string;
  showHeading?: boolean;
  showRawSnapshotLink?: boolean;
}) {
  const history = useLiveResource(
    () => api.topologyDeviceSnapshotHistory(networkId, deviceIeee),
    [networkId, deviceIeee],
    { refetchOn: RAW_TOPOLOGY_HISTORY_EVENTS },
  );
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);

  // Reset selection when the device/network identity changes. Background
  // topology_updated refetches keep prior history visible until new data arrives.
  useEffect(() => {
    setSelectedSnapshotId(null);
  }, [networkId, deviceIeee]);

  useEffect(() => {
    const data = history.data;
    if (!data) return;
    setSelectedSnapshotId((current) => {
      if (
        current != null &&
        data.snapshots.some((row) => row.snapshot_id === current)
      ) {
        return current;
      }
      return defaultSelectedSnapshotId(data);
    });
  }, [history.data]);

  // Retain last accepted data when a background refresh fails. Only the initial
  // no-data failure uses the section-local unavailable ViewModel.
  const viewModel = useMemo(() => {
    if (history.loading && !history.data) return loadingSnapshotHistoryViewModel();
    if (!history.data) return errorSnapshotHistoryViewModel();
    return buildSnapshotHistoryViewModel(history.data, selectedSnapshotId);
  }, [history.loading, history.data, selectedSnapshotId]);

  const refreshFailed = Boolean(history.data && history.error);

  return (
    <section
      id="snapshot-history"
      data-testid="device-snapshot-history"
      aria-label={viewModel.sectionTitle}
      className="space-y-3"
    >
      {showHeading && (
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          {viewModel.sectionTitle}
        </h2>
      )}
      <SnapshotHistoryContent
        viewModel={viewModel}
        onSelectSnapshot={setSelectedSnapshotId}
        refreshFailed={refreshFailed}
        onRetryRefresh={history.refetch}
      />
      {showRawSnapshotLink && (
        <Link
          to={topologySnapshotPath(networkId)}
          className="inline-flex min-h-11 items-center text-sm text-zl-muted hover:text-zl-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        >
          Raw snapshot →
        </Link>
      )}
    </section>
  );
}
