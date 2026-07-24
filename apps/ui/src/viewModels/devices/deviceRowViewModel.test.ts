import { describe, expect, it } from "vitest";
import type { DeviceSummary } from "@zigbeelens/shared";
import {
  decisionStatusCompactLabel,
  decisionStatusLabel,
  decisionStatusTone,
} from "@/viewModels/decisionCopy";
import {
  buildDeviceInventoryRows,
  buildDeviceRowViewModel,
  compareDevicesByDecision,
  filterDeviceInventoryRows,
} from "./deviceRowViewModel";

function makeDevice(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    decision: { status: "no_notable_change", priority: "none", headline_code: "device_no_notable_change", coverage_label_codes: [] },
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-13T01:00:00Z",
    decision: {
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: ["availability_tracking_off"],
    },
    home_assistant_area_name: "Kitchen",
    ...overrides,
  };
}

describe("deviceRowViewModel", () => {
  it("maps decision badge through shared decision copy", () => {
    const row = buildDeviceRowViewModel(makeDevice());
    expect(row.decision.statusLabel).toBe(decisionStatusLabel("review_first"));
    expect(row.decision.compactLabel).toBe(decisionStatusCompactLabel("review_first"));
    expect(row.decision.tone).toBe(decisionStatusTone("review_first"));
  });

  it("uses Status unknown muted for unknown future status", () => {
    const row = buildDeviceRowViewModel(
      makeDevice({
        decision: {
          status: "future_status_v2",
          priority: "high",
          headline_code: "x",
          coverage_label_codes: [],
        },
      }),
    );
    expect(row.decision.statusLabel).toBe("Status unknown");
    expect(row.decision.compactLabel).toBe("Unknown");
    expect(row.decision.tone).toBe("muted");
  });

  it("does not expose raw unknown decision statuses", () => {
    const row = buildDeviceRowViewModel(
      makeDevice({
        decision: {
          status: "future_status_v2",
          priority: "high",
          headline_code: "future_headline_v2",
          coverage_label_codes: ["future_coverage_v2"],
        },
      }),
    );
    const json = JSON.stringify(row.decision);
    expect(row.decision.statusLabel).toBe("Status unknown");
    expect(row.decision.tone).toBe("muted");
    expect(json).not.toContain("future_status_v2");
    expect(json).not.toContain("future_headline_v2");
    expect(json).not.toContain("future_coverage_v2");
  });

  it("keeps availability labels factual", () => {
    expect(buildDeviceRowViewModel(makeDevice({ availability: "online" })).availabilityLabel).toBe(
      "Online",
    );
    expect(buildDeviceRowViewModel(makeDevice({ availability: "offline" })).availabilityLabel).toBe(
      "Offline",
    );
    expect(buildDeviceRowViewModel(makeDevice({ availability: "unknown" })).availabilityLabel).toBe(
      "No data",
    );
  });

  it("summarises limiting coverage compactly with +N more", () => {
    const one = buildDeviceRowViewModel(
      makeDevice({
        decision: {
          status: "improve_data_coverage",
          priority: "medium",
          headline_code: "data_coverage_gaps",
          coverage_label_codes: ["availability_tracking_off"],
        },
      }),
    );
    expect(one.coverageSummary).toBe("Availability tracking off");
    expect(one.hasCoverageLimitations).toBe(true);

    const many = buildDeviceRowViewModel(
      makeDevice({
        decision: {
          status: "improve_data_coverage",
          priority: "medium",
          headline_code: "data_coverage_gaps",
          coverage_label_codes: [
            "availability_tracking_off",
            "ha_areas_not_linked",
            "topology_history_sparse",
          ],
        },
      }),
    );
    expect(many.coverageSummary).toBe("Availability tracking off +2 more");
  });

  it("keeps battery and LQI numeric with dash fallbacks", () => {
    const row = buildDeviceRowViewModel(makeDevice());
    expect(row.batterySummary).toBe("Battery 62%");
    expect(row.lqiSummary).toBe("LQI 118");
    const missing = buildDeviceRowViewModel(
      makeDevice({ battery: undefined, linkquality: undefined }),
    );
    expect(missing.batterySummary).toBe("Battery —");
    expect(missing.lqiSummary).toBe("LQI —");
  });

  it("composes area and model without inferring area from friendly name", () => {
    const row = buildDeviceRowViewModel(makeDevice());
    expect(row.areaLabel).toBe("Kitchen");
    expect(row.modelLabel).toBe("IKEA · TS011F");

    const noArea = buildDeviceRowViewModel(
      makeDevice({
        friendly_name: "Laundry Sensor",
        home_assistant_area_name: null,
        manufacturer: null,
        model: "XYZ",
      }),
    );
    expect(noArea.areaLabel).toBeNull();
    expect(noArea.modelLabel).toBe("XYZ");
    expect(noArea.areaLabel).not.toBe("Laundry");

    const unknownModel = buildDeviceRowViewModel(
      makeDevice({
        manufacturer: null,
        model: null,
        home_assistant_area_name: null,
      }),
    );
    expect(unknownModel.modelLabel).toBe("Model unknown");

    const legacyAlias = buildDeviceRowViewModel(
      makeDevice({
        home_assistant_area_name: null,
        ha_area: "Legacy Kitchen",
      }),
    );
    expect(legacyAlias.areaLabel).toBe("Legacy Kitchen");
  });

  it("builds device and mesh hrefs from existing route helpers", () => {
    const row = buildDeviceRowViewModel(makeDevice());
    expect(row.deviceHref).toBe("/devices/home/0xa1");
    expect(row.meshHref).toBe("/investigate/home");
  });

  it("prefers the HA name while preserving and searching the Zigbee2MQTT name", () => {
    const row = buildDeviceRowViewModel(
      makeDevice({
        friendly_name: "z2m_kitchen_lamp",
        home_assistant_name: "Kitchen Lamp",
      }),
    );
    expect(row.name).toBe("Kitchen Lamp");
    expect(row.originalName).toBe("z2m_kitchen_lamp");
    expect(row.sourceNameLabel).toBe("Zigbee2MQTT: z2m_kitchen_lamp");
    expect(
      filterDeviceInventoryRows([row], {
        networkId: "",
        decisionStatus: "",
        availability: "",
        coverageFilter: "",
        search: "z2m_kitchen",
      }),
    ).toEqual([row]);

    const fallback = buildDeviceRowViewModel(
      makeDevice({
        friendly_name: "z2m_kitchen_lamp",
        home_assistant_name: "   ",
      }),
    );
    expect(fallback.name).toBe("z2m_kitchen_lamp");
    expect(fallback.sourceNameLabel).toBeNull();
  });

  it("sorts by decision priority then friendly name", () => {
    const rows = buildDeviceInventoryRows([
      makeDevice({
        ieee_address: "0xb",
        friendly_name: "Beta",
        decision: {
          status: "watch",
          priority: "medium",
          headline_code: "stale_last_seen",
          coverage_label_codes: [],
        },
      }),
      makeDevice({
        ieee_address: "0xa",
        friendly_name: "Alpha",
        decision: {
          status: "review_first",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: [],
        },
      }),
      makeDevice({
        ieee_address: "0xc",
        friendly_name: "Charlie",
        decision: {
          status: "no_notable_change",
          priority: "none",
          headline_code: "device_no_notable_change",
          coverage_label_codes: [],
        },
      }),
      makeDevice({
        ieee_address: "0xd",
        friendly_name: "Delta",
        decision: {
          status: "review_first",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: [],
        },
      }),
    ]);
    expect(rows.map((r) => r.name)).toEqual(["Alpha", "Delta", "Beta", "Charlie"]);
  });

  it("places unknown future statuses after known statuses", () => {
    const known = buildDeviceRowViewModel(
      makeDevice({
        friendly_name: "Known",
        decision: {
          status: "data_unavailable",
          priority: "none",
          headline_code: "no_notable_signals",
          coverage_label_codes: [],
        },
      }),
    );
    const unknown = buildDeviceRowViewModel(
      makeDevice({
        friendly_name: "Unknown",
        decision: {
          status: "future_status_v2",
          priority: "high",
          headline_code: "x",
          coverage_label_codes: [],
        },
      }),
    );
    expect(compareDevicesByDecision(known, unknown)).toBeLessThan(0);
  });

  it("filters by structured decision status and coverage, searching identity fields", () => {
    const rows = buildDeviceInventoryRows([
      makeDevice({
        ieee_address: "0xoff",
        friendly_name: "Office Plug",
        availability: "offline",
        manufacturer: "Philips",
        model: "Hue",
        home_assistant_area_name: "Office",
        decision: {
          status: "review_first",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: ["availability_tracking_off"],
        },
      }),
      makeDevice({
        ieee_address: "0xkit",
        friendly_name: "Kitchen Plug",
        availability: "online",
        decision: {
          status: "no_notable_change",
          priority: "none",
          headline_code: "no_notable_signals",
          coverage_label_codes: [],
        },
        home_assistant_area_name: "Kitchen",
      }),
    ]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "review_first",
        availability: "",
        coverageFilter: "",
        search: "",
      }).map((r) => r.name),
    ).toEqual(["Office Plug"]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "",
        availability: "online",
        coverageFilter: "",
        search: "",
      }).map((r) => r.name),
    ).toEqual(["Kitchen Plug"]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "",
        availability: "",
        coverageFilter: "limitations",
        search: "",
      }).map((r) => r.name),
    ).toEqual(["Office Plug"]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "",
        availability: "",
        coverageFilter: "",
        search: "0xoff",
      }).map((r) => r.name),
    ).toEqual(["Office Plug"]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "",
        availability: "",
        coverageFilter: "",
        search: "philips",
      }).map((r) => r.name),
    ).toEqual(["Office Plug"]);

    expect(
      filterDeviceInventoryRows(rows, {
        networkId: "",
        decisionStatus: "",
        availability: "",
        coverageFilter: "",
        search: "office",
      }).map((r) => r.name),
    ).toEqual(["Office Plug"]);
  });
});
