import { describe, expect, it } from "vitest";
import type {
  CoverageLabelCode,
  DecisionBadge,
  DecisionCountSummary,
  DecisionPriority,
  DecisionStatus,
  Incident,
  LegacyStoredReportBody,
  ReportDetailV3,
} from "@zigbeelens/shared";
import { parseIncident } from "@/lib/decisionContract";
import { buildIncidentRecordViewModel } from "@/viewModels/incidents/incidentViewModel";
import { buildIncidentDetailViewModel } from "@/viewModels/incidents/incidentDetailViewModel";

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

  it("types Incident nullability exactly as Core and parseIncident accept", () => {
    const openIncident: Incident = {
      id: "inc-nullability",
      type: "single_device_unavailable",
      status: "open",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      title: "Nullability alignment",
      summary: "Open incident with explicit nulls.",
      interpretation: "Recorded interpretation.",
      network_ids: ["home"],
      affected_device_count: 1,
      affected_devices: [
        {
          network_id: "home",
          ieee_address: "0x1",
          friendly_name: "Kitchen Sensor",
          decision: {
            status: "worth_reviewing",
            priority: "medium",
            headline_code: "current_issue_present",
            coverage_label_codes: [],
          },
        },
      ],
      opened_at: "2026-01-01T00:00:00+00:00",
      updated_at: "2026-01-01T01:00:00+00:00",
      resolved_at: null,
      evidence: [
        {
          id: "e1",
          kind: "availability",
          summary: "Device marked offline",
          detail: null,
          timestamp: null,
          network_id: null,
          ieee_address: null,
        },
      ],
      counter_evidence: [],
      limitations: [{ id: "l1", summary: "No topology", detail: null }],
      timeline: [
        {
          id: "t1",
          timestamp: "2026-01-01T00:00:00+00:00",
          kind: "incident_opened",
          severity: "incident",
          title: "Opened",
          summary: "Incident opened",
          network_id: null,
          ieee_address: null,
          friendly_name: null,
          incident_id: null,
        },
      ],
      conclusion: {
        classification: "single_device_unavailable",
        severity: "incident",
        scope: "device",
        confidence: "medium",
        summary: "Open incident with explicit nulls.",
        evidence: [],
        counter_evidence: [],
        limitations: [],
      },
    };

    const resolvedIncident: Incident = {
      ...openIncident,
      id: "inc-resolved",
      status: "resolved",
      resolved_at: "2026-01-02T00:00:00+00:00",
    };

    expect(parseIncident(openIncident)).toEqual(openIncident);
    expect(parseIncident(resolvedIncident)).toEqual(resolvedIncident);
    expect(buildIncidentRecordViewModel(openIncident).lifecycle).toBe("open");
    expect(buildIncidentRecordViewModel(resolvedIncident).lifecycle).toBe("resolved");
    expect(buildIncidentDetailViewModel(openIncident).record.id).toBe("inc-nullability");
    expect(buildIncidentDetailViewModel(resolvedIncident).record.resolvedExact).toBeTruthy();
    expect(openIncident.resolved_at).toBeNull();
    expect(resolvedIncident.resolved_at).toBe("2026-01-02T00:00:00+00:00");
  });
});
