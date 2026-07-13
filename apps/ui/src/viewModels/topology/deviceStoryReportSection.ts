/**
 * Device Story report section — maps a Device Story ViewModel to Markdown lines.
 *
 * Reports must consume the same ViewModel output as the drawer section so UI
 * and export stay aligned. Phase 5 report wiring passes a built ViewModel here;
 * this module does not fetch or reinterpret Device Story meaning.
 */

import {
  DEVICE_SECTION_STORY,
  DEVICE_STORY_COVERAGE_TITLE,
  DEVICE_STORY_EVIDENCE_TITLE,
} from "@/lib/meshGraphCopy";
import type { DeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";

export interface DeviceStoryReportSection {
  title: string;
  lines: string[];
}

function bulletBlock(title: string, items: string[]): string[] {
  if (items.length === 0) return [];
  return ["", `### ${title}`, "", ...items.map((item) => `- ${item}`)];
}

/** Build Markdown lines for one device story. Omits empty subsections. */
export function buildDeviceStoryReportSection(
  story: DeviceStoryViewModel,
): DeviceStoryReportSection {
  const lines = [
    `## ${DEVICE_SECTION_STORY}`,
    "",
    `**${story.statusPill?.label ?? "Status unknown"}** — ${story.headline}`,
    "",
    story.headlineLead,
    ...bulletBlock(story.whyTitle, story.reasons),
    ...bulletBlock(story.limitationsTitle, story.limitations),
    ...bulletBlock(story.checksTitle, story.suggestedChecks),
  ];

  if (story.coverageItems.length > 0) {
    lines.push("", `### ${DEVICE_STORY_COVERAGE_TITLE}`, "");
    for (const item of story.coverageItems) {
      lines.push(`- ${item.label}`);
    }
  }

  if (story.evidenceLines.length > 0) {
    lines.push(...bulletBlock(DEVICE_STORY_EVIDENCE_TITLE, story.evidenceLines));
  }

  if (story.timeline.length > 0) {
    lines.push("", "### Timeline", "");
    for (const item of story.timeline) {
      const suffix = item.occurredAtTitle ? ` (${item.occurredAtTitle})` : "";
      lines.push(`- ${item.text}${suffix}`);
    }
  }

  return { title: DEVICE_SECTION_STORY, lines };
}
