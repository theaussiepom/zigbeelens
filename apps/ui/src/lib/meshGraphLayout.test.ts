import { describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge, MeshRole } from "@/lib/meshEvidence";
import { buildStructuralLayoutEdges } from "@/lib/meshGraphLayout";

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

describe("buildStructuralLayoutEdges", () => {
  it("collapses bidirectional neighbour evidence into one undirected structural edge", () => {
    const result = buildStructuralLayoutEdges(devices, [
      edge("0xr1", "0xc0"),
      edge("0xc0", "0xr1"),
    ]);
    expect(result).toHaveLength(1);
  });

  it("ignores parallel evidence classes on the same pair", () => {
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
