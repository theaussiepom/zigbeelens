import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  coreFetch,
  createBrowserSession,
  deleteBrowserSession,
  downloadStoredReport,
  parseContentDispositionFilename,
  sanitizeDownloadFilename,
  triggerBrowserDownload,
  __unsafeApiMethodsForTests,
} from "./api";
import { authRuntime } from "./authRuntime";
import {
  clearSessionTransportCredentials,
  CSRF_HEADER_NAME,
  getSessionTransportRevision,
  installSessionTransportCredentials,
  resetSessionTransportForTests,
} from "./sessionTransport";
import {
  fetchCallParts,
  futureExpiry,
  jsonResponse,
  SENTINEL_TOKEN,
} from "@/test/authTestUtils";

function seedSession(csrf: string) {
  const { revision } = installSessionTransportCredentials(csrf);
  authRuntime.setSession({
    expiresAt: futureExpiry(),
    browserSessionEnabled: true,
    credentialRevision: revision,
  });
}

describe("credential-aware Core fetch", () => {
  beforeEach(() => {
    authRuntime.resetForTests();
    resetSessionTransportForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    resetSessionTransportForTests();
  });

  it("includes credentials on every request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.health();
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.credentials).toBe("include");
  });

  it("does not send CSRF on GET in session mode", async () => {
    seedSession("csrf-1");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.health();
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.headers.has(CSRF_HEADER_NAME)).toBe(false);
  });

  it("sends CSRF on session mutations and preserves Content-Type", async () => {
    seedSession("csrf-mutate");
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "r1",
        summary: "s",
        scope: "full",
        format: "json",
        redaction_profile: "standard",
        generated_at: "t",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.createReport({
      scope: "full",
      format: "json",
      redaction: { profile: "standard" },
    });
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.headers.get(CSRF_HEADER_NAME)).toBe("csrf-mutate");
    expect(call.headers.get("Content-Type")).toBe("application/json");
    expect(call.headers.has("Origin")).toBe(false);
  });

  it("omits CSRF for trusted_local mutations", async () => {
    authRuntime.setTrustedLocal(false);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ deleted: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api.deleteReport("r1");
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.headers.has(CSRF_HEADER_NAME)).toBe(false);
  });

  it("does not send CSRF on session bootstrap and uses bearer once", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        authenticated: true,
        auth_method: "session",
        browser_session_enabled: true,
        expires_at: futureExpiry(),
        csrf_token: "csrf-new",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await createBrowserSession(SENTINEL_TOKEN);
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.method).toBe("POST");
    expect(call.headers.get("Authorization")).toBe(`Bearer ${SENTINEL_TOKEN}`);
    expect(call.headers.has(CSRF_HEADER_NAME)).toBe(false);
    expect(call.headers.has("Origin")).toBe(false);
    expect(call.credentials).toBe("include");
    expect(call.cache).toBe("no-store");
  });

  it("blocks session mutation when CSRF is missing without sending the request", async () => {
    seedSession("temp");
    clearSessionTransportCredentials();
    // Identity remains session; transport CSRF is gone.
    authRuntime.setSession({
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
      credentialRevision: getSessionTransportRevision(),
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.deleteReport("r1")).rejects.toMatchObject({ kind: "csrf" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps CSRF 403 and Origin 403 kinds without retry", async () => {
    seedSession("csrf-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "CSRF validation failed." }, 403))
      .mockResolvedValueOnce(jsonResponse({ detail: "Browser origin validation failed." }, 403));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deleteReport("r1")).rejects.toMatchObject({ kind: "csrf", status: 403 });
    await expect(api.deleteReport("r2")).rejects.toMatchObject({ kind: "origin", status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("notifies unauthorized on protected 401 once per epoch", async () => {
    const listener = vi.fn();
    authRuntime.onUnauthorized(listener);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Authentication required." }, 401));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not treat public session-status 401 as protected unauthorized", async () => {
    const listener = vi.fn();
    authRuntime.onUnauthorized(listener);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Authentication required." }, 401));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      coreFetch("api/auth/session", {}, undefined, { intent: "public_session_status" }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
  });

  it("logout DELETE sends CSRF in session mode", async () => {
    seedSession("csrf-logout");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await deleteBrowserSession();
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.headers.get(CSRF_HEADER_NAME)).toBe("csrf-logout");
    expect(call.method).toBe("DELETE");
    expect(call.credentials).toBe("include");
  });

  it("covers every unsafe api method through mutation transport", async () => {
    seedSession("csrf-all");
    const fetchMock = vi.fn().mockImplementation(() =>
      jsonResponse({
        ok: true,
        deleted: true,
        snapshot_id: "s",
        status: "ok",
        id: "r",
        summary: "s",
        scope: "full",
        format: "json",
        redaction_profile: "standard",
        generated_at: "t",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createReport({
      scope: "full",
      format: "json",
      redaction: { profile: "standard" },
    });
    await api.deleteReport("r1");
    await api.captureTopology("home");

    expect(__unsafeApiMethodsForTests.length).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const call of fetchMock.mock.calls) {
      const parts = fetchCallParts(call);
      expect(parts.headers.get(CSRF_HEADER_NAME)).toBe("csrf-all");
      expect(parts.credentials).toBe("include");
    }
  });

  it("preserves stale_auth_context through allowEmpty JSON branch", async () => {
    seedSession("csrf-empty");
    let resolveText: ((value: string) => void) | null = null;
    const textPromise = new Promise<string>((resolve) => {
      resolveText = resolve;
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      text: () => textPromise,
      json: async () => ({}),
      blob: async () => new Blob(),
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = deleteBrowserSession();
    await Promise.resolve();
    await Promise.resolve();
    authRuntime.clear();
    clearSessionTransportCredentials();
    resolveText?.(JSON.stringify({ leftover: true }));
    await expect(pending).rejects.toMatchObject({ kind: "stale_auth_context" });
  });

  it("malformed bootstrap response is protocol not authentication", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ authenticated: "yes" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(createBrowserSession(SENTINEL_TOKEN)).rejects.toMatchObject({
      kind: "protocol",
    });
  });
});

describe("report download helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    resetSessionTransportForTests();
  });

  it("sanitizes traversal and control characters in filenames", () => {
    expect(sanitizeDownloadFilename("../../etc/passwd")).toBe("passwd");
    expect(sanitizeDownloadFilename("a\nb.json")).toBe("ab.json");
    expect(sanitizeDownloadFilename("")).toBe("zigbeelens-report.json");
  });

  it("parses Content-Disposition filename and filename*", () => {
    expect(parseContentDispositionFilename('attachment; filename="report.json"')).toBe(
      "report.json",
    );
    expect(
      parseContentDispositionFilename("attachment; filename*=UTF-8''my%20report.json"),
    ).toBe("my report.json");
  });

  it("downloads via credentialed fetch without Authorization or query token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("report-body", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Disposition": 'attachment; filename="net-report.json"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await downloadStoredReport("rep-1");
    expect(result.filename).toBe("net-report.json");
    expect(result.contentType).toContain("application/json");
    expect(await result.blob.text()).toBe("report-body");
    const call = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(call.url).toContain("api/reports/rep-1/download");
    expect(call.url).not.toMatch(/[?&](token|access_token|csrf)=/);
    expect(call.headers.has("Authorization")).toBe(false);
    expect(call.credentials).toBe("include");
  });

  it("refuses to save error JSON as a report file", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(downloadStoredReport("missing")).rejects.toBeInstanceOf(ApiError);
  });

  it("creates object URL, clicks anchor, and revokes", async () => {
    authRuntime.setTrustedLocal(false);
    const generation = authRuntime.getGeneration();
    const createObjectURL = vi.fn(() => "blob:test-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.fn();
    const remove = vi.fn();
    const appendChild = vi.spyOn(document.body, "appendChild").mockImplementation((node) => {
      const el = node as HTMLAnchorElement;
      el.click = click;
      el.remove = remove;
      return node;
    });

    await triggerBrowserDownload({
      blob: new Blob(["x"]),
      filename: "r.json",
      contentType: "application/json",
      authGeneration: generation,
    });

    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(remove).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test-url");
    appendChild.mockRestore();
  });

  it("rejects download trigger after auth generation change", async () => {
    seedSession("csrf-dl");
    const generation = authRuntime.getGeneration();
    const createObjectURL = vi.fn(() => "blob:test-url");
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    authRuntime.clear();
    await expect(
      triggerBrowserDownload({
        blob: new Blob(["x"]),
        filename: "r.json",
        contentType: "application/json",
        authGeneration: generation,
      }),
    ).rejects.toMatchObject({ kind: "stale_auth_context" });
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it("marks protected JSON stale after logout during body read", async () => {
    seedSession("csrf-stale");
    let resolveBody: ((value: string) => void) | null = null;
    const bodyPromise = new Promise<string>((resolve) => {
      resolveBody = resolve;
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => bodyPromise.then((text) => JSON.parse(text)),
      text: () => bodyPromise,
      blob: async () => new Blob(),
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = api.health();
    authRuntime.clear();
    resolveBody?.(JSON.stringify({ status: "ok" }));
    await expect(pending).rejects.toMatchObject({ kind: "stale_auth_context" });
  });
});
