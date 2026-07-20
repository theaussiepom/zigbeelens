import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  investigatePath,
  legacyTopologyGraphPath,
  topologySnapshotPath,
} from "@/lib/routes";

const srcRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const ALLOWED_LEGACY_GRAPH_FILES = new Set([
  "lib/routes.ts",
  "lib/routes.test.ts",
  "main.tsx",
  "components/LegacyTopologyGraphRedirect.tsx",
  "pages/LegacyTopologyGraphRedirect.test.tsx",
]);

function walkTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...walkTsFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith(".d.ts")) {
      out.push(full);
    }
  }
  return out;
}

describe("routes helpers", () => {
  it("builds canonical investigate and snapshot paths", () => {
    expect(investigatePath("home")).toBe("/investigate/home");
    expect(topologySnapshotPath("home")).toBe("/topology/home");
    expect(legacyTopologyGraphPath("home")).toBe("/topology/home/graph");
  });

  it("keeps /topology/:networkId/graph only in compatibility routing/tests", () => {
    const offenders: string[] = [];
    for (const file of walkTsFiles(srcRoot)) {
      const rel = path.relative(srcRoot, file).replaceAll("\\", "/");
      const text = readFileSync(file, "utf8");
      if (!text.includes("/topology/") || !text.includes("/graph")) {
        continue;
      }
      // Match literal path templates that navigate to the legacy graph route.
      if (
        /`\/topology\/\$\{[^}]+}\/graph`/.test(text) ||
        /"\/topology\/[^"]+\/graph"/.test(text) ||
        /'\/topology\/[^']+\/graph'/.test(text) ||
        /path="topology\/:networkId\/graph"/.test(text) ||
        /path="\/topology\/:networkId\/graph"/.test(text)
      ) {
        if (!ALLOWED_LEGACY_GRAPH_FILES.has(rel) && !rel.endsWith("routes.test.ts")) {
          // Allow explicit redirect regression test file.
          if (rel !== "pages/LegacyTopologyGraphRedirect.test.tsx") {
            offenders.push(rel);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
