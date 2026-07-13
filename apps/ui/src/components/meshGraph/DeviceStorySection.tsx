import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { DrawerSection } from "@/components/meshGraph/DrawerShell";
import { EvidenceCoverageStrip } from "@/components/meshGraph/EvidenceCoverageStrip";
import {
  buildDeviceStoryViewModel,
  errorDeviceStoryViewModel,
  loadingDeviceStoryViewModel,
} from "@/viewModels/topology/deviceStoryViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

function statusPillClassName(tone: DecisionPillTone): string {
  if (tone === "coverage") {
    return "inline-flex items-center rounded-full border border-zl-unavailable/40 bg-zl-unavailable/10 px-2 py-0.5 text-[11px] font-medium text-zl-unavailable";
  }
  if (tone === "watch") {
    return "inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-2 py-0.5 text-[11px] font-medium text-zl-watch";
  }
  if (tone === "action") {
    return "inline-flex items-center rounded-full border border-zl-accent/40 bg-zl-accent/10 px-2 py-0.5 text-[11px] font-medium text-zl-accent";
  }
  if (tone === "info") {
    return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-text";
  }
  return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-muted";
}

/**
 * Device story section inside the Device details panel.
 *
 * Fetches the read-only Device Story API and renders a ViewModel built from
 * coded backend output. Does not reinterpret statuses or invent diagnostics.
 */
export function DeviceStorySection({
  networkId,
  deviceIeee,
}: {
  networkId: string;
  deviceIeee: string;
}) {
  const [story, setStory] = useState<Awaited<ReturnType<typeof api.deviceStory>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setStory(null);
    setLoading(true);
    setError(false);
    api.deviceStory(networkId, deviceIeee).then(
      (data) => {
        if (cancelled) return;
        setStory(data);
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
    if (loading) return loadingDeviceStoryViewModel();
    if (error || !story) return errorDeviceStoryViewModel();
    return buildDeviceStoryViewModel(story);
  }, [loading, error, story]);

  return (
    <DrawerSection title={viewModel.sectionTitle}>
      <div data-testid="device-story-section" className="space-y-3">
        {viewModel.loadState === "loading" ? (
          <p className="text-xs text-zl-muted">{viewModel.loadingCopy}</p>
        ) : viewModel.loadState === "error" ? (
          <p className="text-xs text-zl-muted">{viewModel.unavailableCopy}</p>
        ) : (
          <>
            <div>
              {viewModel.statusPill && (
                <span className={statusPillClassName(viewModel.statusPill.tone)}>
                  {viewModel.statusPill.label}
                </span>
              )}
              <p className="mt-2 text-sm font-semibold text-zl-text">{viewModel.headline}</p>
              <p className="mt-0.5 text-xs text-zl-muted">{viewModel.headlineLead}</p>
            </div>

            {viewModel.reasons.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.whyTitle}
                </h4>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
                  {viewModel.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}

            {viewModel.limitations.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.limitationsTitle}
                </h4>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-muted">
                  {viewModel.limitations.map((limitation) => (
                    <li key={limitation}>{limitation}</li>
                  ))}
                </ul>
              </div>
            )}

            {viewModel.suggestedChecks.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.checksTitle}
                </h4>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-text">
                  {viewModel.suggestedChecks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ul>
              </div>
            )}

            {viewModel.coverageItems.length > 0 && (
              <EvidenceCoverageStrip
                title={viewModel.coverageTitle}
                items={viewModel.coverageItems}
              />
            )}

            {viewModel.evidenceLines.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
                  {viewModel.evidenceTitle}
                </h4>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-zl-muted">
                  {viewModel.evidenceLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            )}

            {viewModel.timeline.length > 0 && (
              <ul className="space-y-1 text-xs text-zl-muted">
                {viewModel.timeline.map((item) => (
                  <li key={`${item.text}-${item.occurredAtTitle ?? "none"}`}>
                    {item.text}
                    {item.occurredAtTitle ? ` · ${item.occurredAtTitle}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </DrawerSection>
  );
}
