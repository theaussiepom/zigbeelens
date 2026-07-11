import { describe, expect, it } from "vitest";
import {
  REASON_CODES,
  coverageLabel,
  decisionStatusCompactLabel,
  decisionStatusLabel,
  decisionStatusTone,
  isKnownReasonCode,
  reasonText,
} from "@/viewModels/decisionCopy";

describe("decisionCopy", () => {
  it("maps seeded reason codes to user-facing text", () => {
    expect(reasonText("latest_snapshot_no_links")).toBe(
      "Latest snapshot shows no links for this device.",
    );
    expect(
      reasonText("selected_snapshot_had_links", {
        selected_snapshot_link_count: 6,
      }),
    ).toBe("Selected snapshot showed 6 links for this device.");
    expect(reasonText("availability_tracking_off")).toBe(
      "Availability tracking was off for the selected period.",
    );
  });

  it("falls back safely for unknown reason codes", () => {
    expect(reasonText("not_a_real_code")).toBe(
      "Details unavailable (not_a_real_code).",
    );
    expect(isKnownReasonCode("battery_low")).toBe(true);
    expect(isKnownReasonCode("not_a_real_code")).toBe(false);
  });

  it("maps required coverage labels", () => {
    expect(coverageLabel("availability_tracking_off")).toBe(
      "Availability tracking off",
    );
    expect(coverageLabel("availability_history_building")).toBe(
      "Availability history building",
    );
    expect(coverageLabel("availability_status_unknown")).toBe(
      "Availability status unknown",
    );
    expect(coverageLabel("route_hints_unavailable")).toBe(
      "Route hints unavailable",
    );
    expect(coverageLabel("ha_areas_not_linked")).toBe("HA areas not linked");
    expect(coverageLabel("snapshot_stale")).toBe("Snapshot stale");
    expect(coverageLabel("battery_history_sparse")).toBe("Battery history sparse");
    expect(coverageLabel("lqi_history_sparse")).toBe("LQI history sparse");
  });

  it("maps decision status labels and tones deterministically", () => {
    expect(decisionStatusLabel("worth_reviewing")).toBe("Worth reviewing");
    expect(decisionStatusCompactLabel("no_notable_change")).toBe("Similar");
    expect(decisionStatusTone("worth_reviewing")).toBe("action");
    expect(decisionStatusTone("improve_data_coverage")).toBe("coverage");
    expect(decisionStatusTone("informational")).toBe("info");
  });

  it("keeps backend reason codes unique in the frontend seed set", () => {
    const unique = new Set(REASON_CODES);
    expect(unique.size).toBe(REASON_CODES.length);
  });
});
