/**
 * Reports preview ViewModel — maps ReportDetail decision sections to UI-ready models.
 * Reuses Device Story, investigation priority, and data coverage ViewModel builders.
 */

import type { ReportDetail, ReportDeviceStory, ReportScope } from "@zigbeelens/shared";
import type { DeviceStoryDto } from "@/types/devices";
import type { DecisionPriority, DecisionStatus } from "@/types/decisions";
import { decisionStatusLabel } from "@/viewModels/decisionCopy";
import {
  DEVICE_DECISION_SORT_ORDER,
  decisionSortRank,
} from "@/viewModels/devices/deviceRowViewModel";
import {
  buildDataCoverageWarningViewModel,
  type DataCoverageWarningViewModel,
} from "@/viewModels/overview/dataCoverageViewModel";
import {
  buildInvestigationPriorityViewModel,
  type InvestigationPriorityViewModel,
} from "@/viewModels/overview/investigationPriorityViewModel";
import {
  buildDeviceStoryViewModel,
  type DeviceStoryViewModel,
} from "@/viewModels/topology/deviceStoryViewModel";

export const REPORT_LEGACY_NOTICE =
  "This stored report uses the earlier report format. Open the Markdown or download to view the original stored snapshot.";

const SCOPE_LABELS: Record<ReportScope, string> = {
  full: "Full evidence",
  incident: "Incident",
  network: "Network",
  device: "Device",
};

export interface ReportDecisionSummaryItem {
  key: string;
  label: string;
  count: number;
}

export interface ReportDeviceStoryItem {
  key: string;
  name: string;
  networkId: string;
  ieeeAddress: string;
  story: DeviceStoryViewModel;
}

export interface ReportDecisionViewModel {
  reportVersion: number;
  scopeLabel: string;
  isLegacyFormat: boolean;
  legacyNotice: string | null;
  meshNavigationAvailable: boolean;
  decisionSummaryItems: ReportDecisionSummaryItem[];
  networksInScope: number;
  devicesInScope: number;
  incidentsInScope: number;
  investigationPriorities: InvestigationPriorityViewModel[];
  deviceStories: ReportDeviceStoryItem[];
  networkCoverage: DataCoverageWarningViewModel[];
  redactionProfile: string;
  markdown: string;
}

function isLegacyReport(report: ReportDetail): boolean {
  // Current contract is report_version 3. Stored v1/v2 remain readable as-is.
  if (report.report_version < 3) {
    return true;
  }
  const stories = report.device_stories ?? [];
  const decisionSummary = report.decision_summary;
  return stories.length === 0 && decisionSummary == null;
}

function reportNetworks(report: ReportDetail) {
  return report.domain_details?.networks ?? report.networks ?? [];
}

function reportDevices(report: ReportDetail) {
  return report.domain_details?.devices ?? report.devices ?? [];
}

function reportStoryToDeviceStoryDto(story: ReportDeviceStory): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: story.subject_id,
    status: story.status as DecisionStatus,
    priority: story.priority as DecisionPriority,
    headline_code: story.headline_code,
    reasons: story.reasons,
    evidence: story.evidence as unknown as DeviceStoryDto["evidence"],
    limitations: story.limitations,
    suggested_checks: story.suggested_checks,
    coverage: story.coverage as unknown as DeviceStoryDto["coverage"],
    related_unresolved_incident_ids: story.related_unresolved_incident_ids ?? [],
    timeline: story.timeline.map((item) => ({
      code: item.code,
      params: item.params,
      occurred_at: item.occurred_at ?? null,
    })),
  };
}

function buildDecisionSummaryItems(
  statusCounts: Record<string, number>,
): ReportDecisionSummaryItem[] {
  const items: ReportDecisionSummaryItem[] = [];
  const seen = new Set<string>();

  for (const status of DEVICE_DECISION_SORT_ORDER) {
    const count = statusCounts[status] ?? 0;
    if (count > 0) {
      items.push({
        key: status,
        label: decisionStatusLabel(status),
        count,
      });
      seen.add(status);
    }
  }

  for (const [status, count] of Object.entries(statusCounts).sort(([a], [b]) =>
    a.localeCompare(b),
  )) {
    if (!seen.has(status) && count > 0) {
      items.push({
        key: status,
        label: decisionStatusLabel(status),
        count,
      });
    }
  }

  return items;
}

function compareReportDeviceStories(
  a: ReportDeviceStory,
  b: ReportDeviceStory,
): number {
  const rankDiff = decisionSortRank(a.status) - decisionSortRank(b.status);
  if (rankDiff !== 0) {
    return rankDiff;
  }
  return a.friendly_name.localeCompare(b.friendly_name, undefined, {
    sensitivity: "base",
  });
}

function networkNamesFromReport(report: ReportDetail): Record<string, string> {
  return Object.fromEntries(
    reportNetworks(report).map((network) => [network.id, network.name]),
  );
}

export function buildReportDecisionViewModel(
  report: ReportDetail,
): ReportDecisionViewModel {
  const legacy = isLegacyReport(report);
  const names = networkNamesFromReport(report);
  const meshNavigationAvailable = report.redaction.network_names === "preserved";

  const decisionSummaryItems = legacy
    ? []
    : buildDecisionSummaryItems(report.decision_summary?.status_counts ?? {});

  const investigationPriorities = legacy
    ? []
    : (report.investigation_priorities ?? []).map((priority) =>
        buildInvestigationPriorityViewModel(priority, names[priority.network_id]),
      );

  const deviceStories = legacy
    ? []
    : [...(report.device_stories ?? [])]
        .sort(compareReportDeviceStories)
        .map((story) => ({
          key: `${story.network_id}:${story.ieee_address}`,
          name: story.friendly_name,
          networkId: story.network_id,
          ieeeAddress: story.ieee_address,
          story: buildDeviceStoryViewModel(reportStoryToDeviceStoryDto(story)),
        }));

  const networkCoverage = legacy
    ? []
    : (report.data_coverage_warnings ?? []).map((warning) =>
        buildDataCoverageWarningViewModel(warning, names[warning.network_id]),
      );

  return {
    reportVersion: report.report_version,
    scopeLabel: SCOPE_LABELS[report.scope] ?? report.scope,
    isLegacyFormat: legacy,
    legacyNotice: legacy ? REPORT_LEGACY_NOTICE : null,
    meshNavigationAvailable,
    decisionSummaryItems,
    networksInScope: reportNetworks(report).length,
    devicesInScope:
      report.raw_counts.devices_included ?? reportDevices(report).length,
    incidentsInScope:
      report.raw_counts.incidents_included ?? report.incidents.length,
    investigationPriorities,
    deviceStories,
    networkCoverage,
    redactionProfile: report.redaction.profile,
    markdown: report.markdown_summary,
  };
}
