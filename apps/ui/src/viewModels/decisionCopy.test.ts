import { describe, expect, it } from "vitest";
import {
  COVERAGE_LABEL_CODES,
  REASON_CODES,
  coverageHelperText,
  coverageLabel,
  deviceCoverageHelperText,
  deviceCoverageLabel,
  decisionStatusCompactLabel,
  decisionStatusLabel,
  decisionStatusTone,
  headlineText,
  isKnownCoverageLabelCode,
  isKnownHeadlineCode,
  isKnownLimitationCode,
  isKnownReasonCode,
  isKnownSuggestedCheckCode,
  limitationText,
  reasonText,
  suggestedCheckText,
} from "@/viewModels/decisionCopy";

const SPECULATIVE_FUTURE_REASON_CODES = [
  "router_area_issue_cluster",
  "model_pattern_observed",
] as const;

const PHASE_4B_REASON_CODES = [
  "observed_reporting_rhythm",
  "reporting_silence_beyond_expected",
] as const;

const PHASE_4D_REASON_CODES = [
  "observed_lqi_trend",
  "reported_lqi_declining",
] as const;

const PHASE_4D_HEADLINE_CODES = ["reported_link_quality_changed"] as const;

const PHASE_4D_LIMITATION_CODES = ["reported_lqi_not_path_failure"] as const;

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
    expect(reasonText("availability_tracking_off")).toBe("Availability tracking is off.");
    expect(reasonText("availability_history_building")).toBe(
      "Availability history is still building.",
    );
    expect(reasonText("availability_status_unknown")).toBe(
      "Availability status could not be confirmed from stored evidence.",
    );
    for (const text of [
      reasonText("availability_tracking_off"),
      reasonText("availability_history_building"),
      reasonText("availability_status_unknown"),
    ]) {
      expect(text.toLowerCase()).not.toContain("selected period");
      expect(text.toLowerCase()).not.toContain("selected snapshot");
    }
  });

  it("falls back safely for unknown reason codes without exposing internal codes", () => {
    expect(reasonText("not_a_real_code")).toBe("Details unavailable.");
    expect(reasonText("router_area_issue_cluster")).toBe("Details unavailable.");
    expect(isKnownReasonCode("battery_low")).toBe(true);
    expect(isKnownReasonCode("not_a_real_code")).toBe(false);
  });

  it("keeps speculative future reason codes out of the Phase 1 seed set", () => {
    for (const code of SPECULATIVE_FUTURE_REASON_CODES) {
      expect(REASON_CODES).not.toContain(code);
      expect(isKnownReasonCode(code)).toBe(false);
    }
  });

  it("maps Phase 4B reporting rhythm reason codes without failure claims", () => {
    for (const code of PHASE_4B_REASON_CODES) {
      expect(isKnownReasonCode(code)).toBe(true);
    }
    expect(
      reasonText("observed_reporting_rhythm", {
        interval_minutes_p25: 60,
        interval_minutes_median: 60,
        interval_minutes_p75: 60,
        interval_minutes_max: 60,
      }),
    ).toBe("Usually reports about every 1 hour based on stored payload history.");
    expect(
      reasonText("observed_reporting_rhythm", {
        interval_minutes_p25: 40,
        interval_minutes_median: 60,
        interval_minutes_p75: 90,
        interval_minutes_max: 1080,
      }),
    ).toBe(
      "Usually reports every 40 minutes–1 hour 30 minutes based on stored payload history.",
    );
    expect(
      reasonText("reporting_silence_beyond_expected", {
        silence_minutes: 240,
        extended_silence_threshold_minutes: 150,
      }),
    ).toBe("No payload observed for 4 hours.");
    expect(
      reasonText("reporting_silence_beyond_expected", {
        extended_silence_threshold_minutes: 150,
      }),
    ).toBe("Current payload silence is longer than the observed reporting cadence.");
    const phase4bReasonTexts = [
      reasonText("observed_reporting_rhythm", {
        interval_minutes_p25: 60,
        interval_minutes_median: 60,
        interval_minutes_p75: 60,
        interval_minutes_max: 60,
      }),
      reasonText("observed_reporting_rhythm", {
        interval_minutes_p25: 40,
        interval_minutes_median: 60,
        interval_minutes_p75: 90,
        interval_minutes_max: 1080,
      }),
      reasonText("reporting_silence_beyond_expected", {
        silence_minutes: 240,
        extended_silence_threshold_minutes: 150,
      }),
    ];
    for (const text of phase4bReasonTexts) {
      const lower = text.toLowerCase();
      expect(lower).not.toContain("failed");
      expect(lower).not.toContain("suspicious");
      expect(lower).not.toContain("threshold");
      expect(lower).not.toContain("multiplier");
      expect(lower).not.toContain("p75");
      expect(lower).not.toContain("median");
      expect(lower).not.toContain("suspicion");
    }
    expect(
      JSON.stringify({
        silence_minutes: 240,
        extended_silence_threshold_minutes: 150,
      }),
    ).not.toContain("suspicion_threshold_minutes");
  });

  it("maps Phase 4D LQI trend reason codes without path-failure claims", () => {
    for (const code of PHASE_4D_REASON_CODES) {
      expect(isKnownReasonCode(code)).toBe(true);
    }
    expect(
      reasonText("observed_lqi_trend", {
        earlier_median: 180,
        recent_median: 80,
        delta: -100,
        sample_count: 50,
        window_size: 3,
        latest_value: 80,
      }),
    ).toBe(
      "Reported link quality median changed from 180 to 80 across the compared stored observation windows.",
    );
    expect(reasonText("observed_lqi_trend", {})).toBe(
      "Stored reported link-quality observations show a trend across compared observation windows.",
    );
    expect(reasonText("reported_lqi_declining")).toBe(
      "Reported link quality is lower in the recent stored observations.",
    );
    const phase4dReasonTexts = [
      reasonText("observed_lqi_trend", {
        earlier_median: 180,
        recent_median: 80,
      }),
      reasonText("reported_lqi_declining"),
    ];
    for (const text of phase4dReasonTexts) {
      const lower = text.toLowerCase();
      expect(lower).not.toContain("route failure");
      expect(lower).not.toContain("path failure");
      expect(lower).not.toContain("rf interference");
      expect(lower).not.toContain("network degradation");
    }
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

  it("maps Phase 4C per-device coverage labels with params", () => {
    expect(deviceCoverageLabel("availability_tracking_off")).toBe("Availability: tracking off");
    expect(deviceCoverageLabel("availability_history_building")).toBe("Availability: building");
    expect(deviceCoverageLabel("availability_status_unknown")).toBe("Availability: unknown");
    expect(deviceCoverageLabel("availability_available")).toBe("Availability: available");
    expect(deviceCoverageLabel("last_seen_available")).toBe("Last seen: available");
    expect(
      deviceCoverageLabel("topology_history_sparse", {
        observed_snapshot_count: 2,
        snapshot_window_count: 10,
      }),
    ).toBe("Topology history: 2 of 10 snapshots");
    expect(deviceCoverageLabel("ha_area_linked", { area_name: "Hall" })).toBe("HA area: Hall");
    expect(deviceCoverageLabel("ha_area_linked", { area_id: "hall" })).toBe("HA area: hall");
    expect(deviceCoverageLabel("ha_areas_not_linked")).toBe("HA area: missing");
    expect(coverageLabel("ha_areas_not_linked")).toBe("HA areas not linked");
    expect(
      deviceCoverageLabel("ha_area_linked", { area_id: "hall", area_name: "Hall" }),
    ).toBe("HA area: Hall");
    expect(deviceCoverageHelperText("ha_area_linked", { area_id: "hall" })).toMatch(
      /area id hall/i,
    );
    expect(deviceCoverageHelperText("ha_area_linked", { area_id: "hall" })).not.toMatch(
      /area_name/i,
    );
  });

  it("maps device availability helper copy without network tracking wording", () => {
    const helper = deviceCoverageHelperText("availability_history_building");
    expect(helper).toMatch(/this device/i);
    expect(helper.toLowerCase()).not.toContain("turned on");
    expect(helper.toLowerCase()).not.toContain("recently enabled");
  });

  it("maps device HA not-linked helper copy", () => {
    const helper = deviceCoverageHelperText("ha_areas_not_linked");
    expect(helper).toMatch(/this device/i);
    expect(helper).toMatch(/not a zigbee network fault/i);
  });

  it("maps device topology helper copy by snapshot window", () => {
    expect(
      deviceCoverageHelperText("topology_history_not_observed", {
        observed_snapshot_count: 0,
        snapshot_window_count: 0,
      }),
    ).toBe("No complete stored topology snapshots are available to assess this device yet.");
    expect(
      deviceCoverageHelperText("topology_history_not_observed", {
        observed_snapshot_count: 0,
        snapshot_window_count: 10,
      }),
    ).toMatch(/not observed in the considered stored topology snapshots/i);
    expect(
      deviceCoverageHelperText("topology_history_sparse", {
        observed_snapshot_count: 2,
        snapshot_window_count: 10,
      }),
    ).toMatch(/absent from some considered stored topology snapshots/i);
    expect(
      deviceCoverageHelperText("topology_history_available", {
        observed_snapshot_count: 10,
        snapshot_window_count: 10,
      }),
    ).toMatch(/appeared in every considered stored topology snapshot/i);
  });

  it("falls back safely for unknown coverage label codes", () => {
    expect(coverageLabel("future_backend_label")).toBe("Coverage status unknown");
    expect(coverageHelperText("future_backend_label")).toMatch(
      /interpret other evidence conservatively/i,
    );
    expect(isKnownCoverageLabelCode("availability_tracking_off")).toBe(true);
    expect(isKnownCoverageLabelCode("future_backend_label")).toBe(false);
    expect(COVERAGE_LABEL_CODES.length).toBeGreaterThan(0);
  });

  it("maps required coverage helper text", () => {
    expect(coverageHelperText("availability_tracking_off")).toMatch(/zigbee2mqtt availability/i);
    expect(coverageHelperText("route_hints_unavailable")).toMatch(
      /does not mean routes are absent/i,
    );
    expect(coverageHelperText("ha_areas_not_linked")).toMatch(/not a zigbee network fault/i);
    expect(coverageHelperText("ha_areas_not_linked").toLowerCase()).not.toContain(
      "for this device",
    );
    expect(coverageHelperText("snapshot_stale")).toMatch(/configured capture cadence/i);
  });

  it("maps decision status labels and tones deterministically", () => {
    expect(decisionStatusLabel("worth_reviewing")).toBe("Worth reviewing");
    expect(decisionStatusCompactLabel("no_notable_change")).toBe("Similar");
    expect(decisionStatusTone("worth_reviewing")).toBe("action");
    expect(decisionStatusTone("improve_data_coverage")).toBe("coverage");
    expect(decisionStatusTone("informational")).toBe("info");
  });

  it("falls back safely for unknown decision statuses", () => {
    expect(decisionStatusLabel("future_status")).toBe("Status unknown");
    expect(decisionStatusCompactLabel("future_status")).toBe("Unknown");
    expect(decisionStatusTone("future_status")).toBe("muted");
    expect(decisionStatusLabel("toString")).toBe("Status unknown");
    expect(decisionStatusCompactLabel("toString")).toBe("Unknown");
    expect(decisionStatusTone("toString")).toBe("muted");
  });

  it("keeps backend reason codes unique in the frontend seed set", () => {
    const unique = new Set(REASON_CODES);
    expect(unique.size).toBe(REASON_CODES.length);
  });

  it("maps device story headline codes", () => {
    expect(headlineText("topology_evidence_gap")).toBe("Topology evidence gap");
    expect(headlineText("current_issue_present")).toBe("Current issue needs attention");
    expect(headlineText("extended_reporting_silence")).toBe("Extended reporting silence");
    for (const code of PHASE_4D_HEADLINE_CODES) {
      expect(isKnownHeadlineCode(code)).toBe(true);
    }
    expect(headlineText("reported_link_quality_changed")).toBe("Reported link quality changed");
    expect(isKnownHeadlineCode("topology_evidence_gap")).toBe(true);
    expect(isKnownHeadlineCode("extended_reporting_silence")).toBe(true);
    expect(headlineText("future_headline")).toBe("Device story summary unavailable.");
  });

  it("maps device story limitation codes", () => {
    expect(limitationText("absence_from_latest_not_failure")).toMatch(
      /does not prove the device failed/i,
    );
    expect(limitationText("extended_silence_not_failure")).toMatch(
      /does not prove the device failed/i,
    );
    expect(limitationText("route_hints_not_live_routing")).toMatch(/do not prove live routing/i);
    expect(isKnownLimitationCode("absence_from_latest_not_failure")).toBe(true);
    expect(isKnownLimitationCode("extended_silence_not_failure")).toBe(true);
    for (const code of PHASE_4D_LIMITATION_CODES) {
      expect(isKnownLimitationCode(code)).toBe(true);
    }
    expect(limitationText("reported_lqi_not_path_failure")).toBe(
      "A drop in reported link quality does not prove a Zigbee path, route, or device failure.",
    );
    expect(limitationText("future_limitation")).toMatch(/interpretation is limited/i);
  });

  it("maps device story suggested check codes", () => {
    expect(suggestedCheckText("compare_earlier_snapshot")).toMatch(/earlier topology snapshot/i);
    expect(suggestedCheckText("check_battery_level", { battery_percent: 12 })).toBe(
      "Check the reported battery level (12%).",
    );
    expect(isKnownSuggestedCheckCode("confirm_powered")).toBe(true);
    expect(suggestedCheckText("future_check")).toMatch(/review stored evidence/i);
  });
});
