import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  coverageLabel,
  decisionStatusLabel,
  deviceCoverageLabel,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";

type ParityCase = {
  kind:
    | "status"
    | "headline"
    | "reason"
    | "limitation"
    | "suggested_check"
    | "coverage"
    | "device_coverage";
  code: string;
  params?: Record<string, unknown>;
  expected: string;
};

type ParityFixture = {
  cases: ParityCase[];
};

const fixturePath = path.resolve(
  import.meta.dirname,
  "../../../../packages/shared/decision-copy-parity.json",
);

const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as ParityFixture;

function renderCase(caseEntry: ParityCase): string {
  const params = caseEntry.params ?? {};
  switch (caseEntry.kind) {
    case "status":
      return decisionStatusLabel(caseEntry.code);
    case "headline":
      return headlineText(caseEntry.code);
    case "reason":
      return reasonText(caseEntry.code, params);
    case "limitation":
      return limitationText(caseEntry.code, params);
    case "suggested_check":
      return suggestedCheckText(caseEntry.code, params);
    case "coverage":
      return coverageLabel(caseEntry.code, params);
    case "device_coverage":
      return deviceCoverageLabel(caseEntry.code, params);
    default:
      throw new Error(`Unknown parity kind: ${caseEntry.kind}`);
  }
}

describe("decisionCopy parity fixture", () => {
  it.each(fixture.cases.map((caseEntry, index) => [index, caseEntry] as const))(
    "case %i (%s:%s)",
    (_index, caseEntry) => {
      expect(renderCase(caseEntry)).toBe(caseEntry.expected);
    },
  );
});
