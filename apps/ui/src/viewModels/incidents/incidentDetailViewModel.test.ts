import { describe, expect, it } from "vitest";
import type { Incident } from "@zigbeelens/shared";
import {
  decisionStatusLabel,
  headlineText,
} from "@/viewModels/decisionCopy";
import { buildIncidentDetailViewModel } from "./incidentDetailViewModel";

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    type: "single_device_unavailable",
    status: "resolved",
    severity: "incident",
    scope: "device",
    confidence: "medium",
    title: "Kitchen Plug unavailable",
    summary: "Kitchen Plug stopped reporting on Monday.",
    interpretation: "Legacy interpretation that differs from summary.",
    network_ids: ["home"],
    affected_device_count: 1,
    affected_devices: [
      {
        network_id: "home",
        ieee_address: "0xa1",
        friendly_name: "Kitchen Plug",
        decision: {
          status: "no_notable_change",
          priority: "none",
          headline_code: "no_notable_signals",
          coverage_label_codes: [],
        },
      },
    ],
    opened_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
    resolved_at: "2026-07-12T12:00:00Z",
    evidence: [{ id: "e1", kind: "stored", summary: "Was offline" }],
    counter_evidence: [{ id: "c1", kind: "stored", summary: "Bridge stayed online" }],
    limitations: [{ id: "l1", summary: "No topology" }],
    timeline: [
      {
        id: "t1",
        timestamp: "2026-07-11T00:00:00Z",
        kind: "incident_opened",
        severity: "incident",
        title: "Opened",
        summary: "Incident opened",
        incident_id: "inc-1",
      },
    ],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      summary: "Kitchen Plug stopped reporting on Monday.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

describe("incidentDetailViewModel", () => {
  it("keeps recorded summary and historical interpretation separate", () => {
    const vm = buildIncidentDetailViewModel(makeIncident());
    expect(vm.record.recordSummary).toBe("Kitchen Plug stopped reporting on Monday.");
    expect(vm.recordedInterpretation).toBe(
      "Legacy interpretation that differs from summary.",
    );
  });

  it("maps current device decisions through shared copy", () => {
    const vm = buildIncidentDetailViewModel(makeIncident());
    expect(vm.currentDeviceDecisions).toHaveLength(1);
    expect(vm.currentDeviceDecisions[0]?.decision.statusLabel).toBe(
      decisionStatusLabel("no_notable_change"),
    );
    expect(vm.currentDeviceDecisions[0]?.decision.headline).toBe(
      headlineText("no_notable_signals"),
    );
  });

  it("builds a record-oriented snippet without raw decision codes", () => {
    const vm = buildIncidentDetailViewModel(makeIncident());
    expect(vm.snippet).toContain("# Kitchen Plug unavailable");
    expect(vm.snippet).toContain("## Recorded summary");
    expect(vm.snippet).toContain("## Current device decisions");
    expect(vm.snippet).toContain(decisionStatusLabel("no_notable_change"));
    expect(vm.snippet).not.toContain("no_notable_change");
    expect(vm.snippet).not.toContain("## Interpretation");
    expect(vm.snippet).not.toContain("What ZigbeeLens thinks");
    expect(vm.snippet).toContain("## Stored evidence");
    expect(vm.snippet).toContain("Was offline");
  });

  it("omits duplicated recorded interpretation when identical to summary", () => {
    const vm = buildIncidentDetailViewModel(
      makeIncident({ interpretation: "Kitchen Plug stopped reporting on Monday." }),
    );
    expect(vm.recordedInterpretation).toBeNull();
  });

  it("preserves stored evidence collections and timeline", () => {
    const vm = buildIncidentDetailViewModel(makeIncident());
    expect(vm.evidence).toHaveLength(1);
    expect(vm.counterEvidence).toHaveLength(1);
    expect(vm.limitations).toHaveLength(1);
    expect(vm.timeline).toHaveLength(1);
    expect(vm.record.lifecycle).toBe("resolved");
    expect(vm.record.resolvedExact).toBeTruthy();
  });
});
