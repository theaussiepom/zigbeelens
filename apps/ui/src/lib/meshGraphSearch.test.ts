import { describe, expect, it } from "vitest";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { findForbiddenUserFacingPhrases } from "@/lib/meshGraphCopy";
import {
  LIMITED_TOPOLOGY_SEARCH_NOTE,
  MAX_DEVICE_SEARCH_RESULTS,
  SEARCH_RANK,
  searchDevices,
} from "@/lib/meshGraphSearch";

function makeDevice(overrides: Partial<MeshEvidenceDevice>): MeshEvidenceDevice {
  return {
    ieee_address: "0x0000000000000001",
    network_id: "home",
    friendly_name: "Device",
    role: "end_device",
    power: "mains",
    availability: "online",
    manufacturer: null,
    model: null,
    in_inventory: true,
    in_latest_snapshot: true,
    health_bucket: "healthy",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "Observed in the latest topology snapshot.",
    passive_observation_summary: "",
    open_issue: null,
    diagnostic_stats: [],
    ...overrides,
  };
}

function makeEdge(overrides: Partial<MeshEvidenceEdge>): MeshEvidenceEdge {
  return {
    id: "edge-1",
    network_id: "home",
    source: "0x0000000000000001",
    target: "0x0000000000000002",
    evidence_class: "latest_snapshot_neighbor",
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    limitations: [],
    suggested_investigation: [],
    ...overrides,
  };
}

describe("searchDevices", () => {
  it("returns nothing for an empty or whitespace query", () => {
    const devices = [makeDevice({ friendly_name: "Laundry Plug" })];
    expect(searchDevices("", devices, [])).toEqual([]);
    expect(searchDevices("   ", devices, [])).toEqual([]);
  });

  it("includes all known devices, not just latest-snapshot devices", () => {
    const devices = [
      makeDevice({
        ieee_address: "0xaaa",
        friendly_name: "Inventory Only Sensor",
        in_latest_snapshot: false,
      }),
      makeDevice({
        ieee_address: "0xbbb",
        friendly_name: "Topology Only Placeholder",
        in_inventory: false,
        in_latest_snapshot: true,
      }),
      makeDevice({ ieee_address: "0xccc", friendly_name: "Snapshot Sensor" }),
    ];
    const names = searchDevices("sensor", devices, []).map((r) => r.device.friendly_name);
    expect(names).toContain("Inventory Only Sensor");
    expect(names).toContain("Snapshot Sensor");
    const placeholder = searchDevices("placeholder", devices, []);
    expect(placeholder).toHaveLength(1);
    expect(placeholder[0].device.friendly_name).toBe("Topology Only Placeholder");
  });

  it("ranks exact name above prefix above substring", () => {
    const devices = [
      makeDevice({ ieee_address: "0x1", friendly_name: "Back Laundry Light" }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Laundry" }),
      makeDevice({ ieee_address: "0x3", friendly_name: "Laundry Plug" }),
    ];
    const results = searchDevices("laundry", devices, []);
    expect(results.map((r) => r.device.friendly_name)).toEqual([
      "Laundry",
      "Laundry Plug",
      "Back Laundry Light",
    ]);
    expect(results[0].rank).toBe(SEARCH_RANK.exactName);
    expect(results[1].rank).toBe(SEARCH_RANK.namePrefix);
    expect(results[2].rank).toBe(SEARCH_RANK.nameSubstring);
  });

  it("matches IEEE addresses with or without the 0x prefix", () => {
    const devices = [
      makeDevice({ ieee_address: "0x00158d0001abcdef", friendly_name: "Kitchen Sensor" }),
      makeDevice({ ieee_address: "0xffeeddccbbaa0099", friendly_name: "Hall Router" }),
    ];
    expect(searchDevices("0x00158d", devices, [])[0].device.friendly_name).toBe(
      "Kitchen Sensor",
    );
    expect(searchDevices("00158d", devices, [])[0].device.friendly_name).toBe(
      "Kitchen Sensor",
    );
    expect(searchDevices("0x00158d", devices, [])[0].rank).toBe(SEARCH_RANK.ieee);
  });

  it("matches manufacturer and model when available", () => {
    const devices = [
      makeDevice({
        ieee_address: "0x1",
        friendly_name: "Office Blind",
        manufacturer: "IKEA",
        model: "FYRTUR",
      }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Kitchen Plug" }),
    ];
    const byManufacturer = searchDevices("ikea", devices, []);
    expect(byManufacturer).toHaveLength(1);
    expect(byManufacturer[0].device.friendly_name).toBe("Office Blind");
    expect(byManufacturer[0].rank).toBe(SEARCH_RANK.manufacturerModel);
    expect(searchDevices("fyrtur", devices, [])).toHaveLength(1);
  });

  it("matches status terms: unavailable, needs attention, limited topology", () => {
    const devices = [
      makeDevice({
        ieee_address: "0x1",
        friendly_name: "Garage Sensor",
        availability: "offline",
        flags: ["unavailable"],
      }),
      makeDevice({
        ieee_address: "0x2",
        friendly_name: "Hall Bulb",
        health_bucket: "needs_attention",
        flags: ["needs_attention"],
      }),
      makeDevice({
        ieee_address: "0x3",
        friendly_name: "Patio Plug",
        in_latest_snapshot: false,
      }),
      makeDevice({ ieee_address: "0x4", friendly_name: "Healthy Lamp" }),
    ];
    expect(searchDevices("unavailable", devices, []).map((r) => r.device.ieee_address)).toEqual([
      "0x1",
    ]);
    expect(
      searchDevices("needs attention", devices, []).map((r) => r.device.ieee_address),
    ).toEqual(["0x2"]);
    expect(
      searchDevices("limited topology", devices, []).map((r) => r.device.ieee_address),
    ).toEqual(["0x3"]);
  });

  it("prefers needs-attention, then unavailable, then latest topology within a rank", () => {
    const devices = [
      makeDevice({ ieee_address: "0x4", friendly_name: "Router D" }),
      makeDevice({
        ieee_address: "0x3",
        friendly_name: "Router C",
        in_latest_snapshot: false,
      }),
      makeDevice({
        ieee_address: "0x2",
        friendly_name: "Router B",
        availability: "offline",
        flags: ["unavailable"],
      }),
      makeDevice({
        ieee_address: "0x1",
        friendly_name: "Router A",
        health_bucket: "needs_attention",
        flags: ["needs_attention"],
      }),
    ];
    const results = searchDevices("router", devices, []);
    expect(results.map((r) => r.device.friendly_name)).toEqual([
      "Router A",
      "Router B",
      "Router D",
      "Router C",
    ]);
  });

  it("is deterministic regardless of device input order", () => {
    const devices = [
      makeDevice({ ieee_address: "0x1", friendly_name: "Motion One" }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Motion Two" }),
      makeDevice({ ieee_address: "0x3", friendly_name: "Motion Three" }),
    ];
    const forward = searchDevices("motion", devices, []).map((r) => r.device.ieee_address);
    const reversed = searchDevices("motion", [...devices].reverse(), []).map(
      (r) => r.device.ieee_address,
    );
    expect(forward).toEqual(reversed);
  });

  it("caps the number of results deterministically", () => {
    const devices = Array.from({ length: 30 }, (_, i) =>
      makeDevice({
        ieee_address: `0x${String(i).padStart(3, "0")}`,
        friendly_name: `Motion Sensor ${String(i).padStart(2, "0")}`,
      }),
    );
    const results = searchDevices("motion", devices, []);
    expect(results).toHaveLength(MAX_DEVICE_SEARCH_RESULTS);
    expect(results[0].device.friendly_name).toBe("Motion Sensor 00");
  });

  it("adds evidence badges from recent missing and suggested investigation links", () => {
    const devices = [
      makeDevice({ ieee_address: "0x1", friendly_name: "Bathroom Sensor" }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Bathroom Fan" }),
    ];
    const edges = [
      makeEdge({
        id: "hist-1",
        evidence_class: "historical_neighbor",
        source: "0x1",
        target: "0x9",
        in_latest_snapshot: false,
      }),
      makeEdge({
        id: "hint-1",
        evidence_class: "passive_derived_association",
        source: "0x2",
        target: "0x9",
        in_latest_snapshot: false,
      }),
    ];
    const results = searchDevices("bathroom", devices, edges);
    const sensor = results.find((r) => r.device.ieee_address === "0x1");
    const fan = results.find((r) => r.device.ieee_address === "0x2");
    expect(sensor?.badges).toContain("Recent missing evidence");
    expect(fan?.badges).toContain("Suggested investigation link");
  });

  it("explains limited topology evidence honestly for known devices", () => {
    const devices = [
      makeDevice({
        ieee_address: "0x1",
        friendly_name: "Cupboard Sensor",
        in_latest_snapshot: false,
      }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Cupboard Light" }),
    ];
    const results = searchDevices("cupboard", devices, []);
    const limited = results.find((r) => r.device.ieee_address === "0x1");
    const present = results.find((r) => r.device.ieee_address === "0x2");
    expect(limited?.limitedTopologyNote).toBe(LIMITED_TOPOLOGY_SEARCH_NOTE);
    expect(limited?.badges).toContain("Limited topology evidence");
    expect(present?.limitedTopologyNote).toBeNull();
    expect(findForbiddenUserFacingPhrases(LIMITED_TOPOLOGY_SEARCH_NOTE)).toEqual([]);
  });

  it("uses role badges instead of raw graph terms", () => {
    const devices = [
      makeDevice({ ieee_address: "0x1", friendly_name: "Hub", role: "coordinator" }),
      makeDevice({ ieee_address: "0x2", friendly_name: "Hall Repeater", role: "router" }),
      makeDevice({ ieee_address: "0x3", friendly_name: "Door Sensor", role: "end_device" }),
    ];
    expect(searchDevices("hub", devices, [])[0].badges).toContain("Coordinator");
    expect(searchDevices("repeater", devices, [])[0].badges).toContain("Router");
    expect(searchDevices("door", devices, [])[0].badges).toContain("End device");
    for (const result of searchDevices("e", devices, [])) {
      for (const badge of result.badges) {
        expect(findForbiddenUserFacingPhrases(badge)).toEqual([]);
      }
    }
  });
});
