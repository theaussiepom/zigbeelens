/**
 * Evidence summary report builder.
 *
 * Builds a deterministic, human Markdown report (plus an optional JSON
 * summary) from evidence state the graph page already holds. Read-only:
 * nothing is persisted, nothing is fetched, nothing is inferred. Sections
 * with nothing useful to say are omitted — silence is better than
 * unnecessary reassurance. All wording follows docs/ubiquitous-language.md.
 */

import type { InvestigationCard, SnapshotCompareDetail } from "@/lib/api";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  COMPARE_NO_CHANGES_COPY,
  COMPARE_NOT_ENOUGH_HISTORY_COPY,
  meshHealthBucketLabel,
  meshRoleLabel,
  REPORT_PASSIVE_HINT_NOTE,
  REPORT_ROUTE_HINT_NOTE,
  REPORT_SAFETY_NOTE,
  REPORT_TITLE,
} from "@/lib/meshGraphCopy";
import { buildDeviceStoryReportSection } from "@/viewModels/topology/deviceStoryReportSection";
import type { DeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";

export interface MeshEvidenceReportInput {
  networkId: string;
  networkName?: string | null;
  /** ISO timestamp of the latest topology snapshot, when known. */
  latestSnapshotCapturedAt?: string | null;
  /** When the report is generated; injected for deterministic output. */
  generatedAt: Date;
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  investigations: InvestigationCard[];
  /** Snapshot comparison, included only when compare is active/available. */
  compare?: SnapshotCompareDetail | null;
  /** Selected device, included only when a device is selected. */
  selectedDevice?: MeshEvidenceDevice | null;
  /**
   * Device Story ViewModel for the selected device. Phase 4A-4 report-readiness
   * hook — pass a built ViewModel when available; Phase 5 wiring will fetch and
   * map the Device Story API here. Not fetched by the report builder itself.
   */
  deviceStory?: DeviceStoryViewModel | null;
}

export interface MeshEvidenceReport {
  markdown: string;
  /** Base filename without extension, sanitised for filesystem use. */
  filenameBase: string;
  /** Structured summary for tools; unknown values are null, never zero. */
  jsonSummary: MeshEvidenceJsonSummary;
}

export interface MeshEvidenceJsonSummary {
  network_id: string;
  network_name: string | null;
  generated_at: string;
  latest_snapshot: { captured_at: string | null } | null;
  counts: {
    known_devices: number;
    observed_topology_devices: number;
    latest_snapshot_links: number;
    recent_missing_links: number;
    suggested_investigation_links: number;
    investigation_priorities: number;
  };
  snapshot_comparison: SnapshotCompareDetail | null;
  investigation_priorities: InvestigationCard[];
  selected_device: {
    ieee_address: string;
    friendly_name: string;
    role: string;
    status: string;
  } | null;
  /** Present when a Device Story ViewModel was supplied to the report builder. */
  device_story: {
    status_label: string;
    headline: string;
    reasons: string[];
    limitations: string[];
    suggested_checks: string[];
  } | null;
  limitations: string[];
}

/** Local `YYYY-MM-DD HH:mm` stamp — the timezone the UI already lives in. */
function formatStamp(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function formatIsoStamp(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return formatStamp(date);
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** Filesystem-safe slug for network names. */
export function sanitizeFilenamePart(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "network";
}

interface EvidenceCounts {
  knownDevices: number;
  observedTopologyDevices: number;
  latestSnapshotLinks: number;
  recentMissingLinks: number;
  suggestedInvestigationLinks: number;
}

function countEvidence(devices: MeshEvidenceDevice[], edges: MeshEvidenceEdge[]): EvidenceCounts {
  return {
    knownDevices: devices.filter((device) => device.in_inventory).length,
    observedTopologyDevices: devices.filter((device) => device.in_latest_snapshot).length,
    latestSnapshotLinks: edges.filter((edge) => edge.in_latest_snapshot).length,
    recentMissingLinks: edges.filter(
      (edge) =>
        edge.evidence_class === "historical_neighbor" ||
        edge.evidence_class === "historical_route",
    ).length,
    suggestedInvestigationLinks: edges.filter(
      (edge) => edge.evidence_class === "passive_derived_association",
    ).length,
  };
}

function plural(count: number, singular: string, pluralForm: string): string {
  return count === 1 ? singular : pluralForm;
}

/**
 * Whether a card's "What this does not prove" changes interpretation:
 * passive-derived and recent-missing evidence is easy to over-read, so those
 * cards carry their limitation. Latest-snapshot-only groupings do not.
 */
function cardNeedsLimitation(card: InvestigationCard): boolean {
  return card.created_from_evidence_classes.some(
    (cls) => cls.includes("passive") || cls.includes("historical"),
  );
}

function summarySection(input: MeshEvidenceReportInput, counts: EvidenceCounts): string[] {
  const label = input.networkName || input.networkId;
  const lines = [
    "## Summary",
    "",
    `ZigbeeLens reviewed the latest topology evidence for \`${label}\`.`,
  ];
  const bullets: string[] = [];
  if (counts.knownDevices > 0) {
    bullets.push(`- ${formatCount(counts.knownDevices)} known devices`);
  }
  if (counts.observedTopologyDevices > 0) {
    bullets.push(
      `- ${formatCount(counts.observedTopologyDevices)} devices observed in the latest topology snapshot`,
    );
  }
  if (counts.latestSnapshotLinks > 0) {
    bullets.push(
      `- ${formatCount(counts.latestSnapshotLinks)} latest snapshot evidence ${plural(counts.latestSnapshotLinks, "link", "links")} available`,
    );
  }
  if (counts.recentMissingLinks > 0) {
    bullets.push(
      `- ${formatCount(counts.recentMissingLinks)} recent missing ${plural(counts.recentMissingLinks, "link", "links")} in the selected history window`,
    );
  }
  if (counts.suggestedInvestigationLinks > 0) {
    bullets.push(
      `- ${formatCount(counts.suggestedInvestigationLinks)} suggested investigation ${plural(counts.suggestedInvestigationLinks, "link", "links")}`,
    );
  }
  if (input.investigations.length > 0) {
    bullets.push(
      `- ${input.investigations.length} investigation ${plural(input.investigations.length, "priority", "priorities")} worth checking`,
    );
  }
  if (bullets.length > 0) {
    lines.push("", "Useful evidence in this view:", ...bullets);
  }
  return lines;
}

function whatChangedSection(compare: SnapshotCompareDetail): string[] {
  const lines = ["## What changed", ""];
  if (!compare.has_comparison) {
    lines.push(COMPARE_NOT_ENOUGH_HISTORY_COPY);
    return lines;
  }
  if (compare.changes.length === 0) {
    lines.push(COMPARE_NO_CHANGES_COPY);
    return lines;
  }
  // The backend summary leads with the churn level and its calm qualifier.
  lines.push(compare.summary);
  for (const item of compare.summary_items) {
    lines.push(`- ${item}`);
  }
  return lines;
}

function investigationSection(investigations: InvestigationCard[]): string[] {
  const lines = ["## Where to look first"];
  for (const card of investigations) {
    lines.push("", `### ${card.priority}: ${card.title}`, "", card.summary);
    if (card.supporting_evidence.length > 0) {
      lines.push("", "Supporting evidence:");
      for (const item of card.supporting_evidence) lines.push(`- ${item}`);
    }
    if (cardNeedsLimitation(card) && card.limitations.length > 0) {
      lines.push("", "What this does not prove:", card.limitations[0]);
    }
    if (card.suggested_next_steps.length > 0) {
      lines.push("", "Suggested checks:");
      for (const item of card.suggested_next_steps) lines.push(`- ${item}`);
    }
  }
  return lines;
}

function selectedDeviceSection(
  device: MeshEvidenceDevice,
  edges: MeshEvidenceEdge[],
): string[] {
  const touching = edges.filter(
    (edge) => edge.source === device.ieee_address || edge.target === device.ieee_address,
  );
  const countOf = (...classes: string[]) =>
    touching.filter((edge) => classes.includes(edge.evidence_class)).length;
  const neighbourLinks = countOf("latest_snapshot_neighbor");
  const routeHints = countOf("latest_snapshot_route");
  const recentMissing = countOf("historical_neighbor", "historical_route");
  const lastKnown = countOf("last_known_link");
  const passiveHints = countOf("passive_derived_association");

  const lines = [
    "## Selected device",
    "",
    `Device: ${device.friendly_name}`,
    `IEEE: ${device.ieee_address}`,
    `Status: ${meshHealthBucketLabel(device.health_bucket)}`,
    `Role: ${meshRoleLabel(device.role)}`,
    "",
    "Evidence:",
    `- ${device.topology_evidence_summary}`,
  ];
  if (neighbourLinks > 0) {
    lines.push(
      `- ${neighbourLinks} latest snapshot neighbour ${plural(neighbourLinks, "link", "links")}`,
    );
  }
  if (routeHints > 0) {
    lines.push(`- ${routeHints} route ${plural(routeHints, "hint", "hints")}`);
  }
  if (recentMissing > 0) {
    lines.push(`- ${recentMissing} recent missing ${plural(recentMissing, "link", "links")}`);
  }
  if (lastKnown > 0) {
    lines.push(`- ${lastKnown} last known ${plural(lastKnown, "link", "links")}`);
  }
  if (passiveHints > 0) {
    lines.push(
      `- ${passiveHints} suggested investigation ${plural(passiveHints, "link", "links")}`,
    );
  }
  for (const stat of device.diagnostic_stats) {
    lines.push(`- ${stat.label}: ${stat.value}`);
  }
  if (device.open_issue) {
    lines.push("", `Open issue: ${device.open_issue.title}. ${device.open_issue.summary}`);
  }
  // Suggested checks come only from real backend suggestions on evidence
  // touching this device — never invented for the report.
  const checks = Array.from(
    new Set(touching.flatMap((edge) => edge.suggested_investigation)),
  );
  if (checks.length > 0) {
    lines.push("", "Suggested checks:");
    for (const item of checks) lines.push(`- ${item}`);
  }
  return lines;
}

/**
 * The short, practical notes this evidence set actually needs. The safety
 * note always applies; route/passive notes only when that evidence exists.
 */
function activeLimitations(edges: MeshEvidenceEdge[]): string[] {
  const notes = [REPORT_SAFETY_NOTE];
  if (
    edges.some(
      (edge) =>
        edge.evidence_class === "latest_snapshot_route" ||
        edge.evidence_class === "historical_route",
    )
  ) {
    notes.push(REPORT_ROUTE_HINT_NOTE);
  }
  if (edges.some((edge) => edge.evidence_class === "passive_derived_association")) {
    notes.push(REPORT_PASSIVE_HINT_NOTE);
  }
  return notes;
}

function evidenceNotesSection(edges: MeshEvidenceEdge[]): string[] {
  return ["## Evidence notes", "", activeLimitations(edges).join(" ")];
}

export function buildMeshEvidenceReport(input: MeshEvidenceReportInput): MeshEvidenceReport {
  const counts = countEvidence(input.devices, input.edges);
  const snapshotStamp = input.latestSnapshotCapturedAt
    ? formatIsoStamp(input.latestSnapshotCapturedAt)
    : null;

  const sections: string[][] = [];

  const header = [
    `# ${REPORT_TITLE}`,
    "",
    `Network: ${input.networkName ? `${input.networkName} (${input.networkId})` : input.networkId}`,
    `Generated: ${formatStamp(input.generatedAt)}`,
  ];
  if (snapshotStamp) header.push(`Latest topology snapshot: ${snapshotStamp}`);
  sections.push(header);

  sections.push(summarySection(input, counts));

  if (input.compare) {
    sections.push(whatChangedSection(input.compare));
  }
  if (input.investigations.length > 0) {
    sections.push(investigationSection(input.investigations));
  }
  if (input.selectedDevice) {
    sections.push(selectedDeviceSection(input.selectedDevice, input.edges));
  }
  if (input.deviceStory) {
    sections.push(buildDeviceStoryReportSection(input.deviceStory).lines);
  }
  sections.push(evidenceNotesSection(input.edges));

  const markdown = sections.map((section) => section.join("\n")).join("\n\n") + "\n";

  const pad = (n: number) => String(n).padStart(2, "0");
  const d = input.generatedAt;
  const filenameBase =
    `zigbeelens-${sanitizeFilenamePart(input.networkName || input.networkId)}` +
    `-evidence-summary-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `-${pad(d.getHours())}${pad(d.getMinutes())}`;

  const jsonSummary: MeshEvidenceJsonSummary = {
    network_id: input.networkId,
    network_name: input.networkName ?? null,
    generated_at: input.generatedAt.toISOString(),
    latest_snapshot: input.latestSnapshotCapturedAt
      ? { captured_at: input.latestSnapshotCapturedAt }
      : null,
    counts: {
      known_devices: counts.knownDevices,
      observed_topology_devices: counts.observedTopologyDevices,
      latest_snapshot_links: counts.latestSnapshotLinks,
      recent_missing_links: counts.recentMissingLinks,
      suggested_investigation_links: counts.suggestedInvestigationLinks,
      investigation_priorities: input.investigations.length,
    },
    snapshot_comparison: input.compare ?? null,
    investigation_priorities: input.investigations,
    selected_device: input.selectedDevice
      ? {
          ieee_address: input.selectedDevice.ieee_address,
          friendly_name: input.selectedDevice.friendly_name,
          role: meshRoleLabel(input.selectedDevice.role),
          status: meshHealthBucketLabel(input.selectedDevice.health_bucket),
        }
      : null,
    device_story: input.deviceStory
      ? {
          status_label: input.deviceStory.statusPill?.label ?? "Status unknown",
          headline: input.deviceStory.headline,
          reasons: input.deviceStory.reasons,
          limitations: input.deviceStory.limitations,
          suggested_checks: input.deviceStory.suggestedChecks,
        }
      : null,
    limitations: activeLimitations(input.edges),
  };

  return { markdown, filenameBase, jsonSummary };
}
