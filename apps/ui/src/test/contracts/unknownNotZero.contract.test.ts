import { describe, expect, it } from "vitest";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import type { DeviceStoryDto } from "@/types/devices";
import { allOracleScenarios } from "@/test/contracts/oracleFixture";

const FALSE_HEALTHY = [
  /\bhealthy\b/i,
  /\bcomplete\b/i,
  /\bno issue\b/i,
  /\bno links\b/i,
];

function looksLikeFalseZero(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed === "0" || trimmed === "0%") return true;
  return FALSE_HEALTHY.some((pattern) => pattern.test(trimmed));
}

describe("unknown never becomes zero/healthy (UI)", () => {
  it("ViewModels for data_unavailable / coverage gaps do not claim measured zero", () => {
    for (const [, scenario] of allOracleScenarios()) {
      for (const story of Object.values(scenario.device_stories) as DeviceStoryDto[]) {
        if (
          story.status !== "data_unavailable" &&
          story.status !== "improve_data_coverage" &&
          story.headline_code !== "data_coverage_gaps"
        ) {
          continue;
        }
        const vm = buildDeviceStoryViewModel(story);
        expect(looksLikeFalseZero(vm.headline)).toBe(false);
        for (const reason of vm.reasons) {
          expect(looksLikeFalseZero(reason)).toBe(false);
        }
        for (const item of vm.coverageItems) {
          expect(looksLikeFalseZero(item.label)).toBe(false);
          expect(item.label).not.toBe("0");
        }
      }
    }
  });

  it("nullable device metrics stay null in oracle fixtures", () => {
    for (const [, scenario] of allOracleScenarios()) {
      for (const device of scenario.devices) {
        for (const field of ["linkquality", "battery", "last_seen"] as const) {
          if (field in device && device[field] === null) {
            expect(device[field]).toBeNull();
          }
        }
      }
    }
  });
});
