/**
 * Primary-copy safety: one catalogue authority, exact static exceptions.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { FORBIDDEN_USER_FACING_PHRASES } from "@/lib/meshGraphCopy";
import {
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

const CATALOGUE_FILE = "apps/ui/src/lib/meshGraphCopy.ts";

/** Safe negative limitation fragments — only for limitationText() output. */
const SAFE_LIMITATION_NEGATIVE = [
  /does not prove/i,
  /does not claim/i,
  /absence does not prove/i,
  /not (a |an )?(live|proven|causal)/i,
  /not proof of/i,
];

function assertPrimarySafe(text: string, context: string): void {
  for (const phrase of FORBIDDEN_USER_FACING_PHRASES) {
    expect(text.toLowerCase(), `${context}: ${text}`).not.toContain(phrase.toLowerCase());
  }
}

function assertLimitationSafe(text: string, context: string): void {
  for (const phrase of FORBIDDEN_USER_FACING_PHRASES) {
    if (!text.toLowerCase().includes(phrase.toLowerCase())) continue;
    const allowed = SAFE_LIMITATION_NEGATIVE.some((safe) => safe.test(text));
    expect(allowed, `${context}: forbidden positive in limitation: ${text}`).toBe(true);
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

function stringLiteralsInFile(filePath: string): string[] {
  const sourceText = readFileSync(filePath, "utf8");
  const source = ts.createSourceFile(filePath, sourceText, ts.ScriptTarget.Latest, true);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      found.push(node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

function containsPhrase(text: string, phrase: string): boolean {
  // Word-boundary match so import paths like DrawerShell do not hit "drawer".
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`, "i").test(text);
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
    for (const code of vocab.limitation_codes) {
      assertLimitationSafe(limitationText(code, {}), code);
    }
  });

  it("catalogue declarations are the only static exceptions and each is consumed once", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const remaining = new Set(FORBIDDEN_USER_FACING_PHRASES);

    const roots = [
      path.join(repoRoot, "apps/ui/src/components"),
      path.join(repoRoot, "apps/ui/src/pages"),
      path.join(repoRoot, "apps/ui/src/viewModels"),
      path.join(repoRoot, CATALOGUE_FILE),
    ];
    const files: string[] = [];
    for (const root of roots) {
      if (statSync(root).isDirectory()) files.push(...listTsFiles(root));
      else files.push(root);
    }

    let catalogueHits = 0;
    for (const file of files) {
      const rel = path.relative(repoRoot, file);
      for (const literal of stringLiteralsInFile(file)) {
        for (const phrase of FORBIDDEN_USER_FACING_PHRASES) {
          if (!containsPhrase(literal, phrase)) continue;
          // Exact catalogue declaration: the whole string is the phrase.
          if (rel === CATALOGUE_FILE && literal === phrase) {
            expect(remaining.has(phrase), `duplicate catalogue hit: ${phrase}`).toBe(true);
            remaining.delete(phrase);
            catalogueHits += 1;
            continue;
          }
          expect.fail(
            `${rel}: undeclared forbidden primary copy literal containing "${phrase}": ${JSON.stringify(literal)}`,
          );
        }
      }
    }

    expect(catalogueHits).toBe(FORBIDDEN_USER_FACING_PHRASES.length);
    expect(remaining.size, `unused catalogue phrases: ${[...remaining].join(", ")}`).toBe(0);
  });

  it("exact catalogue declaration passes and nearby unsafe fails", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const literals = stringLiteralsInFile(path.join(repoRoot, CATALOGUE_FILE));
    expect(literals).toContain("parent router");
    expect(literals).not.toContain("parent router caused the outage");
    expect(() => assertPrimarySafe("parent router caused the outage", "same-file")).toThrow();
  });
});
