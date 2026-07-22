import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TopologyEvidenceGraphDetail } from "@/types/topology";
import { TopologyMetricStrip } from "./TopologyMetricStrip";

function graphDetail(nodes: TopologyEvidenceGraphDetail["nodes"]): TopologyEvidenceGraphDetail {
  return {
    network_id: "home",
    network_name: "Home",
    nodes,
    links: [],
    counts: {
      latest_snapshot_neighbor_edges: 0,
      latest_snapshot_route_edges: 0,
      historical_neighbor_edges: 0,
      historical_route_edges: 0,
      recent_missing_link_count_total: 0,
      last_known_link_count: 0,
      passive_hint_count_available: 0,
      passive_hint_count_total: 0,
      passive_hint_count_drawn: null,
      hidden_for_readability: null,
      known_inventory_devices: 0,
      observed_topology_nodes: nodes.length,
    },
  } as TopologyEvidenceGraphDetail;
}

describe("TopologyMetricStrip", () => {
  it("renders node count from an accepted non-null graph detail", () => {
    render(
      <TopologyMetricStrip
        graphDetail={graphDetail([
          { ieee_address: "0x1", node_type: "Coordinator" },
          { ieee_address: "0x2", node_type: "Router" },
        ])}
        snapshot={{ snapshot_id: "snap-1", status: "complete" }}
        liveEdgeCount={0}
      />,
    );
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Observed topology nodes").parentElement).toHaveTextContent("2");
  });

  it("keeps null narrowing at the caller and has no numeric absence fallback", () => {
    const componentSource = readFileSync(path.join(__dirname, "TopologyMetricStrip.tsx"), "utf8");
    const pageSource = readFileSync(
      path.join(__dirname, "../../pages/TopologyGraphPage.tsx"),
      "utf8",
    );
    expect(componentSource).toContain("graphDetail: TopologyEvidenceGraphDetail;");
    expect(componentSource).toContain("value={graphDetail.nodes.length}");
    expect(componentSource).not.toMatch(/graphDetail\?\.nodes\?\.length\s*\?\?\s*0/);
    expect(pageSource).toMatch(/graphDetail\s*&&\s*liveEvidence\s*&&\s*snapshot/);
  });
});
