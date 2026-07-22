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
  | "advanced/debug only";

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
    "file": "apps/ui/src/components/meshGraph/TopologyMetricStrip.tsx",
    "kind": "nullishCoalescing",
    "expression": "graphDetail?.nodes?.length ?? 0",
    "line": 26,
    "character": 16,
    "classification": "factual measured default",
    "note": "Array length fallback is a measured empty collection when the source list is absent or empty."
  },
  {
    "file": "apps/ui/src/components/reports/ContextualReportDialog.tsx",
    "kind": "nullishCoalescing",
    "expression": "n ?? 0",
    "line": 579,
    "character": 43,
    "classification": "factual measured default",
    "note": "Optional numeric formatter input treats a missing measured count as zero for display arithmetic."
  },
  {
    "file": "apps/ui/src/hooks/useTopologyGraphData.ts",
    "kind": "nullishCoalescing",
    "expression": "detail.data?.nodes?.length ?? 0",
    "line": 51,
    "character": 9,
    "classification": "factual measured default",
    "note": "Array length fallback is a measured empty collection when the source list is absent or empty."
  },
  {
    "file": "apps/ui/src/hooks/useTopologyGraphData.ts",
    "kind": "nullishCoalescing",
    "expression": "detail.data?.links?.length ?? 0",
    "line": 51,
    "character": 50,
    "classification": "factual measured default",
    "note": "Array length fallback is a measured empty collection when the source list is absent or empty."
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
    "expression": "backendStats?.snapshots_with_links ?? 0",
    "line": 212,
    "character": 17,
    "classification": "advanced/debug only",
    "note": "Advanced evidence-live debug counter: absent backend stats mean zero snapshots with links in that debug panel."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 524,
    "character": 31,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 699,
    "character": 22,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshEvidenceLive.ts",
    "kind": "nullishCoalescing",
    "expression": "neighborCounts.get(ieee) ?? 0",
    "line": 714,
    "character": 7,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.source) ?? 0",
    "line": 337,
    "character": 25,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.target) ?? 0",
    "line": 338,
    "character": 25,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.source) ?? 0",
    "line": 402,
    "character": 25,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphDense.ts",
    "kind": "nullishCoalescing",
    "expression": "perNode.get(edge.target) ?? 0",
    "line": 403,
    "character": 25,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(edge.source) ?? 0",
    "line": 165,
    "character": 30,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(edge.target) ?? 0",
    "line": 166,
    "character": 30,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(key) ?? 0",
    "line": 212,
    "character": 23,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(a) ?? 0",
    "line": 242,
    "character": 20,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(b) ?? 0",
    "line": 243,
    "character": 20,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(b.ieee_address) ?? 0",
    "line": 247,
    "character": 16,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "totals.get(a.ieee_address) ?? 0",
    "line": 247,
    "character": 52,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(pairKey(id, anchor)) ?? 0",
    "line": 265,
    "character": 19,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(b.ieee_address) ?? 0",
    "line": 309,
    "character": 17,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "degree.get(a.ieee_address) ?? 0",
    "line": 309,
    "character": 53,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/lib/meshGraphSmartLayout.ts",
    "kind": "nullishCoalescing",
    "expression": "weights.get(pairKey(coordinatorId, cluster.router.ieee_address)) ?? 0",
    "line": 425,
    "character": 17,
    "classification": "advanced/debug only",
    "note": "Map.get fallback is a graph algorithm accumulator for an unseen node/edge key, not unknown telemetry."
  },
  {
    "file": "apps/ui/src/pages/InvestigateLandingPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.review_first ?? 0",
    "line": 67,
    "character": 33,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/InvestigateLandingPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "summary.status_counts.worth_reviewing ?? 0",
    "line": 68,
    "character": 36,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.review_first ?? 0",
    "line": 228,
    "character": 20,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.review_first ?? 0",
    "line": 229,
    "character": 24,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.worth_reviewing ?? 0",
    "line": 233,
    "character": 20,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "statusCounts.worth_reviewing ?? 0",
    "line": 234,
    "character": 24,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/NetworksPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "timeline.data?.length ?? 0",
    "line": 308,
    "character": 11,
    "classification": "factual measured default",
    "note": "Array length fallback is a measured empty collection when the source list is absent or empty."
  },
  {
    "file": "apps/ui/src/pages/OverviewPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "data.decision_summary.status_counts.review_first ?? 0",
    "line": 132,
    "character": 23,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/OverviewPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "data.decision_summary.status_counts.worth_reviewing ?? 0",
    "line": 133,
    "character": 26,
    "classification": "factual measured default",
    "note": "Missing DecisionCountSummary status enum key means a measured count of zero subjects for that status."
  },
  {
    "file": "apps/ui/src/pages/SettingsPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "collector.subscribed_topics_count ?? 0",
    "line": 89,
    "character": 50,
    "classification": "factual measured default",
    "note": "Collector settings counter: missing subscribed_topics_count is a measured zero topics subscribed."
  },
  {
    "file": "apps/ui/src/pages/SettingsPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "health.data?.mqtt_discovery?.published_entities_count ?? 0",
    "line": 126,
    "character": 21,
    "classification": "factual measured default",
    "note": "MQTT discovery settings counter: missing published_entities_count is a measured zero published entities."
  },
  {
    "file": "apps/ui/src/pages/SettingsPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "health.data?.home_assistant_enrichment?.matched_devices ?? 0",
    "line": 177,
    "character": 27,
    "classification": "factual measured default",
    "note": "Home Assistant enrichment counter: missing matched_devices is a measured zero matched devices."
  },
  {
    "file": "apps/ui/src/pages/TopologyGraphPage.tsx",
    "kind": "nullishCoalescing",
    "expression": "liveEvidence?.edges.filter((edge) => edge.in_latest_snapshot).length ?? 0",
    "line": 44,
    "character": 5,
    "classification": "factual measured default",
    "note": "Array length fallback is a measured empty collection when the source list is absent or empty."
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


const ADVANCED_DEBUG_ALLOWLIST = new Set([
  "apps/ui/src/lib/meshEvidenceLive.ts",
  "apps/ui/src/lib/meshGraphDense.ts",
  "apps/ui/src/lib/meshGraphSmartLayout.ts",
]);

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

const EXPECTED_TOTAL = 45;

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
      if (entry.classification === "advanced/debug only") {
        expect(
          ADVANCED_DEBUG_ALLOWLIST.has(entry.file),
          `advanced/debug outside allowlist: ${entry.file}`,
        ).toBe(true);
        continue;
      }
      expect(ADVANCED_DEBUG_ALLOWLIST.has(entry.file)).toBe(false);
      const isPrimary = PRIMARY_PRESENTATION_PREFIXES.some((prefix) =>
        entry.file.startsWith(prefix),
      );
      if (isPrimary) {
        expect(
          entry.classification === "factual measured default" ||
            entry.classification === "safe rendering fallback",
          `primary presentation must not be advanced/debug: ${entryKey(entry)}`,
        ).toBe(true);
      }
    }
  });
});
