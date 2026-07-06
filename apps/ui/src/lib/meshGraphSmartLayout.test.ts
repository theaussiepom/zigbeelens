import { afterEach, describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";
import {
  DEFAULT_LAYOUT_MODE,
  MESH_LAYOUT_MODES,
  applySavedPositions,
  assignEndDevicesToRouters,
  classifyDevices,
  clearSavedPositions,
  computeMeshLayout,
  loadSavedPositions,
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
    // Connection-control toggles pass the same full edge set, so positions
    // cannot move; this asserts determinism against edge ordering too.
    const shuffled = [...edges].reverse();
    const a = computeMeshLayout(devices, edges, "smart");
    const b = computeMeshLayout(devices, shuffled, "smart");
    for (const d of devices) {
      expect(b.get(d.ieee_address)).toEqual(a.get(d.ieee_address));
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
