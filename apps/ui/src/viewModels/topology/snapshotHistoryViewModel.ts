/**
 * Snapshot history ViewModel — maps device snapshot-history DTOs to UI-ready
 * display models. Components render this; they do not decide comparison status
 * or diagnostic copy.
 */

import type {
  AvailabilityCoverageStatus,
  DeviceSnapshotComparison,
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
} from "@/types/devices";
import type { EvidenceFactDto } from "@/types/decisions";
import { formatTime, relativeTime } from "@/lib/format";
import {
  AVAILABILITY_PILL_BUILDING,
  AVAILABILITY_PILL_BUILDING_HELPER,
  AVAILABILITY_PILL_OFF,
  AVAILABILITY_PILL_OFF_HELPER,
  AVAILABILITY_PILL_UNKNOWN,
  AVAILABILITY_PILL_UNKNOWN_HELPER,
  SNAPSHOT_COMPARE_MEANING,
  SNAPSHOT_COMPARE_STATUS_LEADS,
  SNAPSHOT_HISTORY_CHECKS_TITLE,
  SNAPSHOT_HISTORY_COMPARE_WITH_LABEL,
  SNAPSHOT_HISTORY_EMPTY_COPY,
  SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE,
  SNAPSHOT_HISTORY_LATEST_LABEL,
  SNAPSHOT_HISTORY_MEANING_TITLE,
  SNAPSHOT_HISTORY_ROUTE_HINT_NOTE,
  SNAPSHOT_HISTORY_SECTION_TITLE,
  SNAPSHOT_HISTORY_SELECTED_ONLY_NOTE,
  SNAPSHOT_HISTORY_SOURCE_NOTE,
  SNAPSHOT_HISTORY_UNAVAILABLE_COPY,
  SNAPSHOT_HISTORY_WHY_TITLE,
} from "@/lib/meshGraphCopy";
import {
  decisionStatusCompactLabel,
  decisionStatusLabel,
  reasonText,
} from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

export type SnapshotHistoryLoadState = "loading" | "error" | "ready";

export interface AvailabilityPillViewModel {
  label: string;
  helper: string;
  tone: DecisionPillTone;
}

export interface SnapshotHistoryRowViewModel {
  snapshotId: string;
  capturedAtTitle: string;
  relativeLabel: string;
  countsText: string;
  statusLabel: string | null;
  availabilityStateText: string | null;
  coveragePill: AvailabilityPillViewModel | null;
  selected: boolean;
}

export interface SnapshotEvidenceDetailsViewModel {
  linkLines: string[];
  routeLines: string[];
  showSelectedOnlyNote: boolean;
  showRouteNote: boolean;
  sourceNote: string;
  selectedOnlyNote: string;
  routeHintNote: string;
}

export interface SnapshotComparisonViewModel {
  statusLabel: string;
  statusLead: string;
  whyTitle: string;
  reasons: string[];
  meaningTitle: string;
  meaningText: string;
  checksTitle: string;
  suggestedChecks: string[];
  evidenceDetailsTitle: string;
  evidenceDetails: SnapshotEvidenceDetailsViewModel;
}

export interface SnapshotHistoryViewModel {
  loadState: SnapshotHistoryLoadState;
  sectionTitle: string;
  trackingOffBanner: AvailabilityPillViewModel | null;
  selectedCoverageBanner: AvailabilityPillViewModel | null;
  latestLabel: string;
  latestSummary: string | null;
  compareWithLabel: string;
  emptyCopy: string;
  unavailableCopy: string;
  rows: SnapshotHistoryRowViewModel[];
  comparison: SnapshotComparisonViewModel | null;
  defaultSelectedSnapshotId: string | null;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function rowCountsCopy(row: DeviceSnapshotHistoryRow): string {
  const links = `${plural(row.links_for_device_count, "link")} shown`;
  const routes =
    row.route_hints_for_device_count > 0
      ? plural(row.route_hints_for_device_count, "route hint")
      : "no route hints";
  return `${links} · ${routes}`;
}

function availabilityStateCopy(row: DeviceSnapshotHistoryRow): string | null {
  if (row.availability_state_near_snapshot === "online") return "Online";
  if (row.availability_state_near_snapshot === "offline") return "Offline";
  return null;
}

function availabilityPillForStatus(
  status: AvailabilityCoverageStatus,
): AvailabilityPillViewModel | null {
  if (status === "off") {
    return {
      label: AVAILABILITY_PILL_OFF,
      helper: AVAILABILITY_PILL_OFF_HELPER,
      tone: "coverage",
    };
  }
  if (status === "building") {
    return {
      label: AVAILABILITY_PILL_BUILDING,
      helper: AVAILABILITY_PILL_BUILDING_HELPER,
      tone: "watch",
    };
  }
  if (status === "unknown") {
    return {
      label: AVAILABILITY_PILL_UNKNOWN,
      helper: AVAILABILITY_PILL_UNKNOWN_HELPER,
      tone: "muted",
    };
  }
  return null;
}

function evidenceDetailLines(comparison: DeviceSnapshotComparison): {
  links: string[];
  routes: string[];
} {
  const link = comparison.link_counts;
  const links = [
    `${plural(link.latest_count, "link")} shown in latest snapshot`,
    `${plural(link.selected_count, "link")} shown in selected snapshot`,
  ];
  if (link.latest_only_count > 0) {
    links.push(`${plural(link.latest_only_count, "link")} only in latest snapshot`);
  }
  if (link.selected_only_count > 0) {
    links.push(`${plural(link.selected_only_count, "link")} only in selected snapshot`);
  }
  if (link.changed_count > 0) links.push(`${plural(link.changed_count, "link")} changed`);

  const route = comparison.route_hint_counts;
  const routes = [
    `${plural(route.latest_count, "route hint")} in latest snapshot`,
    `${plural(route.selected_count, "route hint")} in selected snapshot`,
  ];
  const routeDifferences =
    route.latest_only_count + route.selected_only_count + route.changed_count;
  if (routeDifferences === 0) {
    routes.push("No route-hint difference");
  } else {
    if (route.latest_only_count > 0) {
      routes.push(`${plural(route.latest_only_count, "route hint")} only in latest snapshot`);
    }
    if (route.selected_only_count > 0) {
      routes.push(
        `${plural(route.selected_only_count, "route hint")} only in selected snapshot`,
      );
    }
    if (route.changed_count > 0) {
      routes.push(`${plural(route.changed_count, "route hint")} changed`);
    }
  }
  return { links, routes };
}

const TOPOLOGY_FACT_TO_REASON: Record<string, string> = {
  device_no_latest_links: "latest_snapshot_no_links",
  device_has_selected_snapshot_links: "selected_snapshot_had_links",
  availability_coverage_affects_snapshot_comparison: "availability_tracking_off",
};

function reasonParamsFromTopologyFact(fact: EvidenceFactDto): Record<string, unknown> {
  const params = fact.params ?? {};
  if (fact.code === "device_has_selected_snapshot_links") {
    return { selected_snapshot_link_count: params.link_count };
  }
  if (fact.code === "availability_coverage_affects_snapshot_comparison") {
    const coverage = params.availability_coverage_status;
    if (coverage === "building") return {};
    if (coverage === "unknown") return {};
    return {};
  }
  return params;
}

function reasonCodeFromTopologyFact(fact: EvidenceFactDto): string {
  if (fact.code === "availability_coverage_affects_snapshot_comparison") {
    const coverage = fact.params?.availability_coverage_status;
    if (coverage === "building") return "availability_history_building";
    if (coverage === "unknown") return "availability_status_unknown";
    return "availability_tracking_off";
  }
  return TOPOLOGY_FACT_TO_REASON[fact.code] ?? fact.code;
}

function topologyFactReasonText(fact: EvidenceFactDto): string {
  return reasonText(reasonCodeFromTopologyFact(fact), reasonParamsFromTopologyFact(fact));
}

function comparisonReasons(
  comparison: DeviceSnapshotComparison,
  comparisonFacts: EvidenceFactDto[],
): string[] {
  const fromFacts = comparisonFacts
    .map(topologyFactReasonText)
    .filter((text) => text !== "Details unavailable.");
  if (fromFacts.length > 0) return fromFacts;
  return comparison.reasons;
}

function buildComparisonViewModel(
  comparison: DeviceSnapshotComparison,
  comparisonFacts: EvidenceFactDto[],
): SnapshotComparisonViewModel {
  const details = evidenceDetailLines(comparison);
  const status = comparison.status;
  return {
    statusLabel: decisionStatusLabel(status),
    statusLead: SNAPSHOT_COMPARE_STATUS_LEADS[status],
    whyTitle: SNAPSHOT_HISTORY_WHY_TITLE,
    reasons: comparisonReasons(comparison, comparisonFacts),
    meaningTitle: SNAPSHOT_HISTORY_MEANING_TITLE,
    meaningText: SNAPSHOT_COMPARE_MEANING[status],
    checksTitle: SNAPSHOT_HISTORY_CHECKS_TITLE,
    suggestedChecks: comparison.suggested_checks,
    evidenceDetailsTitle: SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE,
    evidenceDetails: {
      linkLines: details.links,
      routeLines: details.routes,
      showSelectedOnlyNote: comparison.link_counts.selected_only_count > 0,
      showRouteNote:
        comparison.route_hint_counts.latest_only_count +
          comparison.route_hint_counts.selected_only_count +
          comparison.route_hint_counts.changed_count >
        0,
      sourceNote: SNAPSHOT_HISTORY_SOURCE_NOTE,
      selectedOnlyNote: SNAPSHOT_HISTORY_SELECTED_ONLY_NOTE,
      routeHintNote: SNAPSHOT_HISTORY_ROUTE_HINT_NOTE,
    },
  };
}

function buildLatestSummary(row: DeviceSnapshotHistoryRow): string {
  const state = availabilityStateCopy(row);
  return `${rowCountsCopy(row)}${state ? ` · ${state}` : ""}`;
}

function buildRowViewModel(
  row: DeviceSnapshotHistoryRow,
  selectedSnapshotId: string | null,
): SnapshotHistoryRowViewModel {
  const statusLabel = row.comparison_to_latest
    ? decisionStatusCompactLabel(row.comparison_to_latest.status)
    : null;
  const coveragePill =
    row.availability_coverage_status !== "tracked"
      ? availabilityPillForStatus(row.availability_coverage_status)
      : null;
  return {
    snapshotId: row.snapshot_id,
    capturedAtTitle: formatTime(row.captured_at ?? undefined),
    relativeLabel: relativeTime(row.captured_at ?? undefined),
    countsText: rowCountsCopy(row),
    statusLabel,
    availabilityStateText: availabilityStateCopy(row),
    coveragePill,
    selected: row.snapshot_id === selectedSnapshotId,
  };
}

export function defaultSelectedSnapshotId(
  detail: DeviceSnapshotHistoryDetail,
): string | null {
  return detail.snapshots[0]?.snapshot_id ?? null;
}

export function buildSnapshotHistoryViewModel(
  detail: DeviceSnapshotHistoryDetail,
  selectedSnapshotId: string | null,
): SnapshotHistoryViewModel {
  const selectedRow =
    detail.snapshots.find((row) => row.snapshot_id === selectedSnapshotId) ?? null;
  const comparisonFacts =
    selectedSnapshotId != null
      ? detail.topology_facts.comparison_facts_by_snapshot_id[selectedSnapshotId] ?? []
      : [];

  let selectedCoverageBanner: AvailabilityPillViewModel | null = null;
  if (
    detail.availability_tracking.enabled &&
    selectedRow &&
    (selectedRow.availability_coverage_status === "building" ||
      selectedRow.availability_coverage_status === "unknown")
  ) {
    selectedCoverageBanner = availabilityPillForStatus(
      selectedRow.availability_coverage_status,
    );
  }

  return {
    loadState: "ready",
    sectionTitle: SNAPSHOT_HISTORY_SECTION_TITLE,
    trackingOffBanner: detail.availability_tracking.enabled
      ? null
      : availabilityPillForStatus("off"),
    selectedCoverageBanner,
    latestLabel: SNAPSHOT_HISTORY_LATEST_LABEL,
    latestSummary: detail.latest_snapshot
      ? buildLatestSummary(detail.latest_snapshot)
      : null,
    compareWithLabel: SNAPSHOT_HISTORY_COMPARE_WITH_LABEL,
    emptyCopy: SNAPSHOT_HISTORY_EMPTY_COPY,
    unavailableCopy: SNAPSHOT_HISTORY_UNAVAILABLE_COPY,
    rows: detail.snapshots.map((row) => buildRowViewModel(row, selectedSnapshotId)),
    comparison:
      selectedRow?.comparison_to_latest != null
        ? buildComparisonViewModel(selectedRow.comparison_to_latest, comparisonFacts)
        : null,
    defaultSelectedSnapshotId: defaultSelectedSnapshotId(detail),
  };
}

export function loadingSnapshotHistoryViewModel(): SnapshotHistoryViewModel {
  return {
    loadState: "loading",
    sectionTitle: SNAPSHOT_HISTORY_SECTION_TITLE,
    trackingOffBanner: null,
    selectedCoverageBanner: null,
    latestLabel: SNAPSHOT_HISTORY_LATEST_LABEL,
    latestSummary: null,
    compareWithLabel: SNAPSHOT_HISTORY_COMPARE_WITH_LABEL,
    emptyCopy: SNAPSHOT_HISTORY_EMPTY_COPY,
    unavailableCopy: SNAPSHOT_HISTORY_UNAVAILABLE_COPY,
    rows: [],
    comparison: null,
    defaultSelectedSnapshotId: null,
  };
}

export function errorSnapshotHistoryViewModel(): SnapshotHistoryViewModel {
  return {
    ...loadingSnapshotHistoryViewModel(),
    loadState: "error",
  };
}
