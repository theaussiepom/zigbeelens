/**
 * Device story ViewModel — maps Device Story API DTOs to UI-ready display models.
 * DeviceStorySection renders this; it does not decide diagnostic meaning or copy.
 */

import type { DeviceStoryDto } from "@/types/devices";
import { formatTime } from "@/lib/format";
import {
  DEVICE_STORY_CHECKS_TITLE,
  DEVICE_STORY_COVERAGE_TITLE,
  DEVICE_STORY_EVIDENCE_TITLE,
  DEVICE_STORY_HEADLINE_LEADS,
  DEVICE_STORY_LIMITATIONS_TITLE,
  DEVICE_SECTION_STORY,
  DEVICE_STORY_LOADING_COPY,
  DEVICE_STORY_UNAVAILABLE_COPY,
  DEVICE_STORY_UNKNOWN_HEADLINE_LEAD,
  DEVICE_STORY_WHY_TITLE,
} from "@/lib/meshGraphCopy";
import { buildEvidenceCoverageStripViewModel } from "@/viewModels/coverage/coverageStripViewModel";
import {
  decisionStatusLabel,
  decisionStatusTone,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

export type DeviceStoryLoadState = "loading" | "error" | "ready";

export interface DeviceStoryStatusPillViewModel {
  label: string;
  tone: DecisionPillTone;
}

export interface DeviceStoryTimelineItemViewModel {
  text: string;
  occurredAtTitle: string | null;
}

export interface DeviceStoryViewModel {
  loadState: DeviceStoryLoadState;
  sectionTitle: string;
  loadingCopy: string;
  unavailableCopy: string;
  statusPill: DeviceStoryStatusPillViewModel | null;
  headline: string;
  headlineLead: string;
  whyTitle: string;
  reasons: string[];
  limitationsTitle: string;
  limitations: string[];
  checksTitle: string;
  suggestedChecks: string[];
  coverageTitle: string;
  coverageItems: ReturnType<typeof buildEvidenceCoverageStripViewModel>["items"];
  evidenceTitle: string;
  evidenceLines: string[];
  timeline: DeviceStoryTimelineItemViewModel[];
}

function headlineLead(code: string): string {
  return DEVICE_STORY_HEADLINE_LEADS[code] ?? DEVICE_STORY_UNKNOWN_HEADLINE_LEAD;
}

function evidenceLine(
  source: string,
  id?: string | null,
  capturedAt?: string | null,
): string {
  if (source === "topology_snapshot") {
    const parts = ["Latest stored topology snapshot"];
    if (capturedAt) parts.push(`captured ${formatTime(capturedAt)}`);
    if (id) parts.push(`(${id})`);
    return parts.join(" · ");
  }
  if (id) return `Stored evidence (${id})`;
  return "Stored evidence reference";
}

export function buildDeviceStoryViewModel(story: DeviceStoryDto): DeviceStoryViewModel {
  const coverage = buildEvidenceCoverageStripViewModel(story.coverage);

  return {
    loadState: "ready",
    sectionTitle: DEVICE_SECTION_STORY,
    loadingCopy: DEVICE_STORY_LOADING_COPY,
    unavailableCopy: DEVICE_STORY_UNAVAILABLE_COPY,
    statusPill: {
      label: decisionStatusLabel(story.status),
      tone: decisionStatusTone(story.status),
    },
    headline: headlineText(story.headline_code),
    headlineLead: headlineLead(story.headline_code),
    whyTitle: DEVICE_STORY_WHY_TITLE,
    reasons: story.reasons.map((reason) =>
      reasonText(reason.code, reason.params ?? {}),
    ),
    limitationsTitle: DEVICE_STORY_LIMITATIONS_TITLE,
    limitations: story.limitations.map((item) =>
      limitationText(item.code, item.params ?? {}),
    ),
    checksTitle: DEVICE_STORY_CHECKS_TITLE,
    suggestedChecks: story.suggested_checks.map((item) =>
      suggestedCheckText(item.code, item.params ?? {}),
    ),
    coverageTitle: DEVICE_STORY_COVERAGE_TITLE,
    coverageItems: coverage.items,
    evidenceTitle: DEVICE_STORY_EVIDENCE_TITLE,
    evidenceLines: story.evidence.map((item) =>
      evidenceLine(item.source, item.id, item.captured_at),
    ),
    timeline: story.timeline.map((item) => ({
      text: reasonText(item.code, item.params ?? {}),
      occurredAtTitle: item.occurred_at ? formatTime(item.occurred_at) : null,
    })),
  };
}

export function loadingDeviceStoryViewModel(): DeviceStoryViewModel {
  return {
    loadState: "loading",
    sectionTitle: DEVICE_SECTION_STORY,
    loadingCopy: DEVICE_STORY_LOADING_COPY,
    unavailableCopy: DEVICE_STORY_UNAVAILABLE_COPY,
    statusPill: null,
    headline: "",
    headlineLead: "",
    whyTitle: DEVICE_STORY_WHY_TITLE,
    reasons: [],
    limitationsTitle: DEVICE_STORY_LIMITATIONS_TITLE,
    limitations: [],
    checksTitle: DEVICE_STORY_CHECKS_TITLE,
    suggestedChecks: [],
    coverageTitle: DEVICE_STORY_COVERAGE_TITLE,
    coverageItems: [],
    evidenceTitle: DEVICE_STORY_EVIDENCE_TITLE,
    evidenceLines: [],
    timeline: [],
  };
}

export function errorDeviceStoryViewModel(): DeviceStoryViewModel {
  return {
    ...loadingDeviceStoryViewModel(),
    loadState: "error",
  };
}
