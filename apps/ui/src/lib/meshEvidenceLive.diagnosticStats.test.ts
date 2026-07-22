import { describe, expect, it } from "vitest";
import { diagnosticStatsFor } from "@/lib/meshEvidenceLive";

describe("diagnosticStatsFor snapshots-with-links", () => {
  it("omits the snapshots-with-links row when the device has no device_stats entry", () => {
    const stats = diagnosticStatsFor({
      summary: undefined,
      neighborCount: 0,
      layoutAvailable: false,
      strongestLiveLqi: null,
      recentMissingCount: null,
      backendStats: undefined,
      backendWindow: { days: 7, max_snapshots: 30, snapshots_considered: 4 },
      nameFor: (ieee) => ieee,
    });
    expect(stats.some((row) => row.label.startsWith("Snapshots with links"))).toBe(false);
    expect(stats.map((row) => row.value).join(" ")).not.toMatch(/\b0 of 4\b/);
  });

  it("renders measured zero when an explicit device_stats entry reports zero links", () => {
    const stats = diagnosticStatsFor({
      summary: undefined,
      neighborCount: 0,
      layoutAvailable: false,
      strongestLiveLqi: null,
      recentMissingCount: null,
      backendStats: {
        snapshots_with_links: 0,
        offline_events_24h: 0,
        offline_events_7d: 0,
      },
      backendWindow: { days: 7, max_snapshots: 30, snapshots_considered: 4 },
      nameFor: (ieee) => ieee,
    });
    const row = stats.find((item) => item.label.startsWith("Snapshots with links"));
    expect(row?.value).toBe("0 of 4");
  });

  it("renders positive measured snapshots-with-links counts", () => {
    const stats = diagnosticStatsFor({
      summary: undefined,
      neighborCount: 0,
      layoutAvailable: false,
      strongestLiveLqi: null,
      recentMissingCount: null,
      backendStats: {
        snapshots_with_links: 2,
        offline_events_24h: 0,
        offline_events_7d: 0,
      },
      backendWindow: { days: 7, max_snapshots: 30, snapshots_considered: 5 },
      nameFor: (ieee) => ieee,
    });
    const row = stats.find((item) => item.label.startsWith("Snapshots with links"));
    expect(row?.value).toBe("2 of 5");
  });
});
