import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("fetchJson retry policy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("retries GET on transient 503", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("error", { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.health();
    expect(result.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry POST on transient 503", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("error", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api.createReport({ scope: "full", format: "json", redaction: { profile: "standard" } }),
    ).rejects.toThrow("503");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry DELETE on transient 503", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("error", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deleteReport("report-1")).rejects.toThrow("503");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry topology capture POST on transient 503", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("error", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.captureTopology("home")).rejects.toThrow("503");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
