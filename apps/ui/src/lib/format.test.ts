import { describe, expect, it } from "vitest";
import type { DeviceSummary, Incident, RouterRisk } from "@zigbeelens/shared";
import {
  bridgeStateLabel,
  bridgeStateSeverity,
  compareDevices,
  compareIncidents,
  compareRouterRisks,
  lifecycleSeverity,
  relativeTime,
  scopeLabel,
  severityLabel,
  severityRank,
} from "./format";

function device(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0x01",
    friendly_name: "Device",
    device_type: "EndDevice",
    power_source: "Battery",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    decision: {
      status: "no_notable_change",
      priority: "none",
      headline_code: "device_no_notable_change",
      coverage_label_codes: [],
    },
    ...overrides,
  };
}

describe("bridge state presentation", () => {
  it("maps online/offline/unknown to honest labels and tones", () => {
    expect(bridgeStateLabel("online")).toBe("Online");
    expect(bridgeStateSeverity("online")).toBe("healthy");
    expect(bridgeStateLabel("offline")).toBe("Offline");
    expect(bridgeStateSeverity("offline")).toBe("critical");
    expect(bridgeStateLabel("unknown")).toBe("No bridge signal");
    expect(bridgeStateSeverity("unknown")).toBe("watch");
  });
});

describe("severity helpers", () => {
  it("ranks worse severities lower", () => {
    expect(severityRank("critical")).toBeLessThan(severityRank("incident"));
    expect(severityRank("incident")).toBeLessThan(severityRank("watch"));
    expect(severityRank("watch")).toBeLessThan(severityRank("healthy"));
  });

  it("uses calm overall labels", () => {
    expect(severityLabel("healthy")).toBe("OK");
    expect(severityLabel("incident")).toBe("Incident");
  });
});

describe("compareDevices bad-first ordering", () => {
  it("puts incident-affected devices first", () => {
    const list = [
      device({ friendly_name: "healthy" }),
      device({ friendly_name: "in-incident", incident_affected: true }),
    ];
    const sorted = [...list].sort(compareDevices);
    expect(sorted[0].friendly_name).toBe("in-incident");
  });

  it("orders by decision status when incident state is equal", () => {
    const list = [
      device({
        friendly_name: "ok",
        decision: {
          status: "no_notable_change",
          priority: "none",
          headline_code: "device_no_notable_change",
          coverage_label_codes: [],
        },
      }),
      device({
        friendly_name: "offline",
        decision: {
          status: "review_first",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: [],
        },
      }),
    ];
    const sorted = [...list].sort(compareDevices);
    expect(sorted[0].friendly_name).toBe("offline");
  });
});

describe("compareIncidents", () => {
  function incident(overrides: Partial<Incident>): Incident {
    return {
      id: "i",
      type: "single_device_unavailable",
      status: "open",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      title: "t",
      summary: "s",
      interpretation: "",
      network_ids: ["home"],
      affected_device_count: 1,
      affected_devices: [],
      opened_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      resolved_at: null,
      evidence: [],
      counter_evidence: [],
      limitations: [],
      timeline: [],
      conclusion: {
        classification: "x",
        severity: "incident",
        scope: "device",
        confidence: "medium",
        summary: "",
        evidence: [],
        counter_evidence: [],
        limitations: [],
      },
      ...overrides,
    };
  }

  it("sorts open incidents before resolved", () => {
    const list = [
      incident({
        id: "resolved",
        status: "resolved",
        resolved_at: "2026-01-02T00:00:00Z",
      }),
      incident({ id: "open", status: "open" }),
      incident({ id: "watching", status: "watching" }),
    ];
    const sorted = [...list].sort(compareIncidents);
    expect(sorted.map((i) => i.id)).toEqual(["open", "watching", "resolved"]);
  });
});

describe("compareRouterRisks", () => {
  function router(overrides: Partial<RouterRisk>): RouterRisk {
    return {
      network_id: "home",
      ieee_address: "0x0a",
      friendly_name: "r",
      availability: "online",
      correlated_affected_devices: 0,
      risk: {
        classification: "router_risk",
        severity: "watch",
        scope: "router_candidate",
        confidence: "low",
        summary: "",
        evidence: [],
        counter_evidence: [],
        limitations: [],
      },
      ...overrides,
    };
  }

  it("puts offline routers first", () => {
    const list = [
      router({ friendly_name: "online" }),
      router({ friendly_name: "offline", availability: "offline" }),
    ];
    const sorted = [...list].sort(compareRouterRisks);
    expect(sorted[0].friendly_name).toBe("offline");
  });
});

describe("lifecycleSeverity", () => {
  it("maps lifecycle to calm severities", () => {
    expect(lifecycleSeverity("open")).toBe("incident");
    expect(lifecycleSeverity("watching")).toBe("watch");
    expect(lifecycleSeverity("resolved")).toBe("healthy");
  });
});

describe("relativeTime", () => {
  it("returns a dash for missing input", () => {
    expect(relativeTime(undefined)).toBe("—");
  });
  it("formats recent timestamps as minutes ago", () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(relativeTime(fiveMinAgo)).toMatch(/m ago/);
  });
});

describe("scopeLabel", () => {
  it("humanizes scopes", () => {
    expect(scopeLabel("multi_network")).toBe("Multiple networks");
    expect(scopeLabel("device")).toBe("Single device");
  });
});
