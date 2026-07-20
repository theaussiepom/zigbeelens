import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Phase 6B: current UI must not present RouterRisk DiagnosticConclusion copy.
 * Router intelligence enters Mesh via investigation_priorities /
 * router_neighbourhood_review only.
 */

const FORBIDDEN = [
  "router.risk.summary",
  "router.risk.severity",
  "router.risk.limitations",
  "RouterRiskCard",
] as const;

function walkSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      walkSourceFiles(path, out);
      continue;
    }
    if (!/\.(tsx|ts)$/.test(entry)) continue;
    if (entry.endsWith(".test.ts") || entry.endsWith(".test.tsx")) continue;
    out.push(path);
  }
  return out;
}

describe("RouterRisk UI presentation contract", () => {
  it("does not render router.risk DiagnosticConclusion fields in current UI source", () => {
    const srcRoot = join(import.meta.dirname, "..");
    const offenders: string[] = [];

    for (const path of walkSourceFiles(srcRoot)) {
      const content = readFileSync(path, "utf8");
      for (const token of FORBIDDEN) {
        if (content.includes(token)) {
          offenders.push(`${path}: ${token}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
