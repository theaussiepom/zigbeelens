import { afterEach, describe, expect, it, vi } from "vitest";
import { authRuntime } from "./authRuntime";
import {
  clearSessionTransportCredentials,
  CSRF_HEADER_NAME,
  getSessionTransportRevision,
  installSessionTransportCredentials,
  isSessionTransportActive,
  resetSessionTransportForTests,
  startCredentialedFetch,
} from "./sessionTransport";
import { futureExpiry } from "@/test/authTestUtils";

function seedSession(csrf: string) {
  const { revision } = installSessionTransportCredentials(csrf);
  authRuntime.setSession({
    expiresAt: futureExpiry(),
    browserSessionEnabled: true,
    credentialRevision: revision,
  });
}

describe("sessionTransport CSRF privacy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    resetSessionTransportForTests();
  });

  it("applies CSRF only onto the Request handed to fetch", async () => {
    seedSession("e30.mutate");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const started = startCredentialedFetch("http://example.test/api/reports", {
      intent: "protected",
      method: "DELETE",
    });
    expect(started.ok).toBe(true);
    if (!started.ok) return;
    await started.promise;

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    const req = fetchMock.mock.calls[0]?.[0] as Request;
    expect(req).toBeInstanceOf(Request);
    expect(req.headers.get(CSRF_HEADER_NAME)).toBe("e30.mutate");
    expect(req.credentials).toBe("include");
  });

  it("does not apply CSRF on GET or trusted_local mutations", async () => {
    seedSession("e30.get");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const getStarted = startCredentialedFetch("http://example.test/api/health", {
      intent: "protected",
      method: "GET",
    });
    expect(getStarted.ok).toBe(true);
    if (getStarted.ok) await getStarted.promise;

    authRuntime.clear();
    clearSessionTransportCredentials();
    authRuntime.setTrustedLocal(false);
    const delStarted = startCredentialedFetch("http://example.test/api/reports/x", {
      intent: "protected",
      method: "DELETE",
    });
    expect(delStarted.ok).toBe(true);
    if (delStarted.ok) await delStarted.promise;

    const getReq = fetchMock.mock.calls[0]?.[0] as Request;
    const delReq = fetchMock.mock.calls[1]?.[0] as Request;
    expect(getReq.headers.has(CSRF_HEADER_NAME)).toBe(false);
    expect(delReq.headers.has(CSRF_HEADER_NAME)).toBe(false);
  });

  it("clearing session clears transport-private CSRF", async () => {
    seedSession("e30.clear");
    expect(isSessionTransportActive()).toBe(true);
    const revBefore = getSessionTransportRevision();
    clearSessionTransportCredentials();
    authRuntime.clear();
    expect(isSessionTransportActive()).toBe(false);
    expect(getSessionTransportRevision()).toBeGreaterThan(revBefore);

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    // Re-seed identity without transport credentials → csrf_missing.
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: getSessionTransportRevision(),
    });
    const started = startCredentialedFetch("http://example.test/api/x", {
      intent: "protected",
      method: "DELETE",
    });
    expect(started).toEqual({ ok: false, reason: "csrf_missing" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("replacing CSRF advances revision and sends the new token", async () => {
    seedSession("e30.old");
    const { revision, changed } = installSessionTransportCredentials("e30.new");
    expect(changed).toBe(true);
    authRuntime.setSession({
      expiresAt: futureExpiry(90_000),
      browserSessionEnabled: true,
      credentialRevision: revision,
    });

    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const started = startCredentialedFetch("http://example.test/api/x", {
      intent: "session_logout",
      method: "DELETE",
    });
    expect(started.ok).toBe(true);
    if (!started.ok) return;
    await started.promise;
    const req = fetchMock.mock.calls[0]?.[0] as Request;
    expect(req.headers.get(CSRF_HEADER_NAME)).toBe("e30.new");
  });

  it("releases bootstrap bearer from options before await", async () => {
    let resolveFetch: ((value: Response) => void) | null = null;
    const fetchPromise = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(fetchPromise);
    vi.stubGlobal("fetch", fetchMock);

    const options = {
      intent: "session_bootstrap" as const,
      method: "POST",
      bearer: "zl-bootstrap-token",
    };
    const started = startCredentialedFetch("http://example.test/api/auth/session", options);
    expect(started.ok).toBe(true);
    expect(options.bearer).toBeUndefined();
    const req = fetchMock.mock.calls[0]?.[0] as Request;
    expect(req.headers.get("Authorization")).toBe("Bearer zl-bootstrap-token");
    expect(req.headers.has(CSRF_HEADER_NAME)).toBe(false);
    resolveFetch?.(new Response("{}", { status: 200 }));
    if (started.ok) await started.promise;
  });
});
