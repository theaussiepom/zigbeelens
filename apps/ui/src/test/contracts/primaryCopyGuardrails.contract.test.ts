/**
 * Primary-copy safety: one catalogue authority, exact static exceptions.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { FORBIDDEN_USER_FACING_PHRASES } from "@/lib/meshGraphCopy";
import {
  LIMITATION_CODES,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

const CATALOGUE_FILE = "apps/ui/src/lib/meshGraphCopy.ts";

/**
 * Explicit additional primary-copy scan roots beyond components/pages/ViewModels
 * and the catalogue file. These modules expose human-facing labels or report
 * action copy; transport errors and internal diagnostics are intentionally out
 * of scope.
 */
const ADDITIONAL_COPY_SCAN_ROOTS = [
  "apps/ui/src/lib/topologyLabels.ts",
  "apps/ui/src/reports",
  "apps/ui/src/lib/format.ts",
  "apps/ui/src/lib/monitoringGuide.ts",
  "apps/ui/src/navigation/model.ts",
] as const;

const EXPECTED_LIMITATIONS: Record<(typeof LIMITATION_CODES)[number], string> = {
  absence_from_latest_not_failure:
    "Absence from the latest snapshot does not prove the device failed or left the network.",
  route_hints_not_live_routing:
    "Route hints describe stored snapshot evidence. They do not prove live routing paths.",
  availability_limits_interpretation:
    "Availability and last-seen evidence is limited for this period, so offline or stale interpretation is constrained.",
  extended_silence_not_failure:
    "Silence longer than the observed reporting rhythm does not prove the device failed, lost power, or left the network.",
  reported_lqi_not_path_failure:
    "A drop in reported link quality does not prove a Zigbee path, route, or device failure.",
  model_pattern_not_causal:
    "A pattern among devices with the same stored model identity does not prove a model defect, manufacturer fault, or shared cause.",
};

function normalizeWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function containsPhrase(text: string, phrase: string): boolean {
  const normalized = normalizeWhitespace(text);
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`, "i").test(normalized);
}

function assertPrimarySafe(text: string, context: string): void {
  const normalized = normalizeWhitespace(text);
  for (const phrase of FORBIDDEN_USER_FACING_PHRASES) {
    expect(containsPhrase(normalized, phrase), `${context}: ${normalized}`).toBe(false);
  }
}

function listTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "test" || name === "contracts") continue;
      out.push(...listTsFiles(full));
      continue;
    }
    if (name.endsWith(".test.ts") || name.endsWith(".test.tsx")) continue;
    if (name.endsWith(".ts") || name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

function staticBinaryText(node: ts.BinaryExpression, source: ts.SourceFile): string | null {
  if (node.operatorToken.kind !== ts.SyntaxKind.PlusToken) return null;
  const left = staticTextFromNode(node.left, source);
  const right = staticTextFromNode(node.right, source);
  if (left === null || right === null) return null;
  return left + right;
}

function staticTextFromNode(node: ts.Node, source: ts.SourceFile): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isJsxText(node)) {
    return node.getText(source);
  }
  if (ts.isTemplateExpression(node)) {
    let text = node.head.text;
    for (const span of node.templateSpans) {
      // Only keep static fragments; interpolated expressions are not static copy.
      text += span.literal.text;
    }
    return text;
  }
  if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
    return node.text;
  }
  if (ts.isBinaryExpression(node)) {
    return staticBinaryText(node, source);
  }
  if (ts.isParenthesizedExpression(node)) {
    return staticTextFromNode(node.expression, source);
  }
  if (ts.isJsxExpression(node) && node.expression) {
    return staticTextFromNode(node.expression, source);
  }
  if (ts.isJsxAttribute(node) && node.initializer) {
    if (ts.isStringLiteral(node.initializer) || ts.isNoSubstitutionTemplateLiteral(node.initializer)) {
      return node.initializer.text;
    }
    if (ts.isJsxExpression(node.initializer) && node.initializer.expression) {
      return staticTextFromNode(node.initializer.expression, source);
    }
  }
  return null;
}

function collectUserFacingStaticTexts(sourceText: string, fileName = "snippet.tsx"): string[] {
  const source = ts.createSourceFile(fileName, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      found.push(node.text);
    } else if (ts.isJsxText(node)) {
      const text = normalizeWhitespace(node.getText(source));
      if (text) found.push(text);
    } else if (ts.isTemplateExpression(node)) {
      found.push(node.head.text);
      for (const span of node.templateSpans) {
        found.push(span.literal.text);
      }
    } else if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const joined = staticBinaryText(node, source);
      if (joined !== null) found.push(joined);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found.map(normalizeWhitespace).filter(Boolean);
}

describe("primary-copy guardrails", () => {
  it("rejects a deliberately unsafe sample", () => {
    const unsafe = "This failed link is the root cause of the currently routed outage.";
    expect(() => assertPrimarySafe(unsafe, "deliberate")).toThrow();
  });

  it("maps the complete vocabulary manifest primary-safe via presenters", () => {
    const vocab = oracleFixture.vocabulary;
    expect(vocab.headline_codes.length).toBeGreaterThan(0);
    expect(vocab.reason_codes.length).toBeGreaterThan(0);
    expect(vocab.limitation_codes.length).toBeGreaterThan(0);
    expect(vocab.suggested_check_codes.length).toBeGreaterThan(0);
    for (const code of vocab.headline_codes) {
      assertPrimarySafe(headlineText(code), code);
    }
    for (const code of vocab.reason_codes) {
      assertPrimarySafe(reasonText(code, {}), code);
    }
    for (const code of vocab.suggested_check_codes) {
      assertPrimarySafe(suggestedCheckText(code, {}), code);
    }
  });

  it("limitationText matches reviewed exact strings without mixed-positive exemptions", () => {
    expect(LIMITATION_CODES.length).toBe(Object.keys(EXPECTED_LIMITATIONS).length);
    for (const code of LIMITATION_CODES) {
      const text = limitationText(code, {});
      expect(text).toBe(EXPECTED_LIMITATIONS[code]);
      assertPrimarySafe(text, code);
    }
    expect(() =>
      assertPrimarySafe(
        "The parent router is the root cause, although this does not prove the device moved.",
        "mixed",
      ),
    ).toThrow();
  });

  it("catalogue declarations are the only static exceptions and each is consumed once", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const remaining = new Set(FORBIDDEN_USER_FACING_PHRASES);

    const roots = [
      path.join(repoRoot, "apps/ui/src/components"),
      path.join(repoRoot, "apps/ui/src/pages"),
      path.join(repoRoot, "apps/ui/src/viewModels"),
      path.join(repoRoot, CATALOGUE_FILE),
      ...ADDITIONAL_COPY_SCAN_ROOTS.map((root) => path.join(repoRoot, root)),
    ];
    const files: string[] = [];
    for (const root of roots) {
      if (statSync(root).isDirectory()) files.push(...listTsFiles(root));
      else files.push(root);
    }

    let catalogueHits = 0;
    for (const file of files) {
      const rel = path.relative(repoRoot, file);
      const texts = collectUserFacingStaticTexts(readFileSync(file, "utf8"), file);
      for (const literal of texts) {
        for (const phrase of FORBIDDEN_USER_FACING_PHRASES) {
          if (!containsPhrase(literal, phrase)) continue;
          if (rel === CATALOGUE_FILE && literal === phrase) {
            expect(remaining.has(phrase), `duplicate catalogue hit: ${phrase}`).toBe(true);
            remaining.delete(phrase);
            catalogueHits += 1;
            continue;
          }
          expect.fail(
            `${rel}: undeclared forbidden primary copy containing "${phrase}": ${JSON.stringify(literal)}`,
          );
        }
      }
    }

    expect(catalogueHits).toBe(FORBIDDEN_USER_FACING_PHRASES.length);
    expect(remaining.size, `unused catalogue phrases: ${[...remaining].join(", ")}`).toBe(0);
  });

  it("detects forbidden phrases in JSX text, templates, and concatenations", () => {
    const jsxTexts = collectUserFacingStaticTexts(
      `export const Bad = () => <p>The parent router failed.</p>;`,
    );
    expect(jsxTexts.some((text) => containsPhrase(text, "parent router"))).toBe(true);

    const templateTexts = collectUserFacingStaticTexts(
      "export const note = `observed root cause at ${when}`;",
    );
    expect(templateTexts.some((text) => containsPhrase(text, "root cause"))).toBe(true);

    const concatTexts = collectUserFacingStaticTexts(
      'export const note = "broken " + "link detected";',
    );
    expect(concatTexts.some((text) => containsPhrase(text, "broken link"))).toBe(true);

    expect(() => assertPrimarySafe("The parent router is the root cause.", "jsx-control")).toThrow();
  });

  it("rejects disappeared in normal strings, JSX text, and template fragments", () => {
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("disappeared");
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("lost link");
    expect(FORBIDDEN_USER_FACING_PHRASES).not.toContain("lost");
    expect(FORBIDDEN_USER_FACING_PHRASES).not.toContain("lost power");

    expect(() => assertPrimarySafe("the device disappeared", "string")).toThrow();

    const jsxTexts = collectUserFacingStaticTexts(
      `export const Bad = () => <p>the device disappeared overnight</p>;`,
    );
    expect(jsxTexts.some((text) => containsPhrase(text, "disappeared"))).toBe(true);

    const templateTexts = collectUserFacingStaticTexts(
      "export const note = `the device disappeared at ${when}`;",
    );
    expect(templateTexts.some((text) => containsPhrase(text, "disappeared"))).toBe(true);

    // Approved practical-check wording may mention lost power; do not blanket-ban "lost".
    expect(() =>
      assertPrimarySafe(
        "This may be worth checking if the device has moved, lost power, or has weak mesh conditions.",
        "lost-power-ok",
      ),
    ).not.toThrow();
    expect(() => assertPrimarySafe("lost link between neighbours", "lost-link")).toThrow();
  });

  it("exact catalogue declaration passes and nearby unsafe fails", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const texts = collectUserFacingStaticTexts(
      readFileSync(path.join(repoRoot, CATALOGUE_FILE), "utf8"),
      CATALOGUE_FILE,
    );
    expect(texts).toContain("parent router");
    expect(texts).not.toContain("parent router caused the outage");
    expect(() => assertPrimarySafe("parent router caused the outage", "same-file")).toThrow();
  });
});
