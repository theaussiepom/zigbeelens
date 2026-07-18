import { afterEach, describe, expect, it, vi } from "vitest";
import { authRuntime, CSRF_HEADER_NAME } from "./authRuntime";
import { futureExpiry } from "@/test/authTestUtils";

describe("authRuntime identity generation", () => {
  afterEach(() => {
    authRuntime.resetForTests();
  });

  it("is idempotent for identical trusted_local status", () => {
    authRuntime.setTrustedLocal(false);
    const gen = authRuntime.getGeneration();
    authRuntime.setTrustedLocal(false);
    expect(authRuntime.getGeneration()).toBe(gen);
  });

  it("is idempotent for identical session status", () => {
    const expiry = futureExpiry();
    authRuntime.setSession({
      csrfToken: "csrf-same",
      expiresAt: expiry,
      browserSessionEnabled: true,
    });
    const gen = authRuntime.getGeneration();
    authRuntime.setSession({
      csrfToken: "csrf-same",
      expiresAt: expiry,
      browserSessionEnabled: true,
    });
    expect(authRuntime.getGeneration()).toBe(gen);
  });

  it("advances generation when session tuple changes", () => {
    authRuntime.setSession({
      csrfToken: "csrf-a",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    const gen = authRuntime.getGeneration();
    authRuntime.setSession({
      csrfToken: "csrf-b",
      expiresAt: futureExpiry(90_000),
      browserSessionEnabled: true,
    });
    expect(authRuntime.getGeneration()).toBeGreaterThan(gen);
  });

  it("clear is idempotent when already clear", () => {
    authRuntime.clear();
    const gen = authRuntime.getGeneration();
    authRuntime.clear();
    expect(authRuntime.getGeneration()).toBe(gen);
  });

  it("logout/clear advances generation from authenticated", () => {
    authRuntime.setTrustedLocal(false);
    const gen = authRuntime.getGeneration();
    authRuntime.clear();
    expect(authRuntime.getGeneration()).toBeGreaterThan(gen);
  });

  it("dedupes unauthorized notifications per generation", () => {
    const listener = vi.fn();
    authRuntime.onUnauthorized(listener);
    authRuntime.setSession({
      csrfToken: "csrf",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    authRuntime.notifyUnauthorized();
    authRuntime.notifyUnauthorized();
    expect(listener).toHaveBeenCalledTimes(1);
    authRuntime.clear();
    authRuntime.notifyUnauthorized();
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

describe("authRuntime CSRF secrecy", () => {
  afterEach(() => {
    authRuntime.resetForTests();
  });

  it("does not expose CSRF via enumeration, JSON, or string conversion", () => {
    authRuntime.setSession({
      csrfToken: "csrf-secret-value",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    expect(JSON.stringify(authRuntime)).not.toContain("csrf-secret-value");
    expect(String(authRuntime)).not.toContain("csrf-secret-value");
    expect(Object.keys(authRuntime)).not.toContain("csrfToken");
    expect(Object.entries(authRuntime).flat().join(",")).not.toContain("csrf-secret-value");
    expect("getCsrfToken" in authRuntime).toBe(false);
  });

  it("applies CSRF to headers without returning the token", () => {
    authRuntime.setSession({
      csrfToken: "csrf-header-value",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    const headers = new Headers();
    expect(authRuntime.applySessionCsrf(headers)).toBe("applied");
    expect(headers.get(CSRF_HEADER_NAME)).toBe("csrf-header-value");
    expect(authRuntime.applySessionCsrf(new Headers())).toBe("applied");
  });

  it("returns not_session for trusted_local", () => {
    authRuntime.setTrustedLocal(false);
    expect(authRuntime.applySessionCsrf(new Headers())).toBe("not_session");
  });
});
