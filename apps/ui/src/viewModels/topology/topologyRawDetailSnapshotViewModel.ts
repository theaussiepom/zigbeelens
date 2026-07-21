import type { Severity } from "@zigbeelens/shared";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import {
  resolveTopologyDisplayCounts,
  topologyLayoutAvailable,
  type TopologyDisplayCounts,
} from "@/lib/topologyStats";
import type {
  TopologyLinkRow,
  TopologyNodeRow,
  TopologySnapshotSummary,
} from "@/types/topology";

export type TopologyRawDetailSnapshotKind =
  | "no_snapshot"
  | "complete"
  | "complete_limited"
  | "pending"
  | "error"
  | "unknown";

export interface TopologyRawDetailSnapshotViewModel {
  kind: TopologyRawDetailSnapshotKind;
  label: string;
  severity: Severity;
  /** Body copy for pending / error / unknown states. */
  statusCopy: string | null;
  storedError: string | null;
  showTopologyCounts: boolean;
  showLimitedLayoutCopy: boolean;
  showRawContents: boolean;
  showPointInTimeLimitation: boolean;
  counts: TopologyDisplayCounts;
}

export const RAW_DETAIL_PENDING_COPY =
  "This capture is still pending. No completed raw snapshot contents are available yet.";

export const RAW_DETAIL_ERROR_GENERIC_COPY = "This capture did not complete.";

export const RAW_DETAIL_UNKNOWN_COPY =
  "The latest snapshot status is unknown. Treat it as incomplete support evidence.";

/**
 * Presentation boundary for `/topology/:networkId` raw snapshot detail.
 * Components render this ViewModel; they do not invent status ranking.
 */
export function buildTopologyRawDetailSnapshotViewModel(
  snapshot: TopologySnapshotSummary | null | undefined,
  nodes: TopologyNodeRow[],
  links: TopologyLinkRow[],
): TopologyRawDetailSnapshotViewModel {
  const counts = resolveTopologyDisplayCounts(snapshot, nodes, links);

  if (!snapshot) {
    return {
      kind: "no_snapshot",
      label: "diagnostics limited",
      severity: "watch",
      statusCopy: null,
      storedError: null,
      showTopologyCounts: false,
      showLimitedLayoutCopy: false,
      showRawContents: false,
      showPointInTimeLimitation: false,
      counts,
    };
  }

  const status = snapshot.status;
  const layoutAvailable = topologyLayoutAvailable(nodes, links);
  const storedError =
    typeof snapshot.error === "string" && snapshot.error.trim() ? snapshot.error : null;

  if (status === "complete") {
    if (!layoutAvailable) {
      return {
        kind: "complete_limited",
        label: "Complete · layout limited",
        severity: "watch",
        statusCopy: null,
        storedError,
        showTopologyCounts: true,
        showLimitedLayoutCopy: true,
        showRawContents: false,
        showPointInTimeLimitation: true,
        counts,
      };
    }
    return {
      kind: "complete",
      label: topologyStatusLabel("complete"),
      severity: "healthy",
      statusCopy: null,
      storedError,
      showTopologyCounts: true,
      showLimitedLayoutCopy: false,
      showRawContents: true,
      showPointInTimeLimitation: true,
      counts,
    };
  }

  if (status === "pending") {
    return {
      kind: "pending",
      label: topologyStatusLabel("pending"),
      severity: "watch",
      statusCopy: RAW_DETAIL_PENDING_COPY,
      storedError,
      showTopologyCounts: false,
      showLimitedLayoutCopy: false,
      showRawContents: false,
      showPointInTimeLimitation: false,
      counts,
    };
  }

  if (status === "error") {
    return {
      kind: "error",
      label: topologyStatusLabel("error"),
      severity: "critical",
      statusCopy: storedError ?? RAW_DETAIL_ERROR_GENERIC_COPY,
      storedError,
      showTopologyCounts: false,
      showLimitedLayoutCopy: false,
      showRawContents: false,
      showPointInTimeLimitation: false,
      counts,
    };
  }

  return {
    kind: "unknown",
    label: "Status unknown",
    severity: "watch",
    statusCopy: RAW_DETAIL_UNKNOWN_COPY,
    storedError,
    showTopologyCounts: false,
    showLimitedLayoutCopy: false,
    showRawContents: false,
    showPointInTimeLimitation: false,
    counts,
  };
}
