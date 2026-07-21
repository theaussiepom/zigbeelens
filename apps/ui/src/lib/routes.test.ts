import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { devicePath } from "@/lib/format";
import {
  encodeRouteSegment,
  investigatePath,
  legacyRoutersPath,
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

const ALLOWED_ROUTERS_PATH_FILES = new Set([
  "lib/routes.ts",
  "lib/routes.test.ts",
  "main.tsx",
  "components/LegacyRoutersRedirect.tsx",
  "pages/LegacyRoutersRedirect.test.tsx",
  "navigation/model.test.ts",
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
  it("encodes network ID path segments", () => {
    const vectors: Array<[string, string]> = [
      ["home", "home"],
      ["Home Office", "Home%20Office"],
      ["home#2", "home%232"],
      ["home?test", "home%3Ftest"],
      ["münchen", "m%C3%BCnchen"],
      ["50%mesh", "50%25mesh"],
    ];
    for (const [input, encoded] of vectors) {
      expect(encodeRouteSegment(input)).toBe(encoded);
      expect(investigatePath(input)).toBe(`/investigate/${encoded}`);
      expect(topologySnapshotPath(input)).toBe(`/topology/${encoded}`);
      expect(legacyTopologyGraphPath(input)).toBe(`/topology/${encoded}/graph`);
    }
  });

  it("does not double-encode already-decoded logical IDs", () => {
    expect(investigatePath("home%20office")).toBe("/investigate/home%2520office");
    expect(devicePath("home%20office", "0xabc")).toBe("/devices/home%2520office/0xabc");
  });

  it("encodes both Device Detail path segments exactly once", () => {
    expect(devicePath("Home Office", "0xabc")).toBe("/devices/Home%20Office/0xabc");
    expect(devicePath("home#2", "0xabc")).toBe("/devices/home%232/0xabc");
    expect(devicePath("50%mesh", "0xabc")).toBe("/devices/50%25mesh/0xabc");
    expect(devicePath("home", "0xab/cd")).toBe(`/devices/home/${encodeURIComponent("0xab/cd")}`);
  });

  it("keeps /topology/:networkId/graph only in compatibility routing/tests", () => {
    const offenders: string[] = [];
    for (const file of walkTsFiles(srcRoot)) {
      const rel = path.relative(srcRoot, file).replaceAll("\\", "/");
      const text = readFileSync(file, "utf8");
      if (
        /`\/topology\/\$\{[^}]+}\/graph`/.test(text) ||
        /"\/topology\/[^"]+\/graph"/.test(text) ||
        /'\/topology\/[^']+\/graph'/.test(text) ||
        /path="topology\/:networkId\/graph"/.test(text) ||
        /path="\/topology\/:networkId\/graph"/.test(text)
      ) {
        if (!ALLOWED_LEGACY_GRAPH_FILES.has(rel)) {
          offenders.push(rel);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps literal /routers only in compatibility routing/tests", () => {
    expect(legacyRoutersPath()).toBe("/routers");
    const offenders: string[] = [];
    for (const file of walkTsFiles(srcRoot)) {
      const rel = path.relative(srcRoot, file).replaceAll("\\", "/");
      if (ALLOWED_ROUTERS_PATH_FILES.has(rel)) continue;
      const text = readFileSync(file, "utf8");
      // Product links / to= targets — allow API paths like api/routers.
      if (
        /to=["']\/routers["']/.test(text) ||
        /href=["']\/routers["']/.test(text) ||
        /Navigate to=["']\/routers["']/.test(text) ||
        /`\/routers`/.test(text) ||
        /to:\s*["']\/routers["']/.test(text)
      ) {
        offenders.push(rel);
      }
    }
    expect(offenders).toEqual([]);
  });
});
