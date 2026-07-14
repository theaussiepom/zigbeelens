/**
 * Presentation-only Device Decision Badge for inventory surfaces.
 * Receives a ViewModel; does not map decision status codes.
 */

import type { DeviceDecisionBadgeViewModel } from "@/viewModels/devices/deviceDecisionBadgeViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

function decisionPillClassName(tone: DecisionPillTone): string {
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

export function DeviceDecisionBadge({
  decision,
}: {
  decision: DeviceDecisionBadgeViewModel;
}) {
  return (
    <span className={decisionPillClassName(decision.tone)} title={decision.headline}>
      {decision.statusLabel}
    </span>
  );
}
