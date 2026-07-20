/**
 * Overview ViewModel for data coverage warnings (Phase 5A-3).
 */

import type { DataCoverageWarningSummary } from "@zigbeelens/shared";
import { coverageLabel, coverageTone } from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

export const DATA_COVERAGE_SECTION_TITLE = "Data coverage";

const UNKNOWN_TITLE = "Coverage status unknown";
const UNKNOWN_SUMMARY =
  "ZigbeeLens could not map this coverage warning to a known evidence limitation.";
const UNKNOWN_CHECK = "Review Mesh evidence coverage before relying on related conclusions.";

export interface DataCoverageWarningViewModel {
  id: string;
  title: string;
  summary: string;
  check: string;
  tone: DecisionPillTone;
  networkLabel: string;
  meshHref: string;
  meshLinkLabel: string;
}

function overviewSummary(labelCode: string, networkLabel: string): string | null {
  switch (labelCode) {
    case "availability_tracking_off":
      return `Stored availability history is not being collected for ${networkLabel}. Offline-pattern and shared-event interpretation will be limited.`;
    case "availability_history_building":
      return `Availability tracking is enabled for ${networkLabel}, but the stored history is still limited.`;
    case "availability_status_unknown":
      return `Current availability cannot be interpreted confidently for part of ${networkLabel}.`;
    case "snapshot_stale":
      return `The latest stored topology snapshot for ${networkLabel} is old enough to limit current Mesh interpretation.`;
    case "route_hints_unavailable":
      return `Route-hint evidence is not available from the latest topology snapshot for ${networkLabel}. This limits mesh path hints only — it does not prove routes are absent.`;
    default:
      return null;
  }
}

function overviewCheck(labelCode: string): string | null {
  switch (labelCode) {
    case "availability_tracking_off":
      return "Review Zigbee2MQTT availability configuration before relying on availability history.";
    case "availability_history_building":
      return "Allow more observations to accumulate before treating missing patterns as reassuring.";
    case "availability_status_unknown":
      return "Review availability configuration and recent device reporting.";
    case "snapshot_stale":
      return "Review topology capture status and capture a new snapshot when appropriate.";
    case "route_hints_unavailable":
      return "Review Mesh using neighbour and historical evidence without treating missing route hints as a failure.";
    default:
      return null;
  }
}

export function buildDataCoverageWarningViewModel(
  warning: DataCoverageWarningSummary,
  networkName?: string | null,
): DataCoverageWarningViewModel {
  const networkLabel = networkName?.trim() || "Network";
  const labelCode = warning.label_code;
  const summary = overviewSummary(labelCode, networkLabel);
  const check = overviewCheck(labelCode);

  if (summary == null || check == null) {
    return {
      id: warning.id,
      title: UNKNOWN_TITLE,
      summary: UNKNOWN_SUMMARY,
      check: UNKNOWN_CHECK,
      tone: "muted",
      networkLabel,
      meshHref: `/investigate/${warning.network_id}`,
      meshLinkLabel: "Review Mesh evidence →",
    };
  }

  return {
    id: warning.id,
    title: coverageLabel(labelCode, warning.params ?? {}),
    summary,
    check,
    tone: coverageTone(labelCode),
    networkLabel,
    meshHref: `/investigate/${warning.network_id}`,
    meshLinkLabel: "Review Mesh evidence →",
  };
}
