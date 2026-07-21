import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Phase 6C: whole-network snapshot compare remains API/debug-only.
 * Current production UI must not call or render it.
 */

const ALLOWED = new Set([
  "lib/api.ts",
  "lib/api.test.ts",
  "lib/api.auth.test.ts",
  "types/topology.ts",
  "test/topologySnapshotCompareUiContract.test.ts",
]);

function walkSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      walkSourceFiles(path, out);
      continue;
    }
    if (!/\.(tsx|ts)$/.test(entry)) continue;
    out.push(path);
  }
  return out;
}

describe("topologySnapshotCompare UI contract", () => {
  it("keeps whole-network compare out of production UI surfaces", () => {
    const srcRoot = join(import.meta.dirname, "..");
    const offenders: string[] = [];

    for (const path of walkSourceFiles(srcRoot)) {
      const rel = path.slice(srcRoot.length + 1);
      if (ALLOWED.has(rel) || rel.endsWith(".test.ts") || rel.endsWith(".test.tsx")) {
        continue;
      }
      const content = readFileSync(path, "utf8");
      if (
        content.includes("topologySnapshotCompare") ||
        content.includes("snapshots/compare")
      ) {
        offenders.push(rel);
      }
    }

    expect(offenders).toEqual([]);
  });
});
