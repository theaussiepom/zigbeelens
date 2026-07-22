/**
 * Central primary-copy safety guardrails.
 * Strict on headlines/reasons/checks; limitation-aware for negative caveats.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  HEADLINE_CODES,
  REASON_CODES,
  headlineText,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";
import { allOracleScenarios } from "@/test/contracts/oracleFixture";

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

/** Exact allowlist: file + pattern + reason. No broad directory exclusions. */
const STATIC_COPY_ALLOWLIST: Array<{
  file: string;
  pattern: RegExp;
  reason: string;
}> = [
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bparent router\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bcurrent route\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bactual path\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\bcaused by\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\broot cause\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
  },
  {
    file: "apps/ui/src/lib/meshGraphCopy.ts",
    pattern: /\binferred route\b/i,
    reason: "FORBIDDEN_USER_FACING_PHRASES catalogue entry (not rendered copy)",
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
    expect(allowed, `${context}: forbidden positive in limitation: ${text}`).toBe(
      true,
    );
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

describe("primary-copy guardrails", () => {
  it("rejects a deliberately unsafe sample", () => {
    const unsafe = "This failed link is the root cause of the route changed event.";
    expect(() => assertPrimarySafe(unsafe, "deliberate")).toThrow();
  });

  it("oracle-mapped headlines/reasons/checks are primary-safe", () => {
    for (const [, scenario] of allOracleScenarios()) {
      for (const story of Object.values(scenario.device_stories)) {
        assertPrimarySafe(headlineText(story.headline_code), story.headline_code);
        for (const reason of story.reasons) {
          assertPrimarySafe(
            reasonText(reason.code, reason.params ?? {}),
            reason.code,
          );
        }
        for (const check of story.suggested_checks) {
          assertPrimarySafe(
            suggestedCheckText(check.code, check.params ?? {}),
            check.code,
          );
        }
        for (const limitation of story.limitations) {
          assertLimitationSafe(
            limitationText(limitation.code, limitation.params ?? {}),
            limitation.code,
          );
        }
      }
    }
  });

  it("catalogue headline/reason codes render primary-safe with empty params", () => {
    for (const code of HEADLINE_CODES) {
      assertPrimarySafe(headlineText(code), code);
    }
    for (const code of REASON_CODES) {
      assertPrimarySafe(reasonText(code, {}), code);
    }
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
        if (!pattern.test(text)) continue;
        const allowed = STATIC_COPY_ALLOWLIST.some(
          (entry) =>
            entry.file === rel &&
            (entry.pattern.source === pattern.source || entry.pattern.test(text)),
        );
        // Allow negative caveats that include forbidden substrings only when the
        // surrounding sentence is an explicit safety limitation.
        const lines = text.split("\n").filter((line) => pattern.test(line));
        for (const line of lines) {
          if (SAFE_NEGATIVE_LIMITATION.some((safe) => safe.test(line))) continue;
          if (allowed) continue;
          expect.fail(`${rel}: undeclared forbidden primary copy: ${line.trim()}`);
        }
      }
    }
  });
});
