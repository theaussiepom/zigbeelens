import { describe, expect, it, vi, afterEach } from "vitest";
import { scenariosEnabled } from "./flags";

describe("scenariosEnabled", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is enabled when VITE_ENABLE_SCENARIOS=true", () => {
    vi.stubEnv("VITE_ENABLE_SCENARIOS", "true");
    expect(scenariosEnabled()).toBe(true);
  });

  it("is disabled in a production build without the flag", () => {
    vi.stubEnv("VITE_ENABLE_SCENARIOS", "");
    vi.stubEnv("DEV", false);
    expect(scenariosEnabled()).toBe(false);
  });
});
