import { describe, expect, it } from "vitest";
import type { MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  countHiddenEvidenceEdges,
  isDenseGraph,
  selectVisibleEdgesForDenseMode,
} from "@/lib/meshGraphDense";

function edge(
  source: string,
  target: string,
  overrides: Partial<MeshEvidenceEdge> = {},
): MeshEvidenceEdge {
  return {
    id: overrides.id ?? `${overrides.evidence_class ?? "latest_snapshot_neighbor"}-${source}-${target}`,
    network_id: "home",
    source,
    target,
    evidence_class: "latest_snapshot_neighbor",
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    limitations: [],
    suggested_investigation: [],
    ...overrides,
  };
}

describe("isDenseGraph", () => {
  it("stays off for small graphs", () => {
    expect(
      isDenseGraph({ nodeCount: 20, evidenceEdgeCount: 40, structuralEdgeCount: 30 }),
    ).toBe(false);
  });

  it("triggers on total evidence edge count", () => {
    expect(
      isDenseGraph({ nodeCount: 20, evidenceEdgeCount: 251, structuralEdgeCount: 100 }),
    ).toBe(true);
    expect(
      isDenseGraph({ nodeCount: 20, evidenceEdgeCount: 250, structuralEdgeCount: 100 }),
    ).toBe(false);
  });

  it("triggers on structural layout edge count", () => {
    expect(
      isDenseGraph({ nodeCount: 20, evidenceEdgeCount: 100, structuralEdgeCount: 401 }),
    ).toBe(true);
  });

  it("triggers on combined node and edge counts", () => {
    expect(
      isDenseGraph({ nodeCount: 81, evidenceEdgeCount: 240, structuralEdgeCount: 100 }),
    ).toBe(false);
    // The reference dense network shape: many nodes and many links.
    expect(
      isDenseGraph({ nodeCount: 106, evidenceEdgeCount: 843, structuralEdgeCount: 843 }),
    ).toBe(true);
  });
});

describe("selectVisibleEdgesForDenseMode", () => {
  const routeEdge = edge("0xr1", "0xc0", {
    evidence_class: "latest_snapshot_route",
    directional: true,
  });
  const issueEdge = edge("0xr2", "0xr3", { issue_related: true });
  const neighborA = edge("0xr1", "0xr2");
  const neighborB = edge("0xr3", "0xr4");
  const all = [routeEdge, issueEdge, neighborA, neighborB];

  it("keeps route evidence visible with no selection", () => {
    const visible = selectVisibleEdgesForDenseMode(all, null);
    expect(visible).toContain(routeEdge);
    expect(visible).not.toContain(neighborA);
    expect(visible).not.toContain(neighborB);
  });

  it("keeps issue-related evidence visible with no selection", () => {
    expect(selectVisibleEdgesForDenseMode(all, null)).toContain(issueEdge);
  });

  it("reveals the full neighbourhood of the selected node", () => {
    const visible = selectVisibleEdgesForDenseMode(all, "0xr1");
    expect(visible).toContain(neighborA);
    expect(visible).not.toContain(neighborB);
  });

  it("reveals edges touching a selected edge's endpoints", () => {
    const visible = selectVisibleEdgesForDenseMode(all, null, neighborB);
    expect(visible).toContain(neighborB);
    // 0xr3 is an endpoint of the selected edge, so issueEdge stays visible
    // regardless, and neighbourB's own endpoints are in focus.
    expect(visible).not.toContain(neighborA);
  });

  it("never invents or removes evidence — output is a subset of input", () => {
    const visible = selectVisibleEdgesForDenseMode(all, "0xr1");
    for (const e of visible) expect(all).toContain(e);
  });
});

describe("countHiddenEvidenceEdges", () => {
  it("reports how many filter-visible edges are hidden for readability", () => {
    const a = edge("a", "b");
    const b = edge("c", "d");
    const c = edge("e", "f");
    expect(countHiddenEvidenceEdges([a, b, c], [a])).toBe(2);
    expect(countHiddenEvidenceEdges([a], [a])).toBe(0);
  });
});
