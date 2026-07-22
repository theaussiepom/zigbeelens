import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const UI_SRC = path.resolve(import.meta.dirname, "../..");

function listProductionSources(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "test") continue;
      out.push(...listProductionSources(full));
      continue;
    }
    if (name.endsWith(".test.ts") || name.endsWith(".test.tsx")) continue;
    if (name.endsWith(".ts") || name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

describe("production import guard", () => {
  it("production modules do not import test/support or test/fixtures", () => {
    const sources = listProductionSources(UI_SRC);
    expect(sources.length).toBeGreaterThan(0);
    for (const file of sources) {
      const text = readFileSync(file, "utf8");
      expect(text, file).not.toMatch(/from ["']@\/test\//);
      expect(text, file).not.toMatch(/from ["']\.\.\/test\//);
      expect(text, file).not.toMatch(/test\/support/);
      expect(text, file).not.toMatch(/test\/fixtures/);
    }
  });
});
