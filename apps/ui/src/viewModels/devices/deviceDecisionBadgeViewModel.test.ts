import { describe, expect, it } from "vitest";
import type { DeviceDecisionBadge } from "@zigbeelens/shared";
import { buildDeviceDecisionBadgeViewModel } from "./deviceDecisionBadgeViewModel";
import {
  decisionStatusCompactLabel,
  decisionStatusLabel,
  decisionStatusTone,
  headlineText,
} from "@/viewModels/decisionCopy";

function makeBadge(overrides: Partial<DeviceDecisionBadge> = {}): DeviceDecisionBadge {
  return {
    status: "review_first",
    priority: "high",
    headline_code: "current_issue_present",
    coverage_label_codes: ["availability_tracking_off"],
    ...overrides,
  };
}

describe("deviceDecisionBadgeViewModel", () => {
  it("maps status through shared decision copy helpers", () => {
    const vm = buildDeviceDecisionBadgeViewModel(makeBadge());
    expect(vm.statusLabel).toBe(decisionStatusLabel("review_first"));
    expect(vm.compactLabel).toBe(decisionStatusCompactLabel("review_first"));
    expect(vm.tone).toBe(decisionStatusTone("review_first"));
    expect(vm.statusLabel).toBe("Review first");
    expect(vm.compactLabel).toBe("Review first");
    expect(vm.tone).toBe("action");
  });

  it("maps headline through shared headline copy", () => {
    const vm = buildDeviceDecisionBadgeViewModel(makeBadge());
    expect(vm.headline).toBe(headlineText("current_issue_present"));
    expect(vm.headline).toBe("Current issue needs attention");
  });

  it("maps coverage label codes without exposing raw codes as primary labels", () => {
    const vm = buildDeviceDecisionBadgeViewModel(makeBadge());
    expect(vm.coverageLabels).toEqual(["Availability tracking off"]);
    expect(JSON.stringify(vm)).not.toContain("availability_tracking_off");
    expect(JSON.stringify(vm)).not.toContain("review_first");
    expect(JSON.stringify(vm)).not.toContain("current_issue_present");
  });

  it("fails safely for unknown status and headline codes", () => {
    const vm = buildDeviceDecisionBadgeViewModel(
      makeBadge({
        status: "future_status_v2",
        headline_code: "future_headline_v2",
        coverage_label_codes: ["future_coverage_v2"],
      }),
    );
    expect(vm.statusLabel).toBe("Status unknown");
    expect(vm.compactLabel).toBe("Unknown");
    expect(vm.tone).toBe("muted");
    expect(vm.headline).toBe("Device story summary unavailable.");
    expect(vm.coverageLabels).toEqual(["Coverage status unknown"]);
    expect(JSON.stringify(vm)).not.toContain("future_status_v2");
    expect(JSON.stringify(vm)).not.toContain("future_headline_v2");
    expect(JSON.stringify(vm)).not.toContain("future_coverage_v2");
  });
});
