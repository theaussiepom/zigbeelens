/**
 * Overview ViewModel for model patterns (Phase 4G-3).
 */

import type { ModelPatternSummary } from "@zigbeelens/shared";
import { formatTime } from "@/lib/format";

export const MODEL_PATTERN_TITLE = "Review devices with the same model";

export const MODEL_PATTERN_LIMITATION =
  "This is an observed pattern in stored availability history. It does not prove the model is defective or that the manufacturer caused the offline events.";

const MODEL_PATTERN_CHECKS = [
  "Compare affected devices for common firmware or version information where stored.",
  "Compare power and placement for affected devices.",
  "Review availability timing for the affected devices.",
  "Check whether the devices were installed or changed around the same period.",
  "Review the affected devices in Mesh.",
] as const;

export interface ModelPatternViewModel {
  id: string;
  networkId: string;
  networkLabel: string;
  title: string;
  summary: string;
  identityLabel: string;
  timingLabel: string;
  limitation: string;
  suggestedChecks: string[];
  meshHref: string;
  meshLinkLabel: string;
}

function modelPatternSummary(
  affectedCount: number,
  groupSize: number,
  lookbackDays: number,
): string {
  const dayWord = lookbackDays === 1 ? "day" : "days";
  return `${affectedCount} of ${groupSize} devices with this model have gone offline in the last ${lookbackDays} ${dayWord}.`;
}

function identityLabel(manufacturer: string | null | undefined, model: string): string {
  const modelValue = model.trim();
  const manufacturerValue = manufacturer?.trim();
  if (manufacturerValue) {
    return `${manufacturerValue} · ${modelValue}`;
  }
  return modelValue;
}

function timingLabel(latestSupportingEvidenceAt: string | null | undefined): string {
  const formatted = latestSupportingEvidenceAt
    ? formatTime(latestSupportingEvidenceAt)
    : null;
  if (formatted) {
    return `Most recent related offline transition: ${formatted}`;
  }
  return "Recent offline timing unavailable";
}

export function buildModelPatternViewModel(
  pattern: ModelPatternSummary,
  networkName?: string | null,
): ModelPatternViewModel {
  const networkLabel = networkName?.trim() || pattern.network_id;

  return {
    id: pattern.pattern_id,
    networkId: pattern.network_id,
    networkLabel,
    title: MODEL_PATTERN_TITLE,
    summary: modelPatternSummary(
      pattern.affected_count,
      pattern.group_size,
      pattern.lookback_days,
    ),
    identityLabel: identityLabel(pattern.manufacturer, pattern.model),
    timingLabel: timingLabel(pattern.latest_supporting_evidence_at),
    limitation: MODEL_PATTERN_LIMITATION,
    suggestedChecks: [...MODEL_PATTERN_CHECKS],
    meshHref: `/topology/${pattern.network_id}`,
    meshLinkLabel: "Review Mesh evidence →",
  };
}
