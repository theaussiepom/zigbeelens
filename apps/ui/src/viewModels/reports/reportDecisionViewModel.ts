/**
 * Reports preview ViewModel — maps ReportDetailV3 decision sections to UI-ready models.
 * Reuses Device Story, investigation priority, and data coverage ViewModel builders.
 */

import type {
  ReportDetailV3,
  ReportDeviceStory,
  ReportScope,
} from "@zigbeelens/shared";
import type { DeviceStoryDto } from "@/types/devices";
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

function reportNetworks(report: ReportDetailV3) {
  return report.domain_details.networks;
}

function reportDevices(report: ReportDetailV3) {
  return report.domain_details.devices;
}

function reportStoryToDeviceStoryDto(story: ReportDeviceStory): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: story.subject_id,
    status: story.status,
    priority: story.priority,
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
  statusCounts: Partial<Record<string, number>>,
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
    const value = count ?? 0;
    if (!seen.has(status) && value > 0) {
      items.push({
        key: status,
        label: decisionStatusLabel(status),
        count: value,
      });
    }
  }

  return items;
}

function compareReportDeviceStories(a: ReportDeviceStory, b: ReportDeviceStory): number {
  const rank = decisionSortRank(a.status) - decisionSortRank(b.status);
  if (rank !== 0) return rank;
  return a.friendly_name.localeCompare(b.friendly_name, undefined, {
    sensitivity: "base",
  });
}

function networkNamesFromReport(report: ReportDetailV3): Record<string, string> {
  return Object.fromEntries(
    reportNetworks(report).map((network) => [network.id, network.name]),
  );
}

export function buildReportDecisionViewModel(report: ReportDetailV3): ReportDecisionViewModel {
  const names = networkNamesFromReport(report);
  const meshNavigationAvailable = report.redaction.network_names === "preserved";

  const decisionSummaryItems = buildDecisionSummaryItems(report.decision_summary.status_counts);

  const investigationPriorities = report.investigation_priorities.map((priority) =>
    buildInvestigationPriorityViewModel(priority, names[priority.network_id]),
  );

  const deviceStories = [...report.device_stories]
    .sort(compareReportDeviceStories)
    .map((story) => ({
      key: `${story.network_id}:${story.ieee_address}`,
      name: story.friendly_name,
      networkId: story.network_id,
      ieeeAddress: story.ieee_address,
      story: buildDeviceStoryViewModel(reportStoryToDeviceStoryDto(story)),
    }));

  const networkCoverage = report.data_coverage_warnings.map((warning) =>
    buildDataCoverageWarningViewModel(warning, names[warning.network_id]),
  );

  return {
    reportVersion: report.report_version,
    scopeLabel: SCOPE_LABELS[report.scope] ?? report.scope,
    meshNavigationAvailable,
    decisionSummaryItems,
    networksInScope: reportNetworks(report).length,
    devicesInScope: report.raw_counts.devices_included ?? reportDevices(report).length,
    incidentsInScope: report.raw_counts.incidents_included ?? report.incidents.length,
    investigationPriorities,
    deviceStories,
    networkCoverage,
    redactionProfile: report.redaction.profile,
    markdown: report.markdown_summary,
  };
}
