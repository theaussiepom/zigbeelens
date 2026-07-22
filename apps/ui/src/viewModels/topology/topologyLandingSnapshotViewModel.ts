import type { Severity } from "@zigbeelens/shared";
import { relativeTime } from "@/lib/format";
import { topologyStatusLabel } from "@/lib/topologyLabels";
import { snapshotSummaryLooksLimited } from "@/lib/topologyStats";
import type { TopologySnapshotSummary } from "@/types/topology";

export interface TopologyLandingSnapshotViewModel {
  /** Badge / status label shown on the landing network card. */
  label: string;
  severity: Severity;
  /** Muted supporting line under the network name. */
  summaryText: string;
}

function formatTopologyCount(
  count: number | null | undefined,
  singular: string,
  plural: string,
): string {
  if (count === null || count === undefined) {
    return `— ${plural}`;
  }
  if (count === 1) {
    return `1 ${singular}`;
  }
  return `${count} ${plural}`;
}

/**
 * Presentation for a network's latest overview snapshot on `/topology`.
 * Does not invent Core status values; unknown never becomes complete.
 * Individual null counts stay unknown and are never coerced to measured zero.
 */
export function buildTopologyLandingSnapshotViewModel(
  latest: TopologySnapshotSummary | null | undefined,
): TopologyLandingSnapshotViewModel {
  if (!latest) {
    return {
      label: "No snapshot",
      severity: "watch",
      summaryText: "No topology snapshot captured yet",
    };
  }

  const captured = latest.captured_at
    ? `Latest snapshot ${relativeTime(latest.captured_at)}`
    : null;
  const status = latest.status;

  if (status === "complete") {
    if (snapshotSummaryLooksLimited(latest)) {
      return {
        label: "Complete · layout limited",
        severity: "watch",
        summaryText: captured
          ? `${captured} · topology layout limited`
          : "Topology layout limited",
      };
    }
    const counts = [
      formatTopologyCount(latest.router_count, "topology router", "topology routers"),
      formatTopologyCount(latest.link_count, "topology link", "topology links"),
    ].join(" · ");
    return {
      label: topologyStatusLabel("complete"),
      severity: "healthy",
      summaryText: captured ? `${captured} · ${counts}` : counts,
    };
  }

  if (status === "pending") {
    return {
      label: topologyStatusLabel("pending"),
      severity: "watch",
      summaryText: captured ? `${captured} · capture pending` : "Capture pending",
    };
  }

  if (status === "error") {
    return {
      label: topologyStatusLabel("error"),
      severity: "critical",
      summaryText: captured ? `${captured} · capture error` : "Capture error",
    };
  }

  return {
    label: "Status unknown",
    severity: "watch",
    summaryText: captured ?? "Latest snapshot status unknown",
  };
}
