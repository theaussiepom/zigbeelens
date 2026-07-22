/**
 * Narrow source scan for suspicious ?? 0 / || 0 in primary presenters.
 * Not a repository-wide ban — each match is classified.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

type Classification =
  | "factual measured default"
  | "safe rendering fallback"
  | "advanced/debug only";

const PRIMARY_FILES: Array<{
  file: string;
  allowed: Array<{ pattern: RegExp; classification: Classification; note: string }>;
}> = [
  {
    file: "apps/ui/src/viewModels/reports/reportDecisionViewModel.ts",
    allowed: [
      {
        pattern: /statusCounts\[status\] \?\? 0/,
        classification: "factual measured default",
        note: "Missing status key in count map is measured absence → 0 count",
      },
      {
        pattern: /count \?\? 0/,
        classification: "factual measured default",
        note: "Priority count fold over known keys",
      },
    ],
  },
  {
    file: "apps/ui/src/viewModels/topology/topologyLandingSnapshotViewModel.ts",
    allowed: [
      {
        pattern: /router_count \?\? 0/,
        classification: "factual measured default",
        note: "Snapshot counters are measured topology counts",
      },
      {
        pattern: /link_count \?\? 0/,
        classification: "factual measured default",
        note: "Snapshot counters are measured topology counts",
      },
    ],
  },
  {
    file: "apps/ui/src/lib/topologyStats.ts",
    allowed: [
      {
        pattern: /\?\? 0/,
        classification: "factual measured default",
        note: "Empty-snapshot detection uses measured zero counters",
      },
    ],
  },
  {
    file: "apps/ui/src/pages/OverviewPage.tsx",
    allowed: [
      {
        pattern: /status_counts\.review_first \?\? 0/,
        classification: "factual measured default",
        note: "DecisionCountSummary missing key means zero subjects in that status",
      },
      {
        pattern: /status_counts\.worth_reviewing \?\? 0/,
        classification: "factual measured default",
        note: "DecisionCountSummary missing key means zero subjects in that status",
      },
    ],
  },
];

describe("unknown-zero source classifications", () => {
  it("classifies every ?? 0 / || 0 in listed primary presenters", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    for (const entry of PRIMARY_FILES) {
      const text = readFileSync(path.join(repoRoot, entry.file), "utf8");
      const matches = text.match(/(\?\?|\|\|) 0/g) ?? [];
      expect(matches.length, entry.file).toBeGreaterThan(0);
      for (const line of text.split("\n")) {
        if (!/(\?\?|\|\|) 0/.test(line)) continue;
        const allowed = entry.allowed.some((rule) => rule.pattern.test(line));
        expect(allowed, `${entry.file}: unclassified: ${line.trim()}`).toBe(true);
      }
    }
  });
});
