import { describe, expect, it } from "vitest";
import { topologyRequestedByLabel, topologyStatusLabel } from "@/lib/topologyLabels";

describe("topologyRequestedByLabel", () => {
  it("humanises known request sources", () => {
    expect(topologyRequestedByLabel("startup_scan")).toBe("Startup scan");
    expect(topologyRequestedByLabel("manual_refresh")).toBe("Manual refresh");
    expect(topologyRequestedByLabel("manual_user_capture")).toBe("Manual refresh");
    expect(topologyRequestedByLabel("scheduled_refresh")).toBe("Scheduled refresh");
    expect(topologyRequestedByLabel("periodic_refresh")).toBe("Scheduled refresh");
  });

  it("falls back for unknown or empty values", () => {
    expect(topologyRequestedByLabel(null)).toBe("Unknown");
    expect(topologyRequestedByLabel("custom_source")).toBe("Custom Source");
  });
});

describe("topologyStatusLabel", () => {
  it("humanises snapshot status values", () => {
    expect(topologyStatusLabel("complete")).toBe("Complete");
    expect(topologyStatusLabel("pending")).toBe("Pending");
    expect(topologyStatusLabel("error")).toBe("Error");
    expect(topologyStatusLabel(null)).toBe("Unknown");
  });
});
