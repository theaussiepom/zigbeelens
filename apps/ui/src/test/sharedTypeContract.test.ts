import { describe, expect, it } from "vitest";
import type {
  CoverageLabelCode,
  DecisionBadge,
  DecisionCountSummary,
  DecisionPriority,
  DecisionStatus,
  LegacyStoredReportBody,
  ReportDetailV3,
} from "@zigbeelens/shared";

describe("shared decision contract", () => {
  it("types DecisionBadge with canonical unions", () => {
    const badge: DecisionBadge = {
      status: "watch",
      priority: "medium",
      headline_code: "stale_last_seen",
      coverage_label_codes: ["availability_tracking_off"],
    };
    const status: DecisionStatus = badge.status;
    const priority: DecisionPriority = badge.priority;
    const label: CoverageLabelCode = badge.coverage_label_codes[0];
    expect(status).toBe("watch");
    expect(priority).toBe("medium");
    expect(label).toBe("availability_tracking_off");
  });

  it("types DecisionCountSummary with canonical status and priority maps", () => {
    const summary: DecisionCountSummary = {
      subject_count: 2,
      overall_status: "worth_reviewing",
      highest_priority: "high",
      status_counts: { worth_reviewing: 2 },
      priority_counts: { high: 2 },
      coverage_warning_count: 1,
    };
    expect(summary.status_counts.worth_reviewing).toBe(2);
  });

  it("separates exact v3 reports from opaque legacy bodies", () => {
    const current: ReportDetailV3 = {
      id: "report-1",
      product: "ZigbeeLens",
      report_version: 3,
      generated_at: "2026-06-14T15:30:00+00:00",
      version: "0.1.0",
      scope: "full",
      format: "json",
      redaction: {
        applied: true,
        profile: "standard",
        mqtt_credentials: true,
        secrets: true,
        hostnames: false,
        ip_addresses: false,
        ieee_addresses_hashed: true,
        friendly_names: "preserved",
        network_names: "preserved",
      },
      config_summary: {},
      decision_summary: {
        subject_count: 0,
        overall_status: "data_unavailable",
        highest_priority: "none",
        status_counts: {},
        priority_counts: {},
        coverage_warning_count: 0,
      },
      investigation_priorities: [],
      device_stories: [],
      data_coverage_warnings: [],
      incidents: [],
      collector_status: {},
      domain_details: {
        networks: [],
        devices: [],
        device_details: [],
        router_risks: [],
        topology_snapshot_count: 0,
      },
      events_or_timeline: [],
      limitations: [],
      raw_counts: {},
      markdown_summary: "",
    };

    const legacy: LegacyStoredReportBody = {
      report_version: 1,
      summary: { current_finding: "Legacy finding" },
    };

    expect(current.report_version).toBe(3);
    expect(legacy.summary).toEqual({ current_finding: "Legacy finding" });
    expect("domain_details" in legacy).toBe(false);
  });
});
