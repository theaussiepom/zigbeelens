import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { useGraphSelection } from "./useGraphSelection";

function device(overrides: Partial<MeshEvidenceDevice> = {}): MeshEvidenceDevice {
  return {
    ieee_address: "0x1",
    network_id: "home",
    friendly_name: "Topology-only device",
    role: "unknown",
    power: "unknown",
    availability: "unknown",
    in_inventory: null,
    in_latest_snapshot: true,
    health_bucket: "unknown",
    flags: [],
    inventory_status: "Inventory unavailable",
    topology_evidence_summary: "Observed in the latest topology snapshot.",
    passive_observation_summary: "No accepted passive observations.",
    diagnostic_stats: [],
    ...overrides,
  };
}

function edge(overrides: Partial<MeshEvidenceEdge> = {}): MeshEvidenceEdge {
  return {
    id: "live-neighbor-0x1|0x2",
    network_id: "home",
    source: "0x1",
    target: "0x2",
    evidence_class: "latest_snapshot_neighbor",
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    lqi_latest: 80,
    limitations: [],
    suggested_investigation: [],
    ...overrides,
  };
}

describe("useGraphSelection", () => {
  it("resolves a selected device from the newest accepted evidence object", () => {
    const firstDevice = device();
    const { result, rerender } = renderHook(
      ({ evidence }) => useGraphSelection("home", evidence),
      { initialProps: { evidence: { devices: [firstDevice], edges: [] } } },
    );

    act(() => result.current.selectNode(firstDevice));
    expect(result.current.selectedDevice).toBe(firstDevice);

    const acceptedInventoryDevice = device({
      friendly_name: "Accepted Kitchen Sensor",
      role: "end_device",
      in_inventory: true,
      inventory_status: "In Zigbee2MQTT device inventory",
      health_bucket: "needs_attention",
    });
    rerender({ evidence: { devices: [acceptedInventoryDevice], edges: [] } });

    expect(result.current.selectedDevice).toBe(acceptedInventoryDevice);
    expect(result.current.selectedDevice).toMatchObject({
      friendly_name: "Accepted Kitchen Sensor",
      role: "end_device",
      in_inventory: true,
      health_bucket: "needs_attention",
    });
  });

  it("keeps a selection while retained evidence is reused after a refresh error", () => {
    const retainedDevice = device({ friendly_name: "Retained accepted device" });
    const retainedEvidence = { devices: [retainedDevice], edges: [] };
    const { result, rerender } = renderHook(
      ({ evidence }) => useGraphSelection("home", evidence),
      { initialProps: { evidence: retainedEvidence } },
    );

    act(() => result.current.selectNode(retainedDevice));
    rerender({ evidence: retainedEvidence });

    expect(result.current.selectedDevice).toBe(retainedDevice);
  });

  it("clears a selected device when its identity disappears", async () => {
    const selected = device();
    const { result, rerender } = renderHook(
      ({ evidence }) => useGraphSelection("home", evidence),
      { initialProps: { evidence: { devices: [selected], edges: [] } } },
    );

    act(() => result.current.selectNode(selected));
    rerender({ evidence: { devices: [], edges: [] } });

    await waitFor(() => expect(result.current.selectedNodeId).toBeNull());
    expect(result.current.selectedDevice).toBeNull();
  });

  it("hides and clears selection as soon as the network changes", async () => {
    const selected = device();
    const { result, rerender } = renderHook(
      ({ networkId, evidence }) => useGraphSelection(networkId, evidence),
      {
        initialProps: {
          networkId: "home",
          evidence: { devices: [selected], edges: [] },
        },
      },
    );

    act(() => result.current.selectNode(selected));
    rerender({
      networkId: "shed",
      evidence: { devices: [device({ network_id: "shed" })], edges: [] },
    });

    expect(result.current.selectedDevice).toBeNull();
    expect(result.current.selectedNodeId).toBeNull();
    await waitFor(() => expect(result.current.selectedEdge).toBeNull());
  });

  it("updates a selected edge by id and clears it when that id disappears", async () => {
    const firstEdge = edge();
    const { result, rerender } = renderHook(
      ({ evidence }) => useGraphSelection("home", evidence),
      { initialProps: { evidence: { devices: [], edges: [firstEdge] } } },
    );

    act(() => result.current.selectEdge(firstEdge));
    const refreshedEdge = edge({ lqi_latest: 145, confidence: "medium" });
    rerender({ evidence: { devices: [], edges: [refreshedEdge] } });
    expect(result.current.selectedEdge).toBe(refreshedEdge);
    expect(result.current.selectedEdge).toMatchObject({ lqi_latest: 145, confidence: "medium" });

    rerender({ evidence: { devices: [], edges: [] } });
    await waitFor(() => expect(result.current.selectedEdge).toBeNull());
  });
});
