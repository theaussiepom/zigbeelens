/**
 * Complete ?? 0 / || 0 classification across primary presentation roots.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

type Classification =
  | "factual measured default"
  | "safe rendering fallback"
  | "advanced/debug only";

type Entry = {
  file: string;
  pattern: RegExp;
  classification: Classification;
  note: string;
};

const CLASSIFICATIONS: Entry[] = [
  {
    file: "apps/ui/src/viewModels/reports/reportDecisionViewModel.ts",
    pattern: /statusCounts\[status\] \?\? 0/,
    classification: "factual measured default",
    note: "Missing status key means zero subjects in that status",
  },
  {
    file: "apps/ui/src/viewModels/reports/reportDecisionViewModel.ts",
    pattern: /const value = count \?\? 0/,
    classification: "factual measured default",
    note: "Unknown-status map entry uses measured count; nullish means zero",
  },
  {
    file: "apps/ui/src/viewModels/topology/topologyLandingSnapshotViewModel.ts",
    pattern: /router_count \?\? 0/,
    classification: "factual measured default",
    note: "Measured snapshot counter",
  },
  {
    file: "apps/ui/src/viewModels/topology/topologyLandingSnapshotViewModel.ts",
    pattern: /link_count \?\? 0/,
    classification: "factual measured default",
    note: "Measured snapshot counter",
  },
  {
    file: "apps/ui/src/viewModels/incidents/incidentViewModel.ts",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Count aggregation over known labels",
  },
  {
    file: "apps/ui/src/lib/topologyStats.ts",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Empty-snapshot detection uses measured counters",
  },
  {
    file: "apps/ui/src/lib/decisionContract.ts",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Count-map fold over known enum keys",
  },
  {
    file: "apps/ui/src/lib/meshEvidenceLive.ts",
    pattern: /\?\? 0/,
    classification: "advanced/debug only",
    note: "Mesh evidence aggregates / neighbor counts",
  },
  {
    file: "apps/ui/src/lib/meshGraphDense.ts",
    pattern: /\?\? 0/,
    classification: "advanced/debug only",
    note: "Graph degree counters",
  },
  {
    file: "apps/ui/src/lib/meshGraphSmartLayout.ts",
    pattern: /\?\? 0/,
    classification: "advanced/debug only",
    note: "Layout weight/degree counters",
  },
  {
    file: "apps/ui/src/components/cards.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "DecisionCountSummary missing key → measured zero",
  },
  {
    file: "apps/ui/src/components/reports/ContextualReportDialog.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Filter measured status counts",
  },
  {
    file: "apps/ui/src/components/meshGraph/TopologyMetricStrip.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Graph node length is a measured collection size",
  },
  {
    file: "apps/ui/src/pages/OverviewPage.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "DecisionCountSummary missing key → measured zero",
  },
  {
    file: "apps/ui/src/pages/NetworksPage.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "DecisionCountSummary / timeline length measured defaults",
  },
  {
    file: "apps/ui/src/pages/InvestigateLandingPage.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "DecisionCountSummary missing key → measured zero",
  },
  {
    file: "apps/ui/src/pages/SettingsPage.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Collector/enrichment measured counters",
  },
  {
    file: "apps/ui/src/pages/TopologyGraphPage.tsx",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Edge filter length is measured",
  },
  {
    file: "apps/ui/src/hooks/useTopologyGraphData.ts",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Collection emptiness checks",
  },
  {
    file: "apps/ui/src/reports/savedReportActionLabels.ts",
    pattern: /\?\? 0/,
    classification: "factual measured default",
    note: "Collision-safe label counters",
  },
];

const ROOTS = [
  "apps/ui/src/viewModels",
  "apps/ui/src/components",
  "apps/ui/src/pages",
  "apps/ui/src/lib/topologyStats.ts",
  "apps/ui/src/lib/decisionContract.ts",
  "apps/ui/src/lib/meshEvidenceLive.ts",
  "apps/ui/src/lib/meshGraphDense.ts",
  "apps/ui/src/lib/meshGraphSmartLayout.ts",
  "apps/ui/src/hooks/useTopologyGraphData.ts",
  "apps/ui/src/reports/savedReportActionLabels.ts",
];

function listFiles(root: string, repoRoot: string): string[] {
  const abs = path.join(repoRoot, root);
  if (!statSync(abs, { throwIfNoEntry: false })?.isDirectory()) {
    return statSync(abs, { throwIfNoEntry: false }) ? [root] : [];
  }
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) {
        if (name === "test" || name === "contracts") continue;
        walk(full);
        continue;
      }
      if (name.endsWith(".test.ts") || name.endsWith(".test.tsx")) continue;
      if (name.endsWith(".ts") || name.endsWith(".tsx")) {
        out.push(path.relative(repoRoot, full));
      }
    }
  };
  walk(abs);
  return out;
}

describe("unknown-zero source classifications", () => {
  it("classifies every ?? 0 / || 0 under primary presentation roots", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const files = new Set<string>();
    for (const root of ROOTS) {
      for (const file of listFiles(root, repoRoot)) files.add(file);
    }

    let matchCount = 0;
    for (const rel of [...files].sort()) {
      const text = readFileSync(path.join(repoRoot, rel), "utf8");
      for (const line of text.split("\n")) {
        if (!/(\?\?|\|\|) 0/.test(line)) continue;
        matchCount += 1;
        const allowed = CLASSIFICATIONS.some(
          (entry) => entry.file === rel && entry.pattern.test(line),
        );
        expect(allowed, `${rel}: unclassified: ${line.trim()}`).toBe(true);
      }
    }
    expect(matchCount).toBeGreaterThan(0);
  });
});
