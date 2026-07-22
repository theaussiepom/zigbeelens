import { describe, expect, it } from "vitest";
import {
  COVERAGE_LABEL_CODES,
  HEADLINE_CODES,
  LIMITATION_CODES,
  REASON_CODES,
  SUGGESTED_CHECK_CODES,
  coverageLabel,
  decisionStatusLabel,
  decisionStatusTone,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import { DEVICE_DECISION_SORT_ORDER } from "@/viewModels/devices/deviceRowViewModel";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

describe("decision vocabulary contract (UI ↔ Core manifest)", () => {
  const vocab = oracleFixture.vocabulary;

  it("matches Core vocabulary manifest exactly", () => {
    expect([...HEADLINE_CODES].sort()).toEqual(vocab.headline_codes);
    expect([...REASON_CODES].sort()).toEqual(vocab.reason_codes);
    expect([...LIMITATION_CODES].sort()).toEqual(vocab.limitation_codes);
    expect([...SUGGESTED_CHECK_CODES].sort()).toEqual(vocab.suggested_check_codes);
    expect([...COVERAGE_LABEL_CODES].sort()).toEqual(vocab.coverage_label_codes);
    expect([...vocab.decision_statuses].sort()).toEqual(vocab.decision_statuses);
    expect(DEVICE_DECISION_SORT_ORDER.slice().sort()).toEqual(
      vocab.decision_statuses.slice().sort(),
    );
  });

  it("maps every manifest code to non-empty safe presentation", () => {
    for (const status of vocab.decision_statuses) {
      const label = decisionStatusLabel(status);
      expect(label.trim().length).toBeGreaterThan(0);
      expect(label.toLowerCase()).not.toBe("healthy");
      expect(decisionStatusTone(status)).toBeTruthy();
    }
    for (const code of vocab.headline_codes) {
      expect(headlineText(code).trim().length).toBeGreaterThan(0);
    }
    for (const code of vocab.reason_codes) {
      expect(reasonText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of vocab.limitation_codes) {
      expect(limitationText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of vocab.suggested_check_codes) {
      expect(suggestedCheckText(code, {}).trim().length).toBeGreaterThan(0);
    }
    for (const code of vocab.coverage_label_codes) {
      expect(coverageLabel(code, {}).trim().length).toBeGreaterThan(0);
    }
  });
});
