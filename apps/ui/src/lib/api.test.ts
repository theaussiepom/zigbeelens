import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { api, ApiError } from "./api";
import type { DeviceStoryDto } from "@/types/devices";

const sampleDeviceStory: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0x03",
  status: "watch",
  priority: "low",
  headline_code: "topology_evidence_gap",
  reasons: [{ code: "latest_snapshot_no_links", params: {} }],
  evidence: [
    {
      source: "topology_snapshot",
      id: "snap-latest",
      captured_at: "2026-07-13T02:00:00Z",
      label: null,
    },
  ],
  limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
  suggested_checks: [{ code: "compare_earlier_snapshot", params: {} }],
  coverage: [
    {
      dimension: "route_hints",
      state: "not_observed",
      label_code: "route_hints_unavailable",
      params: {},
    },
  ],
  timeline: [],
};

describe("deviceStory API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("accepts the full Device Story DTO shape", () => {
    const story: DeviceStoryDto = sampleDeviceStory;
    expect(story.timeline).toEqual([]);
    expect(story.reasons[0]?.code).toBe("latest_snapshot_no_links");
  });

  it("calls the device story endpoint with encoded path segments", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleDeviceStory), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.deviceStory("home", "0x03");
    expect(result).toEqual(sampleDeviceStory);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("api/devices/home/0x03/story");
    expect(url).not.toContain("scenario=");
  });

  it("omits scenario query when scenario is undefined", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleDeviceStory), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.deviceStory("home", "0x03");
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).not.toMatch(/[?&]scenario=/);
  });

  it("includes scenario query when provided and keeps path encoding", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleDeviceStory), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.deviceStory("home/net", "0xab/cd", "offline_cluster");
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain(`api/devices/${encodeURIComponent("home/net")}/${encodeURIComponent("0xab/cd")}/story`);
    expect(url).toContain("scenario=offline_cluster");
  });

  it("returns Device Story JSON unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(sampleDeviceStory), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deviceStory("home", "0x03")).resolves.toEqual(sampleDeviceStory);
  });

  it("propagates 404 through the existing API error handling path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("missing", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deviceStory("home", "0xmissing")).rejects.toBeInstanceOf(ApiError);
    await expect(api.deviceStory("home", "0xmissing")).rejects.toMatchObject({ status: 404 });
  });

  it("is only fetched from the Device Story drawer section", () => {
    const srcRoot = join(import.meta.dirname, "..");
    const componentRoots = ["components", "pages", "hooks"];
    const allowedPaths = new Set([
      join(srcRoot, "components/meshGraph/DeviceStorySection.tsx"),
    ]);
    const offenders: string[] = [];

    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        const path = join(dir, entry);
        if (statSync(path).isDirectory()) {
          walk(path);
          continue;
        }
        if (!/\.(tsx|ts)$/.test(entry) || entry.endsWith(".test.ts") || entry.endsWith(".test.tsx")) {
          continue;
        }
        const content = readFileSync(path, "utf8");
        if (content.includes("api.deviceStory") && !allowedPaths.has(path)) {
          offenders.push(path);
        }
      }
    };

    for (const root of componentRoots) {
      walk(join(srcRoot, root));
    }

    expect(offenders).toEqual([]);
  });
});

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
