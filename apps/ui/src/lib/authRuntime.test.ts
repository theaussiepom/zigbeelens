import { afterEach, describe, expect, it, vi } from "vitest";
import { authRuntime } from "./authRuntime";
import {
  CSRF_HEADER_NAME,
  installSessionTransportCredentials,
  resetSessionTransportForTests,
  startCredentialedFetch,
} from "./sessionTransport";
import { futureExpiry } from "@/test/authTestUtils";

describe("authRuntime identity generation", () => {
  afterEach(() => {
    authRuntime.resetForTests();
    resetSessionTransportForTests();
  });

  it("is idempotent for identical trusted_local status", () => {
    authRuntime.setTrustedLocal(false);
    const gen = authRuntime.getGeneration();
    authRuntime.setTrustedLocal(false);
    expect(authRuntime.getGeneration()).toBe(gen);
  });

  it("is idempotent for identical session status", () => {
    const expiry = futureExpiry();
    const { revision } = installSessionTransportCredentials("csrf-same");
    authRuntime.setSession({
      expiresAt: expiry,
      browserSessionEnabled: true,
      credentialRevision: revision,
    });
    const gen = authRuntime.getGeneration();
    authRuntime.setSession({
      expiresAt: expiry,
      browserSessionEnabled: true,
      credentialRevision: revision,
    });
    expect(authRuntime.getGeneration()).toBe(gen);
  });

  it("advances generation when session tuple changes", () => {
    const { revision: revA } = installSessionTransportCredentials("csrf-a");
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: revA,
    });
    const gen = authRuntime.getGeneration();
    const { revision: revB } = installSessionTransportCredentials("csrf-b");
    authRuntime.setSession({
      expiresAt: futureExpiry(90_000),
      browserSessionEnabled: true,
      credentialRevision: revB,
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
    const { revision } = installSessionTransportCredentials("csrf");
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: revision,
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
    resetSessionTransportForTests();
  });

  it("does not expose CSRF via enumeration, JSON, or string conversion", () => {
    const { revision } = installSessionTransportCredentials("csrf-secret-value");
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: revision,
    });
    expect(JSON.stringify(authRuntime)).not.toContain("csrf-secret-value");
    expect(String(authRuntime)).not.toContain("csrf-secret-value");
    expect(Object.keys(authRuntime)).not.toContain("csrfToken");
    expect(Object.entries(authRuntime).flat().join(",")).not.toContain("csrf-secret-value");
    expect("getCsrfToken" in authRuntime).toBe(false);
    expect("applySessionCsrf" in authRuntime).toBe(false);
    expect(JSON.stringify(authRuntime.toJSON())).not.toContain("csrf-secret-value");
  });

  it("cannot manufacture Headers containing the transport CSRF via public auth runtime", () => {
    const { revision } = installSessionTransportCredentials("csrf-header-value");
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: revision,
    });
    const headers = new Headers();
    // No public AuthRuntime method may write CSRF into caller-owned Headers.
    expect(typeof (authRuntime as { applySessionCsrf?: unknown }).applySessionCsrf).toBe(
      "undefined",
    );
    expect(headers.has(CSRF_HEADER_NAME)).toBe(false);
  });

  it("trusted_local does not activate session CSRF transport", async () => {
    authRuntime.setTrustedLocal(false);
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const started = startCredentialedFetch("http://example.test/api/x", {
      intent: "protected",
      method: "DELETE",
    });
    expect(started.ok).toBe(true);
    if (!started.ok) return;
    await started.promise;
    const req = fetchMock.mock.calls[0]?.[0] as Request;
    expect(req.headers.has(CSRF_HEADER_NAME)).toBe(false);
  });
});
