import { describe, expect, it } from "vitest";
import type { ReportSummary } from "@zigbeelens/shared";
import {
  assignSavedReportActionGroups,
  savedReportActionName,
  savedReportHumanContext,
} from "./savedReportActionLabels";

const base: ReportSummary = {
  id: "rep-1",
  generated_at: "2026-07-21T00:32:00.000Z",
  redaction_applied: true,
  incident_count: 0,
  device_count: 1,
  network_count: 1,
  summary: "Kitchen",
  format: "json",
  scope: "network",
  redaction_profile: "standard",
};

describe("savedReportHumanContext and action names", () => {
  it("builds contextual accessible names without opaque IDs", () => {
    const groups = assignSavedReportActionGroups([base]);
    const name = savedReportActionName("Download", base, groups[0]!);
    expect(name).toContain("Download");
    expect(name).toContain("network");
    expect(name).toContain("JSON");
    expect(name).toContain("standard");
    expect(name).toContain("Kitchen");
    expect(name).not.toContain("rep-1");
    expect(name).not.toMatch(/item \d+ of \d+/);
  });

  it("groups by formatted time so millisecond-only drift collides", () => {
    const a = base;
    const b = { ...base, id: "rep-2", generated_at: "2026-07-21T00:32:00.999Z" };
    const groups = assignSavedReportActionGroups([a, b]);
    expect(savedReportHumanContext(a)).toBe(savedReportHumanContext(b));
    expect(groups[0]).toEqual({ groupIndex: 0, groupSize: 2 });
    expect(groups[1]).toEqual({ groupIndex: 1, groupSize: 2 });
    expect(savedReportActionName("Delete", a, groups[0]!)).toMatch(/item 1 of 2/);
    expect(savedReportActionName("Delete", b, groups[1]!)).toMatch(/item 2 of 2/);
  });

  it("separates groups when summary or profile differs", () => {
    const sameTime = [
      base,
      { ...base, id: "rep-2", summary: "Other" },
      { ...base, id: "rep-3", redaction_profile: "strict" as const },
    ];
    const groups = assignSavedReportActionGroups(sameTime);
    expect(groups.every((g) => g.groupSize === 1)).toBe(true);
  });

  it("uses group-local ordinals when exact duplicates are separated by unrelated rows", () => {
    const rows = [
      base,
      { ...base, id: "rep-x", summary: "Unrelated", scope: "device" as const },
      { ...base, id: "rep-2" },
      { ...base, id: "rep-3" },
    ];
    const groups = assignSavedReportActionGroups(rows);
    expect(groups[0]).toEqual({ groupIndex: 0, groupSize: 3 });
    expect(groups[1]).toEqual({ groupIndex: 0, groupSize: 1 });
    expect(groups[2]).toEqual({ groupIndex: 1, groupSize: 3 });
    expect(groups[3]).toEqual({ groupIndex: 2, groupSize: 3 });
    const names = rows.map((r, i) =>
      savedReportActionName("Download", r, groups[i]!),
    );
    expect(new Set(names).size).toBe(4);
  });
});
