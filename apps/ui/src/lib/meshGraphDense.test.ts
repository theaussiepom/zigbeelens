import { describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  DENSE_DEFAULT_CONNECTION_CONTROLS,
  MAX_RECENT_MISSING_LINKS_PER_NODE,
  MAX_RECENT_MISSING_LINKS_TOTAL,
  collectIssueDeviceIds,
  countHiddenConnectionEdges,
  deviceHasIssue,
  isDenseGraph,
  selectBestNeighbourLinks,
  selectRecentMissingEdges,
  selectVisibleConnectionEdges,
  type ConnectionControls,
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

function device(ieee: string, overrides: Partial<MeshEvidenceDevice> = {}): MeshEvidenceDevice {
  return {
    ieee_address: ieee,
    network_id: "home",
    friendly_name: ieee,
    role: "router",
    power: "mains",
    availability: "online",
    health_bucket: "healthy",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "",
    passive_observation_summary: "",
    interpretation: "",
    ...overrides,
  };
}

function controls(overrides: Partial<ConnectionControls> = {}): ConnectionControls {
  return { ...DENSE_DEFAULT_CONNECTION_CONTROLS, ...overrides };
}

const emptyContext = {
  bestNeighbourEdgeIds: new Set<string>(),
  selectedNodeId: null,
};

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

describe("default connection controls", () => {
  it("matches the spec: routes/best on; issues, all, old and recent missing links off", () => {
    expect(DENSE_DEFAULT_CONNECTION_CONTROLS).toEqual({
      routeHints: true,
      bestNeighbourLinks: true,
      devicesWithIssues: false,
      allNeighbourLinks: false,
      oldUncertainLinks: false,
      recentMissingLinks: false,
    });
  });

  it("keeps Devices with issues off by default", () => {
    expect(DENSE_DEFAULT_CONNECTION_CONTROLS.devicesWithIssues).toBe(false);
  });

  it("keeps Recent missing links off by default", () => {
    expect(DENSE_DEFAULT_CONNECTION_CONTROLS.recentMissingLinks).toBe(false);
  });
});

describe("selectBestNeighbourLinks", () => {
  it("keeps up to N strongest links per device by recorded LQI", () => {
    const edges = [
      edge("a", "b", { id: "ab", lqi_latest: 200 }),
      edge("a", "c", { id: "ac", lqi_latest: 150 }),
      edge("a", "d", { id: "ad", lqi_latest: 100 }),
    ];
    const best = selectBestNeighbourLinks(edges, 2);
    expect(best.has("ab")).toBe(true);
    expect(best.has("ac")).toBe(true);
    // Weakest link is not in a's top 2, but it IS in d's top 2 (d has only
    // one link) — union keeps every device connected.
    expect(best.has("ad")).toBe(true);
  });

  it("drops weakest links only when no endpoint ranks them", () => {
    // b, c, d each connect to both hubs a and z; every leaf keeps 2 links,
    // so the union includes everything here — build a case where a's third
    // link is also the leaf's third.
    const edges = [
      edge("a", "b", { id: "ab", lqi_latest: 200 }),
      edge("a", "c", { id: "ac", lqi_latest: 180 }),
      edge("b", "c", { id: "bc", lqi_latest: 170 }),
      edge("a", "d", { id: "ad", lqi_latest: 20 }),
      edge("b", "d", { id: "bd", lqi_latest: 160 }),
      edge("c", "d", { id: "cd", lqi_latest: 150 }),
    ];
    const best = selectBestNeighbourLinks(edges, 2);
    // "ad" is a's weakest (3rd) and d's weakest (3rd): excluded everywhere.
    expect(best.has("ad")).toBe(false);
    expect(best.has("ab")).toBe(true);
    expect(best.has("bd")).toBe(true);
  });

  it("prefers links with recorded LQI over links without", () => {
    const edges = [
      edge("a", "b", { id: "ab", lqi_latest: 10 }),
      edge("a", "c", { id: "ac", lqi_latest: null }),
      edge("a", "d", { id: "ad", lqi_latest: 5 }),
    ];
    const best = selectBestNeighbourLinks(edges, 2);
    // Both recorded-LQI links beat the unrecorded one, even at low values —
    // missing LQI is unknown, not zero.
    expect(best.has("ab")).toBe(true);
    expect(best.has("ad")).toBe(true);
  });

  it("does not strand devices whose links have no recorded LQI", () => {
    const edges = [
      edge("a", "b", { id: "ab", lqi_latest: null }),
      edge("a", "c", { id: "ac", lqi_latest: null }),
      edge("a", "d", { id: "ad", lqi_latest: null }),
    ];
    const best = selectBestNeighbourLinks(edges, 2);
    expect(best.size).toBeGreaterThanOrEqual(2);
  });

  it("only considers latest_snapshot_neighbor edges", () => {
    const edges = [
      edge("a", "b", { id: "route", evidence_class: "latest_snapshot_route", directional: true }),
    ];
    expect(selectBestNeighbourLinks(edges, 2).size).toBe(0);
  });
});

describe("deviceHasIssue / collectIssueDeviceIds", () => {
  it("flags devices with existing issue signals only", () => {
    expect(deviceHasIssue(device("a"))).toBe(false);
    expect(deviceHasIssue(device("b", { flags: ["needs_attention"] }))).toBe(true);
    expect(deviceHasIssue(device("c", { flags: ["unavailable"] }))).toBe(true);
    expect(deviceHasIssue(device("d", { flags: ["interview_failure"] }))).toBe(true);
    expect(deviceHasIssue(device("e", { flags: ["weak_link_candidate"] }))).toBe(true);
    expect(deviceHasIssue(device("f", { flags: ["router_risk_candidate"] }))).toBe(true);
    expect(deviceHasIssue(device("g", { health_bucket: "unavailable" }))).toBe(true);
    expect(
      deviceHasIssue(device("h", { open_issue: { title: "t", summary: "s" } })),
    ).toBe(true);
  });

  it("does not treat sleepy batteries or limited diagnostics as issues", () => {
    expect(deviceHasIssue(device("a", { flags: ["battery_sleepy"] }))).toBe(false);
    expect(deviceHasIssue(device("b", { flags: ["diagnostics_limited"] }))).toBe(false);
    expect(deviceHasIssue(device("c", { health_bucket: "diagnostics_limited" }))).toBe(false);
  });

  it("collects issue device ids", () => {
    const ids = collectIssueDeviceIds([
      device("a"),
      device("b", { flags: ["needs_attention"] }),
    ]);
    expect(ids).toEqual(new Set(["b"]));
  });
});

describe("selectRecentMissingEdges", () => {
  const noInput = {
    issueDeviceIds: new Set<string>(),
    devicesWithLatestNeighbourEvidence: new Set<string>(),
    latestLayoutLimited: false,
  };

  function historical(
    source: string,
    target: string,
    overrides: Partial<MeshEvidenceEdge> = {},
  ): MeshEvidenceEdge {
    return edge(source, target, {
      evidence_class: "historical_neighbor",
      in_latest_snapshot: false,
      ...overrides,
    });
  }

  it("only considers historical evidence classes", () => {
    const chosen = selectRecentMissingEdges(
      [edge("a", "b", { id: "live" }), historical("c", "d", { id: "hist" })],
      noInput,
    );
    expect(chosen).toEqual(new Set(["hist"]));
  });

  it("caps historical links per node", () => {
    const edges = Array.from({ length: MAX_RECENT_MISSING_LINKS_PER_NODE + 4 }, (_, i) =>
      historical("hub", `leaf-${i}`, { id: `h-${i}` }),
    );
    const chosen = selectRecentMissingEdges(edges, noInput);
    expect(chosen.size).toBe(MAX_RECENT_MISSING_LINKS_PER_NODE);
  });

  it("caps historical links in total", () => {
    const edges = Array.from({ length: MAX_RECENT_MISSING_LINKS_TOTAL + 50 }, (_, i) =>
      historical(`a-${i}`, `b-${i}`, { id: `h-${i}` }),
    );
    const chosen = selectRecentMissingEdges(edges, noInput);
    expect(chosen.size).toBe(MAX_RECENT_MISSING_LINKS_TOTAL);
  });

  it("prioritises edges touching devices with existing issue flags", () => {
    const edges = [
      historical("hub", "plain-1", { id: "plain-1", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "plain-2", { id: "plain-2", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "plain-3", { id: "plain-3", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "flagged", { id: "flagged", last_seen_at: "2026-01-01T00:00:00Z" }),
    ];
    const chosen = selectRecentMissingEdges(edges, {
      ...noInput,
      issueDeviceIds: new Set(["flagged"]),
      // Everything has latest evidence, so only the issue flag grants priority.
      devicesWithLatestNeighbourEvidence: new Set([
        "hub",
        "plain-1",
        "plain-2",
        "plain-3",
        "flagged",
      ]),
    });
    // "flagged" is older but relevant, so it wins a slot under hub's cap.
    expect(chosen.has("flagged")).toBe(true);
    expect(chosen.size).toBe(MAX_RECENT_MISSING_LINKS_PER_NODE);
  });

  it("prioritises edges whose endpoint has no latest neighbour evidence", () => {
    const edges = [
      historical("hub", "covered-1", { id: "c1", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "covered-2", { id: "c2", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "covered-3", { id: "c3", last_seen_at: "2026-07-06T00:00:00Z" }),
      historical("hub", "orphan", { id: "orphan", last_seen_at: "2026-01-01T00:00:00Z" }),
    ];
    const chosen = selectRecentMissingEdges(edges, {
      ...noInput,
      devicesWithLatestNeighbourEvidence: new Set(["hub", "covered-1", "covered-2", "covered-3"]),
    });
    expect(chosen.has("orphan")).toBe(true);
  });

  it("treats every edge as relevant when the latest layout is limited", () => {
    const edges = [historical("a", "b", { id: "h1" }), historical("c", "d", { id: "h2" })];
    const chosen = selectRecentMissingEdges(edges, { ...noInput, latestLayoutLimited: true });
    expect(chosen).toEqual(new Set(["h1", "h2"]));
  });

  it("is deterministic for the same input", () => {
    const edges = Array.from({ length: 30 }, (_, i) =>
      historical(`a-${i % 10}`, `b-${i}`, { id: `h-${i}` }),
    );
    const first = selectRecentMissingEdges(edges, noInput);
    const second = selectRecentMissingEdges([...edges].reverse(), noInput);
    expect(second).toEqual(first);
  });
});

describe("selectVisibleConnectionEdges", () => {
  const routeEdge = edge("r1", "c0", {
    id: "route",
    evidence_class: "latest_snapshot_route",
    directional: true,
  });
  const bestNeighbour = edge("r1", "r2", { id: "best" });
  const otherNeighbour = edge("r3", "r4", { id: "other" });
  const staleEdge = edge("r5", "r6", { id: "stale", evidence_class: "stale_low_confidence" });
  const all = [routeEdge, bestNeighbour, otherNeighbour, staleEdge];
  const context = {
    ...emptyContext,
    bestNeighbourEdgeIds: new Set(["best"]),
  };

  it("shows routes and best neighbour links by default, not the rest", () => {
    const visible = selectVisibleConnectionEdges(all, controls(), context);
    expect(visible).toContain(routeEdge);
    expect(visible).toContain(bestNeighbour);
    expect(visible).not.toContain(otherNeighbour);
    expect(visible).not.toContain(staleEdge);
  });

  it("route hints toggle controls route evidence", () => {
    const visible = selectVisibleConnectionEdges(all, controls({ routeHints: false }), context);
    expect(visible).not.toContain(routeEdge);
  });

  it("best neighbour links toggle controls the readable subset", () => {
    const visible = selectVisibleConnectionEdges(
      all,
      controls({ bestNeighbourLinks: false }),
      context,
    );
    expect(visible).not.toContain(bestNeighbour);
  });

  it("all neighbour links shows every neighbour edge", () => {
    const visible = selectVisibleConnectionEdges(
      all,
      controls({ allNeighbourLinks: true }),
      context,
    );
    expect(visible).toContain(bestNeighbour);
    expect(visible).toContain(otherNeighbour);
    expect(visible).not.toContain(staleEdge);
  });

  it("old or uncertain links gates stale/low-confidence evidence", () => {
    const visible = selectVisibleConnectionEdges(
      all,
      controls({ oldUncertainLinks: true }),
      context,
    );
    expect(visible).toContain(staleEdge);
  });

  it("Devices with issues never expands to every edge touching issue devices", () => {
    // r3 is an issue device with a plain neighbour edge; the toggle is node
    // highlighting, so that edge must stay hidden even when enabled.
    const visible = selectVisibleConnectionEdges(
      all,
      controls({ devicesWithIssues: true }),
      context,
    );
    expect(visible).not.toContain(otherNeighbour);
  });

  it("Devices with issues reveals only edges already marked issue-related", () => {
    const issueEdge = edge("x", "y", { id: "issue", issue_related: true });
    const plainEdge = edge("x", "z", { id: "plain" });
    const on = selectVisibleConnectionEdges(
      [issueEdge, plainEdge],
      controls({ devicesWithIssues: true }),
      emptyContext,
    );
    expect(on).toContain(issueEdge);
    expect(on).not.toContain(plainEdge);

    const off = selectVisibleConnectionEdges([issueEdge, plainEdge], controls(), emptyContext);
    expect(off).not.toContain(issueEdge);
  });

  it("selecting an issue device still reveals its full evidence neighbourhood", () => {
    const visible = selectVisibleConnectionEdges(
      all,
      controls({ devicesWithIssues: true }),
      { ...context, selectedNodeId: "r3" },
    );
    expect(visible).toContain(otherNeighbour);
  });

  it("selected device links are always on: selection reveals every touching edge", () => {
    const visible = selectVisibleConnectionEdges(
      all,
      controls({
        routeHints: false,
        bestNeighbourLinks: false,
      }),
      { ...context, selectedNodeId: "r3" },
    );
    expect(visible).toContain(otherNeighbour);
    expect(visible).not.toContain(bestNeighbour);
  });

  it("a selected edge reveals edges touching its endpoints", () => {
    const visible = selectVisibleConnectionEdges(all, controls(), {
      ...context,
      selectedEdge: staleEdge,
    });
    expect(visible).toContain(staleEdge);
  });

  it("recent missing links render only the focused subset, never all history", () => {
    const inSubset = edge("h1", "h2", {
      id: "hist-in",
      evidence_class: "historical_neighbor",
      in_latest_snapshot: false,
    });
    const overCap = edge("h3", "h4", {
      id: "hist-out",
      evidence_class: "historical_route",
      directional: true,
      in_latest_snapshot: false,
    });
    const withHistory = [...all, inSubset, overCap];
    const historyContext = { ...context, recentMissingEdgeIds: new Set(["hist-in"]) };

    const off = selectVisibleConnectionEdges(withHistory, controls(), historyContext);
    expect(off).not.toContain(inSubset);
    expect(off).not.toContain(overCap);

    const on = selectVisibleConnectionEdges(
      withHistory,
      controls({ recentMissingLinks: true }),
      historyContext,
    );
    expect(on).toContain(inSubset);
    expect(on).not.toContain(overCap);
  });

  it("selecting a device reveals its recent missing links even over the cap", () => {
    const overCap = edge("h3", "h4", {
      id: "hist-out",
      evidence_class: "historical_neighbor",
      in_latest_snapshot: false,
    });
    const visible = selectVisibleConnectionEdges([...all, overCap], controls(), {
      ...context,
      recentMissingEdgeIds: new Set<string>(),
      selectedNodeId: "h3",
    });
    expect(visible).toContain(overCap);
  });

  it("never invents or removes evidence — output is a subset of input", () => {
    const visible = selectVisibleConnectionEdges(all, controls({ allNeighbourLinks: true }), {
      ...context,
      selectedNodeId: "r5",
    });
    for (const e of visible) expect(all).toContain(e);
  });
});

describe("countHiddenConnectionEdges", () => {
  it("reports how many available edges are hidden for readability", () => {
    const a = edge("a", "b");
    const b = edge("c", "d");
    const c = edge("e", "f");
    expect(countHiddenConnectionEdges([a, b, c], [a])).toBe(2);
    expect(countHiddenConnectionEdges([a], [a])).toBe(0);
  });
});
