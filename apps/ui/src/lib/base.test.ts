import { describe, expect, it, vi, afterEach } from "vitest";
import { detectRouterBasename, resolveApiBase } from "./base";

describe("resolveApiBase", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses VITE_API_BASE when set", () => {
    vi.stubEnv("VITE_API_BASE", "https://example.test/prefix/");
    expect(resolveApiBase()).toBe("https://example.test/prefix/");
  });

  it("resolves relative to the current page by default", () => {
    vi.stubEnv("VITE_API_BASE", "");
    const base = resolveApiBase();
    expect(base).toContain(window.location.pathname.split("/").slice(0, -1).join("/") || "");
  });
});

describe("detectRouterBasename", () => {
  it("detects Home Assistant Ingress prefix", () => {
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...original,
        pathname: "/api/hassio_ingress/abc123/incidents",
      },
    });
    expect(detectRouterBasename()).toBe("/api/hassio_ingress/abc123");
    Object.defineProperty(window, "location", { configurable: true, value: original });
  });
});
