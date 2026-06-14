import { describe, expect, it, vi, afterEach } from "vitest";
import { detectRouterBasename, resolveApiBase } from "./base";

function withPathname(pathname: string, fn: () => void) {
  const original = window.location;
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...original, pathname, origin: "http://localhost:5173" },
  });
  try {
    fn();
  } finally {
    Object.defineProperty(window, "location", { configurable: true, value: original });
  }
}

describe("resolveApiBase", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses VITE_API_BASE when set", () => {
    vi.stubEnv("VITE_API_BASE", "https://example.test/prefix/");
    expect(resolveApiBase()).toBe("https://example.test/prefix/");
  });

  it("anchors to the app root, not the current page directory", () => {
    vi.stubEnv("VITE_API_BASE", "");
    // Nested detail route must still resolve API calls against the app root,
    // otherwise `api/devices/...` would hit `/devices/<net>/api/...` (HTML 404).
    withPathname("/devices/home/0x00158d0001a2b3c4", () => {
      expect(resolveApiBase()).toBe("http://localhost:5173/");
    });
  });

  it("anchors under a Home Assistant Ingress prefix", () => {
    vi.stubEnv("VITE_API_BASE", "");
    withPathname("/api/hassio_ingress/abc123/devices/home/0x00158d0001a2b3c4", () => {
      expect(resolveApiBase()).toBe("http://localhost:5173/api/hassio_ingress/abc123/");
    });
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
