import { describe, expect, it } from "vitest";
import type { ReportSummary } from "@zigbeelens/shared";
import { humanReportContextKey, savedReportActionName } from "./savedReportActionLabels";

const base: ReportSummary = {
  id: "rep-1",
  generated_at: "2026-07-21T00:32:00Z",
  redaction_applied: true,
  incident_count: 0,
  device_count: 1,
  network_count: 1,
  summary: "Kitchen",
  format: "json",
  scope: "network",
  redaction_profile: "standard",
};

describe("savedReportActionName", () => {
  it("builds contextual accessible names without opaque IDs", () => {
    const name = savedReportActionName("Download", base, {
      index: 0,
      total: 1,
      duplicateHumanContext: false,
    });
    expect(name).toMatch(/Download network JSON report generated/i);
    expect(name).not.toContain("rep-1");
  });

  it("adds ordinal fallback when human context collides", () => {
    const name = savedReportActionName("Delete", base, {
      index: 1,
      total: 3,
      duplicateHumanContext: true,
    });
    expect(name).toMatch(/item 2 of 3/);
  });

  it("keys duplicate human context without report id", () => {
    expect(humanReportContextKey(base)).not.toContain("rep-1");
    expect(humanReportContextKey(base)).toBe(
      humanReportContextKey({ ...base, id: "other" }),
    );
  });
});
