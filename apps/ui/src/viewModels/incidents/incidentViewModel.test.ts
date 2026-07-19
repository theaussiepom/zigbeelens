import { describe, expect, it } from "vitest";
import type { Incident, IncidentDeviceRef } from "@zigbeelens/shared";
import {
  decisionStatusLabel,
  headlineText,
} from "@/viewModels/decisionCopy";
import {
  buildCurrentDecisionSummary,
  buildIncidentDeviceDecisionViewModel,
  buildIncidentRecordViewModel,
  compareIncidentsByRecordTiming,
} from "./incidentViewModel";

function makeRef(overrides: Partial<IncidentDeviceRef> = {}): IncidentDeviceRef {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    decision: {
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: [],
    },
    ...overrides,
  };
}

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    type: "single_device_unavailable",
    status: "open",
    severity: "incident",
    scope: "device",
    confidence: "medium",
    title: "Kitchen Plug unavailable",
    summary: "Kitchen Plug stopped reporting.",
    interpretation: "Legacy interpretation text",
    network_ids: ["home"],
    affected_device_count: 1,
    affected_devices: [makeRef()],
    opened_at: "2026-07-13T00:00:00Z",
    updated_at: "2026-07-13T01:00:00Z",
    evidence: [{ id: "e1", kind: "stored", summary: "Offline evidence" }],
    counter_evidence: [],
    limitations: [{ id: "l1", summary: "No topology" }],
    timeline: [],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      summary: "Kitchen Plug stopped reporting.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

describe("incidentViewModel", () => {
  it("keeps lifecycle as primary record status and preserves summary", () => {
    const vm = buildIncidentRecordViewModel(makeIncident());
    expect(vm.lifecycle).toBe("open");
    expect(vm.lifecycleLabel).toBeTruthy();
    expect(vm.title).toBe("Kitchen Plug unavailable");
    expect(vm.recordSummary).toBe("Kitchen Plug stopped reporting.");
    expect(vm.href).toBe("/incidents/inc-1");
  });

  it("maps current decisions through shared decision copy", () => {
    const item = buildIncidentDeviceDecisionViewModel(makeRef());
    expect(item.decision.statusLabel).toBe(decisionStatusLabel("review_first"));
    expect(item.decision.headline).toBe(headlineText("current_issue_present"));
    expect(item.deviceHref).toContain("/devices/home/");
    expect(item.decisionStatus).toBe("review_first");
  });

  it("does not use health/lens for decision presentation", () => {
    const item = buildIncidentDeviceDecisionViewModel(
      makeRef({
        decision: {
          status: "watch",
          priority: "low",
          headline_code: "stale_last_seen",
          coverage_label_codes: [],
        },
      }),
    );
    expect(item.decision.statusLabel).toBe(decisionStatusLabel("watch"));
    expect(item.decision.headline).not.toContain("lens");
  });

  it("uses safe unknown for null decision and unknown future codes", () => {
    const missing = buildIncidentDeviceDecisionViewModel(makeRef({ decision: null }));
    expect(missing.decision.statusLabel).toBe("Status unknown");
    expect(missing.decision.headline).toBe("Device story summary unavailable.");
    expect(missing.decisionStatus).toBeNull();

    const future = buildIncidentDeviceDecisionViewModel(
      makeRef({
        decision: {
          status: "future_status_v2",
          priority: "high",
          headline_code: "future_headline_v2",
          coverage_label_codes: ["future_coverage_v2"],
        },
      }),
    );
    expect(future.decision.statusLabel).toBe("Status unknown");
    expect(future.decision.headline).toBe("Device story summary unavailable.");
    expect(future.decision.statusLabel).not.toContain("future_status_v2");
    expect(future.decision.headline).not.toContain("future_headline_v2");
  });

  it("builds accurate current decision summaries", () => {
    const a = buildIncidentDeviceDecisionViewModel(makeRef());
    const b = buildIncidentDeviceDecisionViewModel(
      makeRef({
        ieee_address: "0xa2",
        decision: {
          status: "worth_reviewing",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: [],
        },
      }),
    );
    const c = buildIncidentDeviceDecisionViewModel(
      makeRef({ ieee_address: "0xa3", decision: null }),
    );
    expect(buildCurrentDecisionSummary([a, b, a])).toContain("Review first");
    expect(buildCurrentDecisionSummary([a, b, a])).toContain("Worth reviewing");
    expect(buildCurrentDecisionSummary([])).toBeNull();
    expect(buildCurrentDecisionSummary([c, c])).toBe(
      "Current device decisions unavailable",
    );
  });

  it("keeps recorded severity/confidence as metadata labels", () => {
    const vm = buildIncidentRecordViewModel(makeIncident());
    expect(vm.recordedSeverityLabel).toBeTruthy();
    expect(vm.recordedConfidenceLabel).toBeTruthy();
    expect(vm.openedExact).toBeTruthy();
    expect(vm.updatedLabel).toBeTruthy();
  });

  it("sorts by lifecycle then updated/id desc without severity", () => {
    const older = makeIncident({
      id: "a",
      status: "open",
      severity: "critical",
      updated_at: "2026-07-13T00:00:00Z",
      opened_at: "2026-07-12T00:00:00Z",
    });
    const newer = makeIncident({
      id: "b",
      status: "open",
      severity: "watch",
      updated_at: "2026-07-13T02:00:00Z",
      opened_at: "2026-07-12T00:00:00Z",
    });
    const watching = makeIncident({ id: "c", status: "watching" });
    const sorted = [watching, older, newer].sort(compareIncidentsByRecordTiming);
    expect(sorted.map((i) => i.id)).toEqual(["b", "a", "c"]);
  });
});
