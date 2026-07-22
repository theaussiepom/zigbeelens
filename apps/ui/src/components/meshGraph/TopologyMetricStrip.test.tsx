import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HistoricalEdgeAggregate, TopologyEvidenceGraphDetail } from "@/types/topology";
import { makeTopologyEvidenceGraphDetail } from "@/test/topologyEvidenceGraphFixture";
import { TopologyMetricStrip } from "./TopologyMetricStrip";

function renderMetricStrip(graphDetail: TopologyEvidenceGraphDetail) {
  const snapshot = graphDetail.latest_snapshot;
  if (!snapshot) {
    throw new Error("TopologyMetricStrip test fixture must include a latest snapshot");
  }
  return render(
    <TopologyMetricStrip
      graphDetail={graphDetail}
      snapshot={snapshot}
      liveEdgeCount={graphDetail.counts.latest_snapshot_neighbor_edges}
    />,
  );
}

function makeHistoricalEdge(
  overrides: Partial<HistoricalEdgeAggregate> = {},
): HistoricalEdgeAggregate {
  return {
    source_ieee: "0x1",
    target_ieee: "0x2",
    evidence_class: "historical_neighbor",
    directional: false,
    first_seen_at: "2026-07-01T00:00:00+00:00",
    last_seen_at: "2026-07-05T00:00:00+00:00",
    observed_count: 2,
    snapshot_count: 2,
    lqi_latest: 80,
    lqi_min: 70,
    lqi_median: 75,
    lqi_max: 80,
    route_observed_count: null,
    last_route_count: null,
    last_relationship: "Sibling",
    last_snapshot_id: "snap-history",
    last_captured_at: "2026-07-05T00:00:00+00:00",
    not_seen_in_latest_snapshot: true,
    latest_layout_limited: false,
    confidence: "medium",
    limitations: ["Historical fixture evidence is not a current link claim."],
    ...overrides,
  };
}

describe("TopologyMetricStrip", () => {
  it("renders node count from a complete accepted evidence-graph detail", () => {
    renderMetricStrip(
      makeTopologyEvidenceGraphDetail({
        nodes: [
          { ieee_address: "0x1", node_type: "Coordinator" },
          { ieee_address: "0x2", node_type: "Router" },
        ],
      }),
    );

    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Observed topology nodes").parentElement).toHaveTextContent("2");
  });

  it("keeps recent missing history unknown when no prior snapshots were considered", () => {
    renderMetricStrip(
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 30,
          snapshots_considered: 0,
          earliest_captured_at: null,
          latest_captured_at: null,
        },
      }),
    );

    const metric = screen.getByText("Recent missing links").parentElement;
    expect(metric).toHaveTextContent("—");
    expect(metric).not.toHaveTextContent("Recent missing links0");
    expect(screen.getByLabelText(/History unavailable because no previous snapshots/i)).toBe(metric);
  });

  it("renders measured zero when prior snapshots were considered", () => {
    renderMetricStrip(
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 30,
          snapshots_considered: 3,
          earliest_captured_at: "2026-07-01T00:00:00+00:00",
          latest_captured_at: "2026-07-05T00:00:00+00:00",
        },
      }),
    );

    expect(screen.getByText("Recent missing links").parentElement).toHaveTextContent("0");
  });

  it("renders a positive measured recent-missing count with considered history", () => {
    renderMetricStrip(
      makeTopologyEvidenceGraphDetail({
        history_window: {
          days: 7,
          max_snapshots: 30,
          snapshots_considered: 4,
          earliest_captured_at: "2026-07-01T00:00:00+00:00",
          latest_captured_at: "2026-07-05T00:00:00+00:00",
        },
        historical_neighbors: [
          makeHistoricalEdge({ source_ieee: "0x1", target_ieee: "0x2" }),
          makeHistoricalEdge({ source_ieee: "0x2", target_ieee: "0x3" }),
        ],
        historical_routes: [
          makeHistoricalEdge({
            source_ieee: "0x3",
            target_ieee: "0x4",
            evidence_class: "historical_route",
            directional: true,
            route_observed_count: 1,
            last_route_count: 1,
          }),
        ],
      }),
    );

    expect(screen.getByText("Recent missing links").parentElement).toHaveTextContent("3");
  });
});
