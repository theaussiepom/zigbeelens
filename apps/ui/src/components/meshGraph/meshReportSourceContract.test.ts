import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const MESH_DIR = path.join(__dirname);
const PRODUCTION_GLOBS = [".tsx", ".ts"];

function listProductionSources(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...listProductionSources(full));
      continue;
    }
    if (name.endsWith(".test.ts") || name.endsWith(".test.tsx")) continue;
    if (!PRODUCTION_GLOBS.some((ext) => name.endsWith(ext))) continue;
    out.push(full);
  }
  return out;
}

describe("Mesh production report source contract", () => {
  it("does not import or call the removed client-only Mesh report path", () => {
    const sources = listProductionSources(MESH_DIR);
    expect(sources.length).toBeGreaterThan(0);
    for (const file of sources) {
      const text = readFileSync(file, "utf8");
      expect(text, file).not.toMatch(/\bEvidenceReportMenu\b/);
      expect(text, file).not.toMatch(/\bbuildMeshEvidenceReport\b/);
      expect(text, file).not.toMatch(/\bMeshEvidenceReport\b/);
    }
  });

  it("GraphToolbar launches ContextualReportDialog for network scope", () => {
    const source = readFileSync(path.join(MESH_DIR, "GraphToolbar.tsx"), "utf8");
    expect(source).toMatch(/ContextualReportDialog/);
    expect(source).toMatch(/MESH_CREATE_NETWORK_REPORT_LABEL/);
    expect(source).toMatch(/scope:\s*"network"/);
    expect(source).not.toMatch(/buildMeshEvidenceReport/);
    const copy = readFileSync(
      path.join(MESH_DIR, "..", "..", "lib", "meshGraphCopy.ts"),
      "utf8",
    );
    expect(copy).toMatch(/MESH_CREATE_NETWORK_REPORT_LABEL\s*=\s*"Create network report"/);
  });
});
