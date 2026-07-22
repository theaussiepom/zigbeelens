import type { TopologyEvidenceGraphDetail } from "@/types/topology";

export type HistoryEvaluationState =
  | "not_evaluated"
  | "layout_limited"
  | "evaluated_empty"
  | "available";

export interface HistoryControlPresentation {
  state: HistoryEvaluationState;
  evidenceCount: number;
  helper: string;
}

export interface ConnectionHistoryPresentationViewModel {
  recentMissingLinks: HistoryControlPresentation;
  lastKnownLinks: HistoryControlPresentation;
}

function recentMissingPresentation(
  detail: TopologyEvidenceGraphDetail,
): HistoryControlPresentation {
  const evidenceCount =
    detail.counts.historical_neighbor_edges + detail.counts.historical_route_edges;

  if (detail.history_window.snapshots_considered === 0) {
    const days = detail.history_window.days;
    return {
      state: "not_evaluated",
      evidenceCount,
      helper: `No previous complete snapshots are available in the selected ${days}-day history window, so recent missing links could not be evaluated.`,
    };
  }
  if (detail.latest_layout_limited === true || detail.layout_available === false) {
    return {
      state: "layout_limited",
      evidenceCount,
      helper:
        "The latest topology layout is limited, so recent missing links cannot be measured reliably.",
    };
  }
  if (evidenceCount === 0) {
    return {
      state: "evaluated_empty",
      evidenceCount,
      helper:
        "Previous snapshots were evaluated; no recent missing links were measured in the selected history window.",
    };
  }
  return {
    state: "available",
    evidenceCount,
    helper: `${evidenceCount} recent missing ${evidenceCount === 1 ? "link is" : "links are"} available from evaluated history.`,
  };
}

function lastKnownPresentation(
  detail: TopologyEvidenceGraphDetail,
): HistoryControlPresentation {
  const evidenceCount = detail.last_known_links.length;

  // Core intentionally returns a zeroed last-known window when the latest
  // layout is limited. Layout limitation therefore owns precedence over the
  // otherwise ambiguous zero snapshot count.
  if (detail.latest_layout_limited === true || detail.layout_available === false) {
    return {
      state: "layout_limited",
      evidenceCount,
      helper:
        "The latest topology layout is limited, so absence from it cannot be assessed for last known links.",
    };
  }
  if (detail.last_known_window.snapshots_considered === 0) {
    return {
      state: "not_evaluated",
      evidenceCount,
      helper:
        "No previous complete snapshots are available, so last known links could not be evaluated.",
    };
  }
  if (evidenceCount === 0) {
    return {
      state: "evaluated_empty",
      evidenceCount,
      helper:
        "Previous snapshots were evaluated, but no last known link qualified for display.",
    };
  }
  return {
    state: "available",
    evidenceCount,
    helper: `${evidenceCount} last known ${evidenceCount === 1 ? "link is" : "links are"} available from stored evidence.`,
  };
}

/**
 * Keeps graph-control copy tied to the server's evaluation facts. An empty
 * result is only described as measured when Core actually considered prior
 * snapshots and the latest layout was usable.
 */
export function buildConnectionHistoryPresentationViewModel(
  detail: TopologyEvidenceGraphDetail,
): ConnectionHistoryPresentationViewModel {
  return {
    recentMissingLinks: recentMissingPresentation(detail),
    lastKnownLinks: lastKnownPresentation(detail),
  };
}
