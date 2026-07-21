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

/**
 * Presentation for a network's latest overview snapshot on `/topology`.
 * Does not invent Core status values; unknown never becomes complete.
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
    const routers = latest.router_count ?? 0;
    const links = latest.link_count ?? 0;
    const counts = `${routers} topology routers · ${links} topology links`;
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
