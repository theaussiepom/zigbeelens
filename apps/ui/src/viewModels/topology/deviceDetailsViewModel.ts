/**
 * Device details ViewModel — maps mesh evidence device DTOs to UI-ready
 * section models. NodeDrawer renders this; it does not decide diagnostic
 * meaning or section ordering.
 */

import type { DataCoverageDto } from "@/types/decisions";
import type { MeshEvidenceDevice } from "@/lib/meshEvidence";
import {
  meshHealthBucketLabel,
  meshNodeFlagLabel,
  meshRoleLabel,
} from "@/lib/meshEvidence";
import {
  buildEvidenceCoverageStripViewModel,
  DEVICE_DRAWER_COVERAGE_LABEL_CODES,
} from "@/viewModels/coverage/coverageStripViewModel";
import {
  DEVICE_DETAILS_PANEL_LABEL,
  DEVICE_SECTION_DATA_COVERAGE,
  DEVICE_SECTION_OPEN_ISSUE,
  DEVICE_SECTION_PASSIVE_HINTS,
  DEVICE_SECTION_RECENT_MISSING,
  DEVICE_SECTION_STATS,
  DEVICE_SECTION_STATUS,
  DEVICE_SECTION_SUMMARY,
  DEVICE_SECTION_TOPOLOGY,
} from "@/lib/meshGraphCopy";

export type DeviceDetailsSectionId =
  | "summary"
  | "currentStatus"
  | "deviceStory"
  | "diagnosticStats"
  | "topologyEvidence"
  | "recentMissing"
  | "snapshotHistory"
  | "dataCoverage"
  | "passiveHints"
  | "openIssue";

export interface DeviceDetailsHeaderViewModel {
  friendlyName: string;
  ieeeAddress: string;
  flagLabels: string[];
}

export interface DeviceDetailsFactViewModel {
  label: string;
  value: string;
  detail?: string;
}

export interface DeviceDetailsSummarySectionViewModel {
  id: "summary";
  title: string;
  facts: DeviceDetailsFactViewModel[];
}

export interface DeviceDetailsStatusSectionViewModel {
  id: "currentStatus";
  title: string;
  facts: DeviceDetailsFactViewModel[];
  passiveObservationSummary: string | null;
}

export interface DeviceDetailsStatsSectionViewModel {
  id: "diagnosticStats";
  title: string;
  stats: DeviceDetailsFactViewModel[];
}

export interface DeviceDetailsTextSectionViewModel {
  id: "topologyEvidence" | "recentMissing" | "passiveHints";
  title: string;
  body: string;
}

export interface DeviceDetailsOpenIssueSectionViewModel {
  id: "openIssue";
  title: string;
  issueTitle: string;
  issueSummary: string;
}

export interface DeviceDetailsSnapshotHistorySectionViewModel {
  id: "snapshotHistory";
  networkId: string;
  deviceIeee: string;
}

export interface DeviceDetailsDeviceStorySectionViewModel {
  id: "deviceStory";
  networkId: string;
  deviceIeee: string;
}

export interface DeviceDetailsDataCoverageSectionViewModel {
  id: "dataCoverage";
  title: string;
  items: ReturnType<typeof buildEvidenceCoverageStripViewModel>["items"];
}

export type DeviceDetailsSectionViewModel =
  | DeviceDetailsSummarySectionViewModel
  | DeviceDetailsStatusSectionViewModel
  | DeviceDetailsStatsSectionViewModel
  | DeviceDetailsTextSectionViewModel
  | DeviceDetailsOpenIssueSectionViewModel
  | DeviceDetailsDeviceStorySectionViewModel
  | DeviceDetailsSnapshotHistorySectionViewModel
  | DeviceDetailsDataCoverageSectionViewModel;

export interface DeviceDetailsViewModel {
  panelLabel: string;
  header: DeviceDetailsHeaderViewModel;
  sections: DeviceDetailsSectionViewModel[];
}

function availabilityLabel(device: MeshEvidenceDevice): string {
  switch (device.availability) {
    case "online":
      return "Online";
    case "offline":
      return "Offline";
    default:
      return "No availability data";
  }
}

function powerLabel(device: MeshEvidenceDevice): string {
  if (device.power === "battery") return "Battery";
  if (device.power === "mains") return "Mains";
  return "Unknown power";
}

function buildSummarySection(device: MeshEvidenceDevice): DeviceDetailsSummarySectionViewModel {
  return {
    id: "summary",
    title: DEVICE_SECTION_SUMMARY,
    facts: [
      { label: "Network", value: device.network_id },
      { label: "Role", value: meshRoleLabel(device.role) },
      { label: "Power", value: powerLabel(device) },
      { label: "Inventory status", value: device.inventory_status },
    ],
  };
}

function buildStatusSection(device: MeshEvidenceDevice): DeviceDetailsStatusSectionViewModel {
  return {
    id: "currentStatus",
    title: DEVICE_SECTION_STATUS,
    facts: [
      {
        label: "ZigbeeLens status",
        value: meshHealthBucketLabel(device.health_bucket),
      },
      { label: "Availability", value: availabilityLabel(device) },
    ],
    passiveObservationSummary: device.passive_observation_summary || null,
  };
}

function buildStatsSection(device: MeshEvidenceDevice): DeviceDetailsStatsSectionViewModel | null {
  if (device.diagnostic_stats.length === 0) return null;
  return {
    id: "diagnosticStats",
    title: DEVICE_SECTION_STATS,
    stats: device.diagnostic_stats.map((stat) => ({
      label: stat.label,
      value: stat.value,
      detail: stat.detail,
    })),
  };
}

function buildTopologySection(device: MeshEvidenceDevice): DeviceDetailsTextSectionViewModel {
  return {
    id: "topologyEvidence",
    title: DEVICE_SECTION_TOPOLOGY,
    body: device.topology_evidence_summary,
  };
}

function buildRecentMissingSection(
  device: MeshEvidenceDevice,
): DeviceDetailsTextSectionViewModel | null {
  if (device.historical_topology_summary == null) return null;
  return {
    id: "recentMissing",
    title: DEVICE_SECTION_RECENT_MISSING,
    body: device.historical_topology_summary,
  };
}

function buildPassiveHintsSection(
  device: MeshEvidenceDevice,
): DeviceDetailsTextSectionViewModel | null {
  if (device.passive_hint_summary == null) return null;
  return {
    id: "passiveHints",
    title: DEVICE_SECTION_PASSIVE_HINTS,
    body: device.passive_hint_summary,
  };
}

function buildOpenIssueSection(
  device: MeshEvidenceDevice,
): DeviceDetailsOpenIssueSectionViewModel | null {
  if (!device.open_issue) return null;
  return {
    id: "openIssue",
    title: DEVICE_SECTION_OPEN_ISSUE,
    issueTitle: device.open_issue.title,
    issueSummary: device.open_issue.summary,
  };
}

function buildDeviceStorySection(
  device: MeshEvidenceDevice,
): DeviceDetailsDeviceStorySectionViewModel {
  return {
    id: "deviceStory",
    networkId: device.network_id,
    deviceIeee: device.ieee_address,
  };
}

function buildSnapshotHistorySection(
  device: MeshEvidenceDevice,
): DeviceDetailsSnapshotHistorySectionViewModel {
  return {
    id: "snapshotHistory",
    networkId: device.network_id,
    deviceIeee: device.ieee_address,
  };
}

function buildDataCoverageSection(
  networkCoverage: DataCoverageDto[],
): DeviceDetailsDataCoverageSectionViewModel | null {
  const strip = buildEvidenceCoverageStripViewModel(networkCoverage, {
    filterLabelCodes: DEVICE_DRAWER_COVERAGE_LABEL_CODES,
  });
  if (strip.items.length === 0) return null;
  return {
    id: "dataCoverage",
    title: DEVICE_SECTION_DATA_COVERAGE,
    items: strip.items,
  };
}

export function buildDeviceDetailsViewModel(
  device: MeshEvidenceDevice,
  networkCoverage: DataCoverageDto[] = [],
): DeviceDetailsViewModel {
  const sections: DeviceDetailsSectionViewModel[] = [
    buildSummarySection(device),
    buildDeviceStorySection(device),
    buildStatusSection(device),
  ];

  const stats = buildStatsSection(device);
  if (stats) sections.push(stats);

  sections.push(buildTopologySection(device));

  const recentMissing = buildRecentMissingSection(device);
  if (recentMissing) sections.push(recentMissing);

  sections.push(buildSnapshotHistorySection(device));

  const dataCoverage = buildDataCoverageSection(networkCoverage);
  if (dataCoverage) sections.push(dataCoverage);

  const passiveHints = buildPassiveHintsSection(device);
  if (passiveHints) sections.push(passiveHints);

  const openIssue = buildOpenIssueSection(device);
  if (openIssue) sections.push(openIssue);

  return {
    panelLabel: DEVICE_DETAILS_PANEL_LABEL,
    header: {
      friendlyName: device.friendly_name,
      ieeeAddress: device.ieee_address,
      flagLabels: device.flags.map((flag) => meshNodeFlagLabel(flag)),
    },
    sections,
  };
}
