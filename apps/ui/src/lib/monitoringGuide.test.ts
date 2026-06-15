import { describe, expect, it } from "vitest";
import { deviceHealthRows, incidentRules } from "@/lib/monitoringGuide";

describe("monitoringGuide", () => {
  it("embeds configured thresholds in device rules", () => {
    const rows = deviceHealthRows({ flapping_threshold: 5, weak_link_threshold: 30 });
    const unstable = rows.find((r) => r.label === "recently_unstable");
    expect(unstable?.condition).toContain("5");
    const weak = rows.find((r) => r.label === "weak_link");
    expect(weak?.condition).toContain("30");
  });

  it("includes lifecycle timing in incident rules", () => {
    const rules = incidentRules({
      incident_watch_window_minutes: 45,
      incident_resolution_grace_minutes: 10,
    });
    const lifecycle = rules.find((r) => r.type === "_lifecycle");
    expect(lifecycle?.trigger).toContain("45+10");
  });
});
