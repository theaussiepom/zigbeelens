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
import { authRuntime, CSRF_HEADER_NAME } from "./authRuntime";
import { futureExpiry, jsonResponse, SENTINEL_TOKEN } from "@/test/authTestUtils";

describe("credential-aware Core fetch", () => {
  beforeEach(() => {
    authRuntime.resetForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
  });

  it("includes credentials on every request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.health();
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
  });

  it("does not send CSRF on GET in session mode", async () => {
    authRuntime.setSession({
      csrfToken: "csrf-1",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.health();
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.has(CSRF_HEADER_NAME)).toBe(false);
  });

  it("sends CSRF on session mutations and preserves Content-Type", async () => {
    authRuntime.setSession({
      csrfToken: "csrf-mutate",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: "r1", summary: "s", scope: "full", format: "json", redaction_profile: "standard", generated_at: "t" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.createReport({ scope: "full", format: "json", redaction: { profile: "standard" } });
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get(CSRF_HEADER_NAME)).toBe("csrf-mutate");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.has("Origin")).toBe(false);
  });

  it("omits CSRF for trusted_local mutations", async () => {
    authRuntime.setTrustedLocal(false);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ deleted: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api.deleteReport("r1");
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.has(CSRF_HEADER_NAME)).toBe(false);
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
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe(`Bearer ${SENTINEL_TOKEN}`);
    expect(headers.has(CSRF_HEADER_NAME)).toBe(false);
    expect(headers.has("Origin")).toBe(false);
    expect(init.credentials).toBe("include");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeUndefined();
  });

  it("blocks session mutation when CSRF is missing without sending the request", async () => {
    authRuntime.setSession({
      csrfToken: "temp",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    // Empty CSRF keeps session method but cannot be applied to headers.
    authRuntime.setSession({
      csrfToken: "",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.deleteReport("r1")).rejects.toMatchObject({ kind: "csrf" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps CSRF 403 and Origin 403 kinds without retry", async () => {
    authRuntime.setSession({
      csrfToken: "csrf-1",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
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
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Authentication required." }, 401));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not treat public session-status 401 as protected unauthorized", async () => {
    const listener = vi.fn();
    authRuntime.onUnauthorized(listener);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Authentication required." }, 401));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      coreFetch("api/auth/session", {}, undefined, { intent: "public_session_status" }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
  });

  it("logout DELETE sends CSRF in session mode", async () => {
    authRuntime.setSession({
      csrfToken: "csrf-logout",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await deleteBrowserSession();
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get(CSRF_HEADER_NAME)).toBe("csrf-logout");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "DELETE",
      credentials: "include",
    });
  });

  it("covers every unsafe api method through mutation transport", async () => {
    authRuntime.setSession({
      csrfToken: "csrf-all",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
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

    await api.createReport({ scope: "full", format: "json", redaction: { profile: "standard" } });
    await api.deleteReport("r1");
    await api.captureTopology("home");

    expect(__unsafeApiMethodsForTests.length).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(call[1]?.headers);
      expect(headers.get(CSRF_HEADER_NAME)).toBe("csrf-all");
      expect(call[1]?.credentials).toBe("include");
    }
  });
});

describe("report download helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
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
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("api/reports/rep-1/download");
    expect(url).not.toMatch(/[?&](token|access_token|csrf)=/);
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.has("Authorization")).toBe(false);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
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
    authRuntime.setSession({
      csrfToken: "csrf-dl",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
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
    authRuntime.setSession({
      csrfToken: "csrf-stale",
      expiresAt: futureExpiry(),
      browserSessionEnabled: true,
    });
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
