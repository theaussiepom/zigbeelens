import { describe, expect, it } from "vitest";
import type { ModelPatternSummary } from "@zigbeelens/shared";
import {
  MODEL_PATTERN_LIMITATION,
  MODEL_PATTERN_TITLE,
  buildModelPatternViewModel,
} from "@/viewModels/overview/modelPatternViewModel";

const FORBIDDEN_AFFIRMATIVE_PHRASES = [
  "defective model",
  "faulty model",
  "bad model",
  "unreliable model",
  "manufacturer fault",
  "manufacturer issue",
  "caused by the model",
  "model caused",
  "firmware caused",
  "known defect",
  "systemic defect",
  "product failure",
  "all devices affected",
];

function makePattern(
  overrides: Partial<ModelPatternSummary> = {},
): ModelPatternSummary {
  return {
    pattern_id: "model-pattern-test",
    network_id: "home",
    manufacturer: "IKEA",
    model: "TS011F",
    group_size: 5,
    affected_count: 3,
    lookback_days: 7,
    affected_device_ieees: ["0xm00", "0xm01", "0xm02"],
    latest_supporting_evidence_at: "2026-07-06T08:22:00+00:00",
    ...overrides,
  };
}

function claimText(vm: ReturnType<typeof buildModelPatternViewModel>): string {
  return JSON.stringify({
    title: vm.title,
    summary: vm.summary,
    identityLabel: vm.identityLabel,
    limitation: vm.limitation,
    suggestedChecks: vm.suggestedChecks,
  }).toLowerCase();
}

describe("modelPatternViewModel", () => {
  it("maps dashboard DTO fields to approved Overview copy", () => {
    const vm = buildModelPatternViewModel(makePattern(), "Home");
    expect(vm.title).toBe(MODEL_PATTERN_TITLE);
    expect(vm.summary).toBe(
      "3 of 5 devices with this model have gone offline in the last 7 days.",
    );
    expect(vm.identityLabel).toBe("IKEA · TS011F");
    expect(vm.limitation).toBe(MODEL_PATTERN_LIMITATION);
    expect(vm.meshHref).toBe("/topology/home");
    expect(vm.meshLinkLabel).toBe("Review Mesh evidence →");
  });

  it("uses model-only identity label when manufacturer is unknown", () => {
    const vm = buildModelPatternViewModel(makePattern({ manufacturer: null }), "Home");
    expect(vm.identityLabel).toBe("TS011F");
    expect(vm.identityLabel).not.toContain("None");
    expect(vm.identityLabel).not.toContain("undefined");
  });

  it("does not expose raw reason codes", () => {
    const vm = buildModelPatternViewModel(makePattern());
    expect(JSON.stringify(vm)).not.toContain("model_pattern_observed");
  });

  it("avoids manufacturer-blame affirmative claims", () => {
    const vm = buildModelPatternViewModel(makePattern());
    const text = claimText(vm);
    for (const phrase of FORBIDDEN_AFFIRMATIVE_PHRASES) {
      expect(text).not.toContain(phrase);
    }
    expect(text).toContain("does not prove the model is defective");
  });
});
