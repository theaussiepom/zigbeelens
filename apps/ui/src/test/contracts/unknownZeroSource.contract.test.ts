/**
 * Exact inventory of ?? 0 / || 0 fallbacks under primary presentation roots.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

type Classification =
  | "factual measured default"
  | "safe rendering fallback"
  | "graph algorithm accumulator";

type DeclaredEntry = {
  file: string;
  kind: "nullishCoalescing" | "logicalOr";
  expression: string;
  line: number;
  character: number;
  classification: Classification;
  note: string;
};

/** Exact declared inventory — each discovered expression must match one entry. */
const DECLARED: DeclaredEntry[] = [
  {
    "file": "apps/ui/src/components/cards.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.review_first ?? 0",
    "line": 131,
    "character": 23,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/components/cards.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.worth_reviewing ?? 0",
    "line": 132,
    "character": 26,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/lib/decisionContract.ts",
    "kind": "nullishCoalescing",
    "expression": "status_counts[status] ?? 0",
    "line": 287,
    "character": 12,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/lib/decisionContract.ts",
    "kind": "nullishCoalescing",
    "expression": "priority_counts[priority] ?? 0",
    "line": 297,
    "character": 12,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary priority enum key means a measured count of zero subjects for that priority."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 511,
    "character": 31,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 688,
    "character": 22,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 704,
    "character": 7,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.source) ?? 0",
    "line": 337,
    "character": 25,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.target) ?? 0",
    "line": 338,
    "character": 25,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.source) ?? 0",
    "line": 402,
    "character": 25,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.target) ?? 0",
    "line": 403,
    "character": 25,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(edge.source) ?? 0",
    "line": 165,
    "character": 30,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(edge.target) ?? 0",
    "line": 166,
    "character": 30,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(key) ?? 0",
    "line": 212,
    "character": 23,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(a) ?? 0",
    "line": 242,
    "character": 20,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(b) ?? 0",
    "line": 243,
    "character": 20,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(b.ieee_address) ?? 0",
    "line": 247,
    "character": 16,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(a.ieee_address) ?? 0",
    "line": 247,
    "character": 52,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(pairKey(id, anchor)) ?? 0",
    "line": 265,
    "character": 19,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(b.ieee_address) ?? 0",
    "line": 309,
    "character": 17,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(a.ieee_address) ?? 0",
    "line": 309,
    "character": 53,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(pairKey(coordinatorId, cluster.router.ieee_address)) ?? 0",
    "line": 425,
    "character": 17,
    "classification": "graph algorithm accumulator",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/pages/InvestigateLandingPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.review_first ?? 0",
    "line": 75,
    "character": 33,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/InvestigateLandingPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.worth_reviewing ?? 0",
    "line": 76,
    "character": 36,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.review_first ?? 0",
    "line": 276,
    "character": 20,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.review_first ?? 0",
    "line": 277,
    "character": 24,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.worth_reviewing ?? 0",
    "line": 281,
    "character": 20,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.worth_reviewing ?? 0",
    "line": 282,
    "character": 24,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/OverviewPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "data.decision_summary.status_counts.review_first ?? 0",
    "line": 197,
    "character": 23,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/OverviewPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "data.decision_summary.status_counts.worth_reviewing ?? 0",
    "line": 198,
    "character": 26,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/reports/savedReportActionLabels.ts",
    "kind": "nullishCoalescing",
    "expression": "counts.get(key) ?? 0",
    "line": 42,
    "character": 22,
    "classification": "factual measured default",
    "note": "Label-frequency Map.get fallback is a measured empty group for a newly encountered action label."
  },
  {
    "file": "apps/ui/src/reports/savedReportActionLabels.ts",
    "kind": "nullishCoalescing",
    "expression": "seen.get(key) ?? 0",
    "line": 48,
    "character": 24,
    "classification": "factual measured default",
    "note": "Duplicate-label ordinal count starts from a measured empty group when the label has not been seen yet."
  },
  {
    "file": "apps/ui/src/viewModels/incidents/incidentViewModel.ts",
    "kind": "nullishCoalescing",
    "expression": "counts.get(label) ?? 0",
    "line": 106,
    "character": 24,
    "classification": "factual measured default",
    "note": "Duplicate-label ordinal count starts from a measured empty group when the incident label has not been seen yet."
  },
  {
    "file": "apps/ui/src/viewModels/reports/reportDecisionViewModel.ts",
    "kind": "nullishCoalescing",
    "expression": "statusCounts[status] ?? 0",
    "line": 102,
    "character": 19,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/viewModels/reports/reportDecisionViewModel.ts",
    "kind": "nullishCoalescing",
    "expression": "count ?? 0",
    "line": 116,
    "character": 19,
    "classification": "factual measured default",
    "note": "Optional priority count from a measured DecisionCountSummary map defaults to zero subjects when the key is absent."
  }
];


const GRAPH_ALGORITHM_MODULES = new Set([
  "apps/ui/src/lib/meshEvidenceLive.ts",
  "apps/ui/src/lib/meshGraphDense.ts",
  "apps/ui/src/lib/meshGraphSmartLayout.ts",
]);

const GRAPH_ACCUMULATOR_EXPRESSION_RE =
  /\.(?:get)\s*\(/;

const PRIMARY_PRESENTATION_PREFIXES = [
  "apps/ui/src/components/",
  "apps/ui/src/pages/",
  "apps/ui/src/viewModels/",
  "apps/ui/src/reports/",
];

const PLACEHOLDER_NOTE_RE =
  /^(classified zero fallback|safe|expected)$/i;

function noteIsMeaningful(note: string): boolean {
  const trimmed = note.trim();
  if (trimmed.length < 24) return false;
  if (PLACEHOLDER_NOTE_RE.test(trimmed)) return false;
  if (/\b(classified zero fallback)\b/i.test(trimmed)) return false;
  // Require a domain cue beyond a bare adjective.
  return /\b(measured|accumulator|collection|enum|group|count|telemetry|debug|empty|absent|missing)\b/i.test(
    trimmed,
  );
}

const EXPECTED_TOTAL = 35;

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
  "apps/ui/src/reports/savedReportActionLabels.ts"
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

function normalizeExpression(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function entryKey(entry: {
  file: string;
  kind: string;
  expression: string;
  line: number;
  character: number;
}): string {
  return [
    entry.file,
    entry.kind,
    normalizeExpression(entry.expression),
    String(entry.line),
    String(entry.character),
  ].join("::");
}

function discoverZeroFallbacks(
  repoRoot: string,
  rel: string,
): Array<{
  file: string;
  kind: DeclaredEntry["kind"];
  expression: string;
  line: number;
  character: number;
}> {
  const abs = path.join(repoRoot, rel);
  const sourceText = readFileSync(abs, "utf8");
  const source = ts.createSourceFile(abs, sourceText, ts.ScriptTarget.Latest, true);
  const found: Array<{
    file: string;
    kind: DeclaredEntry["kind"];
    expression: string;
    line: number;
    character: number;
  }> = [];

  const visit = (node: ts.Node) => {
    if (
      ts.isBinaryExpression(node) &&
      (node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken ||
        node.operatorToken.kind === ts.SyntaxKind.BarBarToken) &&
      ts.isNumericLiteral(node.right) &&
      node.right.text === "0"
    ) {
      const kind =
        node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
          ? "nullishCoalescing"
          : "logicalOr";
      const expression = normalizeExpression(node.getText(source));
      const { line, character } = source.getLineAndCharacterOfPosition(node.getStart(source));
      found.push({
        file: rel,
        kind,
        expression,
        line: line + 1,
        character: character + 1,
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

describe("unknown-zero source classifications", () => {
  it("discovers an exact inventory equal to the declared set", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const files = new Set<string>();
    for (const root of ROOTS) {
      for (const file of listFiles(root, repoRoot)) files.add(file);
    }

    const discovered = [...files]
      .sort()
      .flatMap((rel) => discoverZeroFallbacks(repoRoot, rel));

    const declaredKeys = DECLARED.map(entryKey);
    const discoveredKeys = discovered.map(entryKey);
    const remaining = new Set(declaredKeys);

    expect(DECLARED.length).toBe(EXPECTED_TOTAL);
    expect(discovered.length).toBe(EXPECTED_TOTAL);
    expect(new Set(declaredKeys).size).toBe(EXPECTED_TOTAL);
    expect(new Set(discoveredKeys).size).toBe(EXPECTED_TOTAL);

    for (const key of discoveredKeys) {
      expect(remaining.has(key), `undeclared zero fallback: ${key}`).toBe(true);
      remaining.delete(key);
    }
    expect(remaining.size, `unused declarations: ${[...remaining].join(", ")}`).toBe(0);
  });
  it("every declared note is a domain-specific safety justification", () => {
    for (const entry of DECLARED) {
      expect(entry.note.trim().length, entryKey(entry)).toBeGreaterThan(0);
      expect(
        noteIsMeaningful(entry.note),
        `placeholder or non-domain note for ${entryKey(entry)}: ${entry.note}`,
      ).toBe(true);
      expect(PLACEHOLDER_NOTE_RE.test(entry.note.trim())).toBe(false);
    }
  });

  it("classification policy matches module role", () => {
    for (const entry of DECLARED) {
      if (entry.classification === "graph algorithm accumulator") {
        expect(
          GRAPH_ALGORITHM_MODULES.has(entry.file),
          `graph accumulator outside algorithm modules: ${entry.file}`,
        ).toBe(true);
        expect(
          GRAPH_ACCUMULATOR_EXPRESSION_RE.test(entry.expression),
          `graph accumulator without Map.get semantics: ${entry.expression}`,
        ).toBe(true);
        const isPrimary = PRIMARY_PRESENTATION_PREFIXES.some((prefix) =>
          entry.file.startsWith(prefix),
        );
        expect(isPrimary, `graph accumulator in primary presentation: ${entry.file}`).toBe(false);
        continue;
      }
      const isPrimary = PRIMARY_PRESENTATION_PREFIXES.some((prefix) =>
        entry.file.startsWith(prefix),
      );
      if (isPrimary) {
        expect(
          entry.classification === "factual measured default" ||
            entry.classification === "safe rendering fallback",
          `primary presentation must be measured/rendering: ${entryKey(entry)}`,
        ).toBe(true);
      }
    }
  });
});
