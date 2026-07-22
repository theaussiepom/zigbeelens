/**
 * Central primary-copy safety guardrails over the complete vocabulary manifest.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

const FORBIDDEN_POSITIVE = [
  /\bparent router\b/i,
  /\bcurrent route\b/i,
  /\blive route\b/i,
  /\bactual path\b/i,
  /\bcaused by\b/i,
  /\broot cause\b/i,
  /\bfailed link\b/i,
  /\bbroken link\b/i,
  /\bdevice moved\b/i,
  /\broute changed\b/i,
  /\broute failed\b/i,
  /\bdisconnected from router\b/i,
  /\bAI insight\b/i,
  /\binferred route\b/i,
  /\bderived neighbour\b/i,
  /\bderived neighbor\b/i,
];

const SAFE_NEGATIVE_LIMITATION = [
  /does not prove/i,
  /does not claim/i,
  /absence does not prove/i,
  /not (a |an )?(live|proven|causal)/i,
  /not proof of/i,
];

type AllowEntry = {
  file: string;
  pattern: RegExp;
  lineIncludes: string;
  reason: string;
};

const STATIC_COPY_ALLOWLIST: AllowEntry[] = [
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bparent router\b/i,
    lineIncludes: '"parent router"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bcurrent route\b/i,
    lineIncludes: '"current route"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bactual path\b/i,
    lineIncludes: '"actual path"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bcaused by\b/i,
    lineIncludes: '"caused by"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\broot cause\b/i,
    lineIncludes: '"root cause"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\binferred route\b/i,
    lineIncludes: '"inferred route"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bbroken link\b/i,
    lineIncludes: '"broken link"',
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue declaration",
  },
];

function assertPrimarySafe(text: string, context: string): void {
  for (const pattern of FORBIDDEN_POSITIVE) {
    expect(text, `${context}: ${text}`).not.toMatch(pattern);
  }
}

function assertLimitationSafe(text: string, context: string): void {
  for (const pattern of FORBIDDEN_POSITIVE) {
    if (!pattern.test(text)) continue;
    const allowed = SAFE_NEGATIVE_LIMITATION.some((safe) => safe.test(text));
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

function lineAllowed(rel: string, pattern: RegExp, line: string): boolean {
  return STATIC_COPY_ALLOWLIST.some(
    (entry) =>
      entry.file === rel &&
      entry.pattern.source === pattern.source &&
      line.includes(entry.lineIncludes),
  );
}

describe("primary-copy guardrails", () => {
  it("rejects a deliberately unsafe sample", () => {
    const unsafe = "This failed link is the root cause of the route changed event.";
    expect(() => assertPrimarySafe(unsafe, "deliberate")).toThrow();
  });

  it("maps the complete vocabulary manifest primary-safe", () => {
    const vocab = oracleFixture.vocabulary;
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

  it("exact catalogue declaration passes and nearby unsafe fails", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const file = path.join(repoRoot, "apps/ui/src/lib/meshGraphCopy.ts");
    const text = readFileSync(file, "utf8");
    const catalogueLine = text
      .split("\n")
      .find((line) => line.includes('"parent router"'));
    expect(catalogueLine).toBeTruthy();
    expect(
      lineAllowed(
        "apps/ui/src/lib/meshGraphCopy.ts",
        /\bparent router\b/i,
        catalogueLine!,
      ),
    ).toBe(true);

    const unsafeSameFile = 'const bad = "parent router caused the outage";';
    expect(
      lineAllowed("apps/ui/src/lib/meshGraphCopy.ts", /\bparent router\b/i, unsafeSameFile),
    ).toBe(false);
    expect(
      lineAllowed("apps/ui/src/lib/meshGraphCopy.ts", /\bcaused by\b/i, catalogueLine!),
    ).toBe(false);
  });

  it("static primary component copy has no undeclared forbidden positives", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const roots = [
      path.join(repoRoot, "apps/ui/src/components"),
      path.join(repoRoot, "apps/ui/src/pages"),
      path.join(repoRoot, "apps/ui/src/viewModels"),
      path.join(repoRoot, "apps/ui/src/lib/meshGraphCopy.ts"),
    ];
    const files: string[] = [];
    for (const root of roots) {
      if (statSync(root).isDirectory()) files.push(...listTsFiles(root));
      else files.push(root);
    }

    for (const file of files) {
      const rel = path.relative(repoRoot, file);
      const text = readFileSync(file, "utf8");
      for (const pattern of FORBIDDEN_POSITIVE) {
        for (const line of text.split("\n")) {
          if (!pattern.test(line)) continue;
          if (SAFE_NEGATIVE_LIMITATION.some((safe) => safe.test(line))) continue;
          if (lineAllowed(rel, pattern, line)) continue;
          expect.fail(`${rel}: undeclared forbidden primary copy: ${line.trim()}`);
        }
      }
    }
  });
});
