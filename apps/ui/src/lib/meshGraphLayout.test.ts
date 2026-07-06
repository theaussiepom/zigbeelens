import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";
import {
  buildGraphSignature,
  buildStructuralLayoutEdges,
  chooseLayoutStrategy,
  layoutMeshGraph,
} from "@/lib/meshGraphLayout";

const { elkLayoutMock } = vi.hoisted(() => ({ elkLayoutMock: vi.fn() }));

vi.mock("elkjs/lib/elk.bundled.js", () => ({
  default: class MockElk {
    layout = elkLayoutMock;
  },
}));

function device(ieee: string, role: MeshRole): MeshEvidenceDevice {
  return {
    ieee_address: ieee,
    network_id: "home",
    friendly_name: ieee,
    role,
    power: "unknown",
    availability: "unknown",
    health_bucket: "unknown",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "",
    passive_observation_summary: "",
    interpretation: "",
  };
}

function edge(
  source: string,
  target: string,
  evidenceClass: MeshEvidenceEdge["evidence_class"] = "latest_snapshot_neighbor",
): MeshEvidenceEdge {
  return {
    id: `${evidenceClass}-${source}-${target}`,
    network_id: "home",
    source,
    target,
    evidence_class: evidenceClass,
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    limitations: [],
    suggested_investigation: [],
  };
}

const coordinator = device("0xc0", "coordinator");
const router = device("0xr1", "router");
const lamp = device("0xe1", "end_device");
const devices = [coordinator, router, lamp];

function successfulLayout(graph: { children: Array<{ id: string }> }) {
  return Promise.resolve({
    children: graph.children.map((child, index) => ({ ...child, x: index * 10, y: index * 20 })),
  });
}

beforeEach(() => {
  elkLayoutMock.mockReset();
  elkLayoutMock.mockImplementation(successfulLayout);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildStructuralLayoutEdges", () => {
  it("collapses bidirectional neighbour evidence into one undirected structural edge", () => {
    const result = buildStructuralLayoutEdges(devices, [
      edge("0xr1", "0xc0"),
      edge("0xc0", "0xr1"),
    ]);
    expect(result).toHaveLength(1);
  });

  it("ignores parallel evidence classes on the same pair for positioning", () => {
    const result = buildStructuralLayoutEdges(devices, [
      edge("0xr1", "0xc0", "latest_snapshot_neighbor"),
      edge("0xr1", "0xc0", "latest_snapshot_route"),
      edge("0xc0", "0xr1", "latest_snapshot_route"),
    ]);
    expect(result).toHaveLength(1);
  });

  it("does not explode edge count on a dense bidirectional mesh", () => {
    const many = [coordinator, ...Array.from({ length: 20 }, (_, i) => device(`0xr${i}`, "router"))];
    const evidence: MeshEvidenceEdge[] = [];
    for (const a of many) {
      for (const b of many) {
        if (a.ieee_address === b.ieee_address) continue;
        evidence.push(edge(a.ieee_address, b.ieee_address));
      }
    }
    const result = buildStructuralLayoutEdges(many, evidence);
    // n*(n-1) directed evidence edges collapse to n*(n-1)/2 structural pairs.
    expect(evidence.length).toBe(21 * 20);
    expect(result).toHaveLength((21 * 20) / 2);
  });

  it("orients structural edges from higher role toward lower role", () => {
    const [structural] = buildStructuralLayoutEdges(devices, [edge("0xe1", "0xc0")]);
    expect(structural.sources).toEqual(["0xc0"]);
    expect(structural.targets).toEqual(["0xe1"]);
  });

  it("skips edges whose endpoints are missing from the device list", () => {
    const result = buildStructuralLayoutEdges(devices, [
      edge("0xr1", "0xmissing"),
      edge("0xr1", "0xc0"),
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].id).toContain("0xc0");
  });
});

describe("buildGraphSignature", () => {
  const structural = buildStructuralLayoutEdges(devices, [edge("0xr1", "0xc0")]);

  it("is stable across routine refreshes when the graph content is unchanged", () => {
    // Fresh array/object identities, same content — as produced by a refetch.
    const refetchedDevices = devices.map((d) => ({ ...d }));
    const refetchedStructural = buildStructuralLayoutEdges(refetchedDevices, [
      edge("0xr1", "0xc0"),
    ]);
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).toBe(
      buildGraphSignature("live|home|snap-1", refetchedDevices, refetchedStructural, "layered"),
    );
  });

  it("is independent of device and edge ordering", () => {
    const reversed = [...devices].reverse();
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).toBe(
      buildGraphSignature("live|home|snap-1", reversed, [...structural].reverse(), "layered"),
    );
  });

  it("changes when the snapshot seed changes", () => {
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).not.toBe(
      buildGraphSignature("live|home|snap-2", devices, structural, "layered"),
    );
  });

  it("changes when nodes or structural edges change", () => {
    const moreEdges = buildStructuralLayoutEdges(devices, [
      edge("0xr1", "0xc0"),
      edge("0xr1", "0xe1"),
    ]);
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).not.toBe(
      buildGraphSignature("live|home|snap-1", devices, moreEdges, "layered"),
    );
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).not.toBe(
      buildGraphSignature("live|home|snap-1", devices.slice(0, 2), structural, "layered"),
    );
  });

  it("changes when the layout strategy changes", () => {
    expect(buildGraphSignature("live|home|snap-1", devices, structural, "layered")).not.toBe(
      buildGraphSignature("live|home|snap-1", devices, structural, "mrtree"),
    );
  });
});

describe("chooseLayoutStrategy", () => {
  it("uses layered up to the dense threshold and mrtree above it", () => {
    expect(chooseLayoutStrategy(400)).toBe("layered");
    expect(chooseLayoutStrategy(401)).toBe("mrtree");
  });
});

describe("layoutMeshGraph", () => {
  it("uses the layered algorithm for small graphs and reports the strategy", async () => {
    const result = await layoutMeshGraph(devices, [edge("0xr1", "0xc0")]);
    expect(result.strategy).toBe("layered");
    expect(result.structuralEdgeCount).toBe(1);
    expect(result.positions.size).toBe(3);
    expect(elkLayoutMock).toHaveBeenCalledTimes(1);
    expect(elkLayoutMock.mock.calls[0][0].layoutOptions["elk.algorithm"]).toBe("layered");
  });

  it("feeds ELK the deduplicated structural edge set, not raw evidence edges", async () => {
    await layoutMeshGraph(devices, [
      edge("0xr1", "0xc0", "latest_snapshot_neighbor"),
      edge("0xc0", "0xr1", "latest_snapshot_neighbor"),
      edge("0xr1", "0xc0", "latest_snapshot_route"),
      edge("0xr1", "0xe1"),
    ]);
    expect(elkLayoutMock.mock.calls[0][0].edges).toHaveLength(2);
  });

  it("switches to mrtree for dense graphs instead of layered", async () => {
    const result = await layoutMeshGraph(
      devices,
      [edge("0xr1", "0xc0"), edge("0xr1", "0xe1")],
      { denseEdgeThreshold: 1 },
    );
    expect(result.strategy).toBe("mrtree");
    expect(elkLayoutMock).toHaveBeenCalledTimes(1);
    expect(elkLayoutMock.mock.calls[0][0].layoutOptions["elk.algorithm"]).toBe("mrtree");
  });

  it("falls back to mrtree when the layered layout fails", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    elkLayoutMock
      .mockRejectedValueOnce(new Error("Referenced shape does not exist: 0xdead"))
      .mockImplementationOnce(successfulLayout);
    const result = await layoutMeshGraph(devices, [edge("0xr1", "0xc0")]);
    expect(result.strategy).toBe("mrtree");
    expect(result.positions.size).toBe(3);
  });

  it("falls back to mrtree when the layered layout exceeds the timeout", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    elkLayoutMock
      .mockImplementationOnce(() => new Promise(() => {}))
      .mockImplementationOnce(successfulLayout);
    const result = await layoutMeshGraph(devices, [edge("0xr1", "0xc0")], { timeoutMs: 20 });
    expect(result.strategy).toBe("mrtree");
    expect(result.positions.size).toBe(3);
  });

  it("rejects when every layout strategy fails so callers can show an error state", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    elkLayoutMock.mockRejectedValue(new Error("boom"));
    await expect(layoutMeshGraph(devices, [edge("0xr1", "0xc0")])).rejects.toThrow("boom");
    expect(elkLayoutMock).toHaveBeenCalledTimes(2);
  });
});
