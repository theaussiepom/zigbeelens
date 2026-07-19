import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import {
  isDecisionPriority,
  isDecisionStatus,
  parseDecisionBadge,
  parseDecisionCountSummary,
  parseDeviceSummary,
  validateDashboardPayload,
} from "@/lib/decisionContract";

describe("decisionContract", () => {
  it("accepts a valid decision badge", () => {
    expect(
      parseDecisionBadge({
        status: "review_first",
        priority: "high",
        headline_code: "current_issue_present",
        coverage_label_codes: ["availability_tracking_off"],
      }),
    ).toEqual({
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: ["availability_tracking_off"],
    });
  });

  it("rejects a missing decision badge as protocol failure", () => {
    expect(() => parseDecisionBadge(null)).toThrow(ApiError);
    try {
      parseDecisionBadge(null);
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).kind).toBe("protocol");
    }
  });

  it("rejects malformed decision summary count maps", () => {
    expect(() =>
      parseDecisionCountSummary({
        subject_count: 2,
        overall_status: "watch",
        highest_priority: "low",
        status_counts: { watch: 1 },
        priority_counts: { low: 2 },
        coverage_warning_count: 0,
      }),
    ).toThrow(ApiError);
  });

  it("rejects devices missing required decision fields", () => {
    expect(() =>
      parseDeviceSummary({
        network_id: "home",
        ieee_address: "0x1",
        friendly_name: "Sensor",
        device_type: "EndDevice",
        power_source: "Battery",
        availability: "online",
        interview_state: "successful",
        incident_affected: false,
      }),
    ).toThrow(ApiError);
  });

  it("validates dashboard decision summaries and network badges", () => {
    const payload = validateDashboardPayload({
      generated_at: "2026-07-06T12:00:00+00:00",
      active_incident_count: 0,
      watching_incident_count: 0,
      network_count: 1,
      device_count: 0,
      unavailable_device_count: 0,
      networks: [
        {
          id: "home",
          name: "Home",
          base_topic: "zigbee2mqtt",
          bridge_state: "online",
          device_count: 0,
          router_count: 0,
          end_device_count: 0,
          unavailable_count: 0,
          active_incident_severity: null,
          active_incident_count: 0,
          recent_bridge_warnings: 0,
          recent_bridge_errors: 0,
          decision: {
            status: "no_notable_change",
            priority: "none",
            headline_code: "network_no_notable_change",
            coverage_label_codes: [],
          },
          decision_summary: {
            subject_count: 0,
            overall_status: "no_notable_change",
            highest_priority: "none",
            status_counts: {},
            priority_counts: {},
            coverage_warning_count: 0,
          },
        },
      ],
      router_risks: [],
      recent_timeline: [],
      decision_summary: {
        subject_count: 0,
        overall_status: "no_notable_change",
        highest_priority: "none",
        status_counts: {},
        priority_counts: {},
        coverage_warning_count: 0,
      },
      shared_availability_events: [],
      model_patterns: [],
      investigation_priorities: [],
      data_coverage_warnings: [],
    });

    expect(payload.networks[0].decision.status).toBe("no_notable_change");
  });

  it("exports closed canonical unions", () => {
    expect(isDecisionStatus("review_first")).toBe(true);
    expect(isDecisionStatus("future_status_v2")).toBe(false);
    expect(isDecisionPriority("high")).toBe(true);
    expect(isDecisionPriority("urgent")).toBe(false);
  });
});
