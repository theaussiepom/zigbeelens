import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { DrawerSection } from "@/components/meshGraph/DrawerShell";
import {
  buildSnapshotHistoryViewModel,
  defaultSelectedSnapshotId,
  errorSnapshotHistoryViewModel,
  loadingSnapshotHistoryViewModel,
  type AvailabilityPillViewModel,
  type SnapshotComparisonViewModel,
  type SnapshotHistoryRowViewModel,
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
    <li key={row.snapshotId}>
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

/**
 * Device-led snapshot compare inside the Device details panel.
 *
 * Renders a ViewModel built from the snapshot-history API. Selecting a row
 * only updates this panel — it never moves nodes or connection controls.
 */
export function SnapshotHistorySection({
  networkId,
  deviceIeee,
}: {
  networkId: string;
  deviceIeee: string;
}) {
  const [history, setHistory] = useState<Awaited<
    ReturnType<typeof api.topologyDeviceSnapshotHistory>
  > | null>(null);
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
        setSelectedSnapshotId(defaultSelectedSnapshotId(data));
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

  const viewModel = useMemo(() => {
    if (loading) return loadingSnapshotHistoryViewModel();
    if (error || !history) return errorSnapshotHistoryViewModel();
    return buildSnapshotHistoryViewModel(history, selectedSnapshotId);
  }, [loading, error, history, selectedSnapshotId]);

  return (
    <DrawerSection title={viewModel.sectionTitle}>
      <div data-testid="snapshot-history-section" className="space-y-3">
        {viewModel.loadState === "loading" ? (
          <p className="text-xs text-zl-muted">Loading snapshot history…</p>
        ) : viewModel.loadState === "error" ? (
          <p className="text-xs text-zl-muted">{viewModel.unavailableCopy}</p>
        ) : (
          <>
            {viewModel.trackingOffBanner && (
              <CoverageBanner pill={viewModel.trackingOffBanner} />
            )}
            {viewModel.selectedCoverageBanner && (
              <CoverageBanner pill={viewModel.selectedCoverageBanner} />
            )}

            {viewModel.latestSummary && (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.latestLabel}
                </p>
                <p className="mt-0.5 text-xs text-zl-text">
                  {relativeTime(history?.latest_snapshot?.captured_at ?? undefined)} ·{" "}
                  {viewModel.latestSummary}
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
                        onSelect={setSelectedSnapshotId}
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
    </DrawerSection>
  );
}
