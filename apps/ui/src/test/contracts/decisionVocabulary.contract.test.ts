import { describe, expect, it } from "vitest";
import {
  COVERAGE_LABEL_CODES,
  HEADLINE_CODES,
  REASON_CODES,
  coverageLabel,
  decisionStatusLabel,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import { allOracleScenarios } from "@/test/contracts/oracleFixture";

describe("decision vocabulary contract (UI mappings)", () => {
  it("maps every oracle-emitted code to non-empty presentation", () => {
    const headlines = new Set<string>();
    const reasons = new Set<string>();
    const limitations = new Set<string>();
    const checks = new Set<string>();
    const labels = new Set<string>();

    for (const [, scenario] of allOracleScenarios()) {
      for (const story of Object.values(scenario.device_stories)) {
        headlines.add(story.headline_code);
        for (const reason of story.reasons) reasons.add(reason.code);
        for (const limitation of story.limitations) limitations.add(limitation.code);
        for (const check of story.suggested_checks) checks.add(check.code);
        for (const item of story.coverage) labels.add(item.label_code);

        const status = decisionStatusLabel(story.status);
        expect(status.trim().length).toBeGreaterThan(0);
        expect(status.toLowerCase()).not.toBe("healthy");

        const headline = headlineText(story.headline_code);
        expect(headline.trim().length).toBeGreaterThan(0);

        for (const reason of story.reasons) {
          expect(reasonText(reason.code, reason.params ?? {}).trim().length).toBeGreaterThan(
            0,
          );
        }
        for (const limitation of story.limitations) {
          expect(
            limitationText(limitation.code, limitation.params ?? {}).trim().length,
          ).toBeGreaterThan(0);
        }
        for (const check of story.suggested_checks) {
          expect(
            suggestedCheckText(check.code, check.params ?? {}).trim().length,
          ).toBeGreaterThan(0);
        }
        for (const item of story.coverage) {
          expect(coverageLabel(item.label_code, item.params ?? {}).trim().length).toBeGreaterThan(
            0,
          );
        }
      }
    }

    for (const code of headlines) {
      expect((HEADLINE_CODES as readonly string[]).includes(code), code).toBe(true);
    }
    for (const code of reasons) {
      expect((REASON_CODES as readonly string[]).includes(code), code).toBe(true);
    }
    for (const code of labels) {
      expect((COVERAGE_LABEL_CODES as readonly string[]).includes(code), code).toBe(true);
    }
    expect(limitations.size).toBeGreaterThan(0);
    expect(checks.size).toBeGreaterThanOrEqual(0);
  });
});
