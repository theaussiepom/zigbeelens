import { afterEach, describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";
import {
  DEFAULT_LAYOUT_MODE,
  MESH_LAYOUT_MODES,
  applySavedPositions,
  assignEndDevicesToRouters,
  classifyDevices,
  clearSavedPositions,
  computeMeshLayout,
  evidencePairWeights,
  loadSavedPositions,
  orderRoutersByEvidence,
  positionStorageKey,
  saveNodePosition,
} from "@/lib/meshGraphSmartLayout";

function device(
  ieee: string,
  role: MeshRole,
  overrides: Partial<MeshEvidenceDevice> = {},
): MeshEvidenceDevice {
  return {
    ieee_address: ieee,
    network_id: "home",
    friendly_name: ieee,
    role,
    power: role === "end_device" ? "battery" : "mains",
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

function neighbour(
  source: string,
  target: string,
  lqi: number | null = null,
): MeshEvidenceEdge {
  return {
    id: `n-${source}-${target}`,
    network_id: "home",
    source,
    target,
    evidence_class: "latest_snapshot_neighbor",
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    lqi_latest: lqi ?? undefined,
    limitations: [],
    suggested_investigation: [],
  };
}

const coordinator = device("0xc0", "coordinator");
const router1 = device("0xr1", "router");
const router2 = device("0xr2", "router");
const bulb = device("0xe1", "end_device");
const sensor = device("0xe2", "end_device");
const orphan = device("0xe3", "end_device");
const ghost = device("0xu1", "unknown", {
  inventory_status: "Referenced by the latest topology snapshot only",
});

const devices = [coordinator, router1, router2, bulb, sensor, orphan, ghost];
const edges = [
  neighbour("0xc0", "0xr1", 220),
  neighbour("0xc0", "0xr2", 210),
  neighbour("0xr1", "0xr2", 180),
  neighbour("0xe1", "0xr1", 190),
  neighbour("0xe1", "0xr2", 90),
  neighbour("0xe2", "0xr2", null),
  // orphan and ghost have no neighbour evidence.
];

describe("layout modes", () => {
  it("exposes the five required human-named modes with smart as default", () => {
    expect(MESH_LAYOUT_MODES.map((m) => m.label)).toEqual([
      "Smart layout",
      "Router backbone",
      "Router clusters",
      "Health focus",
      "Manual layout",
    ]);
    expect(DEFAULT_LAYOUT_MODE).toBe("smart");
  });

  it("manual layout copy mentions browser-local saved positions", () => {
    const manual = MESH_LAYOUT_MODES.find((m) => m.id === "manual");
    expect(manual?.description).toContain("remembers your positions on this browser");
  });

  it("router clusters copy does not claim live routing", () => {
    const clusters = MESH_LAYOUT_MODES.find((m) => m.id === "clusters");
    expect(clusters?.description).toContain("does not prove current live routing");
  });
});

describe("classifyDevices", () => {
  it("classifies coordinator, routers, end devices and unknown/limited nodes", () => {
    const result = classifyDevices(devices);
    expect(result.coordinators.map((d) => d.ieee_address)).toEqual(["0xc0"]);
    expect(result.routers.map((d) => d.ieee_address).sort()).toEqual(["0xr1", "0xr2"]);
    expect(result.endDevices.map((d) => d.ieee_address).sort()).toEqual([
      "0xe1",
      "0xe2",
      "0xe3",
    ]);
    expect(result.limited.map((d) => d.ieee_address)).toEqual(["0xu1"]);
  });
});

describe("assignEndDevicesToRouters", () => {
  it("attaches each end device to the router with the strongest observed LQI", () => {
    const assignment = assignEndDevicesToRouters(devices, edges);
    expect(assignment.get("0xe1")).toBe("0xr1"); // LQI 190 beats 90
  });

  it("uses router evidence without recorded LQI rather than stranding devices", () => {
    const assignment = assignEndDevicesToRouters(devices, edges);
    expect(assignment.get("0xe2")).toBe("0xr2");
  });

  it("leaves devices without router evidence unassigned", () => {
    const assignment = assignEndDevicesToRouters(devices, edges);
    expect(assignment.has("0xe3")).toBe(false);
  });
});

describe("evidencePairWeights", () => {
  it("accumulates parallel evidence and weights routes above neighbour links", () => {
    const ids = new Set(["a", "b", "c"]);
    const weights = evidencePairWeights(ids, [
      neighbour("a", "b", 100),
      neighbour("b", "a", 50),
      {
        ...neighbour("a", "c", 10),
        id: "route-ac",
        evidence_class: "latest_snapshot_route",
        directional: true,
      },
    ]);
    expect(weights.get("a|b")).toBe(150);
    // Route evidence dominates even at low LQI.
    expect(weights.get("a|c")!).toBeGreaterThan(weights.get("a|b")!);
  });

  it("ignores edges outside the member set and self-loops", () => {
    const weights = evidencePairWeights(new Set(["a", "b"]), [
      neighbour("a", "x", 200),
      neighbour("a", "a", 200),
      neighbour("a", "b", 80),
    ]);
    expect([...weights.keys()]).toEqual(["a|b"]);
  });
});

describe("orderRoutersByEvidence", () => {
  const r = (ieee: string) => device(ieee, "router");

  it("places strongly-linked routers adjacent to each other", () => {
    // Chain evidence: a—b strong, b—c strong, a—d weak. Expected order keeps
    // a,b,c contiguous instead of interleaving d between them.
    const routers = [r("d"), r("a"), r("c"), r("b")];
    const order = orderRoutersByEvidence(routers, [
      neighbour("a", "b", 250),
      neighbour("b", "c", 240),
      neighbour("a", "d", 30),
    ]).map((x) => x.ieee_address);
    const pos = (id: string) => order.indexOf(id);
    expect(Math.abs(pos("a") - pos("b"))).toBe(1);
    expect(Math.abs(pos("b") - pos("c"))).toBe(1);
  });

  it("is deterministic regardless of input order", () => {
    const routers = [r("a"), r("b"), r("c"), r("d")];
    const evidence = [
      neighbour("a", "b", 250),
      neighbour("b", "c", 240),
      neighbour("c", "d", 230),
    ];
    const forward = orderRoutersByEvidence(routers, evidence).map((x) => x.ieee_address);
    const backward = orderRoutersByEvidence([...routers].reverse(), [...evidence].reverse()).map(
      (x) => x.ieee_address,
    );
    expect(backward).toEqual(forward);
  });

  it("appends routers with no evidence in stable name order", () => {
    const isolated1 = device("z1", "router", { friendly_name: "Zeta" });
    const isolated2 = device("y1", "router", { friendly_name: "Alpha" });
    const order = orderRoutersByEvidence(
      [isolated1, r("a"), isolated2, r("b"), r("c")],
      [neighbour("a", "b", 250), neighbour("b", "c", 200)],
    ).map((x) => x.ieee_address);
    // Isolated routers come last, alphabetical by name (Alpha before Zeta).
    expect(order.slice(-2)).toEqual(["y1", "z1"]);
  });
});

describe("computeMeshLayout", () => {
  it("places every device deterministically in every mode", () => {
    for (const mode of MESH_LAYOUT_MODES) {
      const first = computeMeshLayout(devices, edges, mode.id);
      const second = computeMeshLayout(devices, edges, mode.id);
      expect(first.size).toBe(devices.length);
      for (const d of devices) {
        expect(first.get(d.ieee_address)).toEqual(second.get(d.ieee_address));
      }
    }
  });

  it("smart layout anchors the coordinator above the router backbone", () => {
    const positions = computeMeshLayout(devices, edges, "smart");
    const coord = positions.get("0xc0")!;
    expect(coord.y).toBeLessThan(positions.get("0xr1")!.y);
    expect(coord.y).toBeLessThan(positions.get("0xr2")!.y);
  });

  it("smart layout places end devices below their evidence router", () => {
    const positions = computeMeshLayout(devices, edges, "smart");
    expect(positions.get("0xe1")!.y).toBeGreaterThan(positions.get("0xr1")!.y);
    expect(positions.get("0xe2")!.y).toBeGreaterThan(positions.get("0xr2")!.y);
  });

  it("smart layout groups unassigned and limited devices below the mesh", () => {
    const positions = computeMeshLayout(devices, edges, "smart");
    const routerBottom = Math.max(positions.get("0xr1")!.y, positions.get("0xr2")!.y);
    expect(positions.get("0xe3")!.y).toBeGreaterThan(routerBottom);
    expect(positions.get("0xu1")!.y).toBeGreaterThan(positions.get("0xe3")!.y);
  });

  it("router backbone keeps coordinator and all routers in the top bands", () => {
    const positions = computeMeshLayout(devices, edges, "backbone");
    const routerYs = [positions.get("0xr1")!.y, positions.get("0xr2")!.y];
    // Single backbone band: routers share one row.
    expect(routerYs[0]).toBe(routerYs[1]);
    expect(positions.get("0xc0")!.y).toBeLessThan(routerYs[0]);
    for (const end of ["0xe1", "0xe2"]) {
      expect(positions.get(end)!.y).toBeGreaterThan(routerYs[0]);
    }
  });

  it("router clusters place end devices near their evidence router", () => {
    const positions = computeMeshLayout(devices, edges, "clusters");
    const r1 = positions.get("0xr1")!;
    const r2 = positions.get("0xr2")!;
    const e1 = positions.get("0xe1")!;
    const distTo = (a: { x: number; y: number }, b: { x: number; y: number }) =>
      Math.hypot(a.x - b.x, a.y - b.y);
    expect(distTo(e1, r1)).toBeLessThan(distTo(e1, r2));
  });

  it("health focus pulls issue devices into a prominent band without touching edges", () => {
    const flagged = device("0xe9", "end_device", { flags: ["needs_attention"] });
    const withIssue = [...devices, flagged];
    const positions = computeMeshLayout(withIssue, edges, "health");
    // Issue device sits above the coordinator: the most prominent area.
    expect(positions.get("0xe9")!.y).toBeLessThan(positions.get("0xc0")!.y);
    // Layout never manufactures or removes evidence — positions only.
    expect(positions.size).toBe(withIssue.length);
  });

  it("manual mode uses the smart hierarchy as its base", () => {
    const smart = computeMeshLayout(devices, edges, "smart");
    const manual = computeMeshLayout(devices, edges, "manual");
    for (const d of devices) {
      expect(manual.get(d.ieee_address)).toEqual(smart.get(d.ieee_address));
    }
  });

  it("does not depend on which edges are visible — only the full evidence set", () => {
    const shuffled = [...edges].reverse();
    const a = computeMeshLayout(devices, edges, "smart");
    const b = computeMeshLayout(devices, shuffled, "smart");
    for (const d of devices) {
      expect(b.get(d.ieee_address)).toEqual(a.get(d.ieee_address));
    }
  });

  it("keeps every node box separated at default layout spacing", () => {
    const manyRouters = Array.from({ length: 12 }, (_, i) =>
      device(`0xr${i}`, "router", { friendly_name: `Router ${i}` }),
    );
    const manyEnds = Array.from({ length: 24 }, (_, i) =>
      device(`0xe${i}`, "end_device", { friendly_name: `End ${i}` }),
    );
    const denseDevices = [coordinator, ...manyRouters, ...manyEnds];
    const denseEdges = [
      ...manyRouters.map((r) => neighbour("0xc0", r.ieee_address, 200)),
      ...manyRouters.slice(1).map((r, i) =>
        neighbour(manyRouters[i].ieee_address, r.ieee_address, 150),
      ),
      ...manyEnds.map((e, i) =>
        neighbour(e.ieee_address, manyRouters[i % manyRouters.length].ieee_address, 120),
      ),
    ];
    const positions = computeMeshLayout(denseDevices, denseEdges, "smart");
    const ids = denseDevices.map((d) => d.ieee_address);
    const minGap = 8;
    for (let i = 0; i < ids.length; i += 1) {
      const a = positions.get(ids[i])!;
      for (let j = i + 1; j < ids.length; j += 1) {
        const b = positions.get(ids[j])!;
        const separated =
          a.x + MESH_NODE_WIDTH + minGap <= b.x ||
          b.x + MESH_NODE_WIDTH + minGap <= a.x ||
          a.y + MESH_NODE_HEIGHT + minGap <= b.y ||
          b.y + MESH_NODE_HEIGHT + minGap <= a.y;
        expect(separated).toBe(true);
      }
    }
  });
});

describe("saved manual positions", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("uses a versioned, network- and mode-scoped storage key", () => {
    expect(positionStorageKey("home", "smart")).toBe(
      "zigbeelens.meshGraph.positions.v1.home.smart",
    );
  });

  it("saves, loads and clears positions per network and mode", () => {
    saveNodePosition("home", "smart", "0xe1", { x: 10, y: 20 });
    saveNodePosition("home", "smart", "0xe2", { x: 30, y: 40 });
    expect(loadSavedPositions("home", "smart")).toEqual({
      "0xe1": { x: 10, y: 20 },
      "0xe2": { x: 30, y: 40 },
    });
    // Other modes/networks are unaffected.
    expect(loadSavedPositions("home", "manual")).toEqual({});
    expect(loadSavedPositions("other", "smart")).toEqual({});

    clearSavedPositions("home", "smart");
    expect(loadSavedPositions("home", "smart")).toEqual({});
  });

  it("ignores corrupt stored data", () => {
    localStorage.setItem(positionStorageKey("home", "smart"), "{not json");
    expect(loadSavedPositions("home", "smart")).toEqual({});
    localStorage.setItem(
      positionStorageKey("home", "smart"),
      JSON.stringify({ "0xe1": { x: "bad" } }),
    );
    expect(loadSavedPositions("home", "smart")).toEqual({});
  });

  it("saved positions override generated ones for existing devices only", () => {
    const generated = computeMeshLayout(devices, edges, "smart");
    const overlaid = applySavedPositions(generated, {
      "0xe1": { x: -999, y: -999 },
      "0xgone": { x: 1, y: 2 }, // device no longer exists: ignored
    });
    expect(overlaid.get("0xe1")).toEqual({ x: -999, y: -999 });
    expect(overlaid.has("0xgone")).toBe(false);
    // New/unsaved devices keep their generated spot.
    expect(overlaid.get("0xe2")).toEqual(generated.get("0xe2"));
  });
});
