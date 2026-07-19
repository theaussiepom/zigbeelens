import { describe, expect, it } from "vitest";
import type {
  DataCoverageWarningSummary,
  InvestigationPrioritySummary,
  ReportDetail,
  ReportDeviceStory,
} from "@zigbeelens/shared";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import { buildInvestigationPriorityViewModel } from "@/viewModels/overview/investigationPriorityViewModel";
import { buildDataCoverageWarningViewModel } from "@/viewModels/overview/dataCoverageViewModel";
import { decisionStatusLabel } from "@/viewModels/decisionCopy";
import {
  REPORT_LEGACY_NOTICE,
  buildReportDecisionViewModel,
} from "./reportDecisionViewModel";

function baseReport(overrides: Partial<ReportDetail> = {}): ReportDetail {
  return {
    id: "report-preview",
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
    decision_summary: {
      subject_count: 1,
      overall_status: "watch",
      highest_priority: "low",
      status_counts: { watch: 1 },
      priority_counts: { low: 1 },
      coverage_warning_count: 0,
    },
    config_summary: { mode: "mock" },
    collector_status: {},
    domain_details: {
      networks: [
        {
          id: "home",
          name: "Home",
          base_topic: "zigbee2mqtt/home",
        },
      ] as NonNullable<ReportDetail["domain_details"]>["networks"],
      devices: [],
      device_details: [],
      router_risks: [],
      topology_snapshot_count: 0,
    },
    incidents: [],
    events_or_timeline: [],
    limitations: [],
    raw_counts: {
      events_included: 0,
      devices_included: 1,
      incidents_included: 0,
    },
    markdown_summary: "# ZigbeeLens Evidence Report",
    ...overrides,
  } as ReportDetail;
}

function makeStory(overrides: Partial<ReportDeviceStory> = {}): ReportDeviceStory {
  return {
    network_id: "home",
    ieee_address: "0x03",
    friendly_name: "Kitchen plug",
    subject_type: "device",
    subject_id: "0x03",
    status: "watch",
    priority: "low",
    headline_code: "topology_evidence_gap",
    reasons: [{ code: "latest_snapshot_no_links", params: {} }],
    evidence: [
      {
        source: "topology_snapshot",
        id: "snap-latest",
        captured_at: "2026-07-13T02:00:00Z",
      },
    ],
    limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
    suggested_checks: [{ code: "compare_earlier_snapshot", params: {} }],
    coverage: [
      {
        dimension: "route_hints",
        state: "not_observed",
        label_code: "route_hints_unavailable",
        params: {},
      },
    ],
    timeline: [],
    ...overrides,
  };
}

function makePriority(
  overrides: Partial<InvestigationPrioritySummary> = {},
): InvestigationPrioritySummary {
  return {
    id: "priority-1",
    network_id: "home",
    card_type: "shared_availability_event",
    priority: "Review first",
    score: 12,
    action_group: "investigate_shared_event",
    title: "Several devices went offline around the same time",
    summary: "11 devices went offline during a shared availability event.",
    device_ieees: ["0xd00"],
    ...overrides,
  };
}

function makeCoverageWarning(
  overrides: Partial<DataCoverageWarningSummary> = {},
): DataCoverageWarningSummary {
  return {
    id: "cov-1",
    network_id: "home",
    dimension: "route_hints",
    state: "not_observed",
    label_code: "route_hints_unavailable",
    scope_type: "network",
    params: {},
    ...overrides,
  };
}

describe("reportDecisionViewModel", () => {
  it("keeps Device Story fields aligned with buildDeviceStoryViewModel", () => {
    const story = makeStory();
    const report = baseReport({
      device_stories: [story],
      decision_summary: {
        device_story_count: 1,
        status_counts: { watch: 1 },
        priority_counts: { low: 1 },
      },
    });
    const vm = buildReportDecisionViewModel(report);
    const direct = buildDeviceStoryViewModel({
      subject_type: "device",
      subject_id: story.subject_id,
      status: story.status,
      priority: story.priority,
      headline_code: story.headline_code,
      reasons: story.reasons,
      evidence: story.evidence,
      limitations: story.limitations,
      suggested_checks: story.suggested_checks,
      coverage: story.coverage,
      timeline: story.timeline,
    });

    expect(vm.deviceStories).toHaveLength(1);
    expect(vm.deviceStories[0]!.story).toEqual(direct);
    expect(vm.deviceStories[0]!.name).toBe("Kitchen plug");
    expect(vm.deviceStories[0]!.story.headline).toBe("Topology evidence gap");
    expect(vm.deviceStories[0]!.story.reasons).toEqual(direct.reasons);
    expect(vm.deviceStories[0]!.story.limitations).toEqual(direct.limitations);
    expect(vm.deviceStories[0]!.story.suggestedChecks).toEqual(direct.suggestedChecks);
    expect(vm.deviceStories[0]!.story.coverageItems[0]!.label).toBe(
      "Route hints unavailable",
    );
  });

  it("keeps investigation priority fields aligned with buildInvestigationPriorityViewModel", () => {
    const priority = makePriority();
    const report = baseReport({
      investigation_priorities: [priority],
      device_stories: [makeStory()],
    });
    const vm = buildReportDecisionViewModel(report);
    const direct = buildInvestigationPriorityViewModel(priority, "Home");

    expect(vm.investigationPriorities).toHaveLength(1);
    expect(vm.investigationPriorities[0]).toEqual(direct);
    expect(JSON.stringify(vm.investigationPriorities[0])).not.toContain(
      "investigate_shared_event",
    );
  });

  it("keeps data coverage fields aligned with buildDataCoverageWarningViewModel", () => {
    const warning = makeCoverageWarning();
    const report = baseReport({
      data_coverage_warnings: [warning],
      device_stories: [makeStory()],
    });
    const vm = buildReportDecisionViewModel(report);
    const direct = buildDataCoverageWarningViewModel(warning, "Home");

    expect(vm.networkCoverage).toHaveLength(1);
    expect(vm.networkCoverage[0]).toEqual(direct);
    expect(vm.networkCoverage[0]!.title).toBe("Route hints unavailable");
  });

  it("maps decision summary counts with human labels and stable ordering", () => {
    const report = baseReport({
      decision_summary: {
        device_story_count: 4,
        status_counts: {
          informational: 1,
          review_first: 2,
          future_status_code: 1,
        },
        priority_counts: {},
      },
      device_stories: [
        makeStory({ status: "review_first", friendly_name: "A" }),
        makeStory({ ieee_address: "0x04", friendly_name: "B", status: "informational" }),
      ],
    });
    const vm = buildReportDecisionViewModel(report);

    expect(vm.decisionSummaryItems.map((item) => item.label)).toEqual([
      decisionStatusLabel("review_first"),
      decisionStatusLabel("informational"),
      "Status unknown",
    ]);
    expect(vm.decisionSummaryItems.map((item) => item.key)).toEqual([
      "review_first",
      "informational",
      "future_status_code",
    ]);
  });

  it("marks version 1 reports as legacy without reinterpreting decision sections", () => {
    const report = baseReport({
      report_version: 1,
      summary: {
        overall_state: "incident",
        current_finding: "Legacy finding text",
        networks_monitored: 2,
        total_devices: 10,
        active_incidents: 1,
        watching_incidents: 0,
        unavailable_devices: 4,
        router_risks: 1,
        stale_devices: 0,
        weak_links: 0,
        low_battery_devices: 0,
      },
      decision_summary: null,
      device_stories: [],
      investigation_priorities: [],
      data_coverage_warnings: [],
    });
    const vm = buildReportDecisionViewModel(report);

    expect(vm.isLegacyFormat).toBe(true);
    expect(vm.legacyNotice).toBe(REPORT_LEGACY_NOTICE);
    expect(vm.decisionSummaryItems).toEqual([]);
    expect(vm.deviceStories).toEqual([]);
    expect(vm.investigationPriorities).toEqual([]);
    expect(vm.networkCoverage).toEqual([]);
    expect(vm.markdown).toContain("ZigbeeLens");
  });

  it("marks stored v2 reports as legacy even when decision sections exist", () => {
    const report = baseReport({
      report_version: 2,
    });
    const vm = buildReportDecisionViewModel(report);
    expect(vm.isLegacyFormat).toBe(true);
    expect(vm.legacyNotice).toBe(REPORT_LEGACY_NOTICE);
    expect(vm.decisionSummaryItems).toEqual([]);
  });

  it("sorts device stories by decision rank then friendly name", () => {
    const report = baseReport({
      device_stories: [
        makeStory({
          ieee_address: "0x02",
          friendly_name: "Zebra",
          status: "informational",
        }),
        makeStory({
          ieee_address: "0x01",
          friendly_name: "Alpha",
          status: "review_first",
        }),
        makeStory({
          ieee_address: "0x03",
          friendly_name: "Beta",
          status: "review_first",
        }),
      ],
      decision_summary: {
        device_story_count: 3,
        status_counts: { review_first: 2, informational: 1 },
        priority_counts: {},
      },
    });
    const vm = buildReportDecisionViewModel(report);
    expect(vm.deviceStories.map((item) => item.name)).toEqual(["Alpha", "Beta", "Zebra"]);
  });

  it("derives network labels only from report.networks and enables Mesh when preserved", () => {
    const report = baseReport({
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
      domain_details: {
        networks: [
          { id: "home", name: "Home From Report", base_topic: "zigbee2mqtt/home" },
        ] as NonNullable<ReportDetail["domain_details"]>["networks"],
        devices: [],
        device_details: [],
        router_risks: [],
        topology_snapshot_count: 0,
      },
      investigation_priorities: [makePriority()],
      data_coverage_warnings: [makeCoverageWarning()],
      device_stories: [makeStory()],
    });
    const vm = buildReportDecisionViewModel(report);
    expect(vm.meshNavigationAvailable).toBe(true);
    expect(vm.investigationPriorities[0]!.networkLabel).toBe("Home From Report");
    expect(vm.investigationPriorities[0]!.meshHref).toBe("/topology/home");
    expect(vm.networkCoverage[0]!.networkLabel).toBe("Home From Report");
  });

  it("disables Mesh navigation when network names are anonymised", () => {
    const report = baseReport({
      redaction: {
        applied: true,
        profile: "public_safe",
        mqtt_credentials: true,
        secrets: true,
        hostnames: true,
        ip_addresses: true,
        ieee_addresses_hashed: true,
        friendly_names: "labeled",
        network_names: "labeled",
      },
      domain_details: {
        networks: [
          { id: "network_001", name: "network_001", base_topic: "topic_001" },
        ] as NonNullable<ReportDetail["domain_details"]>["networks"],
        devices: [],
        device_details: [],
        router_risks: [],
        topology_snapshot_count: 0,
      },
      investigation_priorities: [
        makePriority({ network_id: "network_001", title: "Anon priority" }),
      ],
      data_coverage_warnings: [
        makeCoverageWarning({ network_id: "network_001" }),
      ],
      device_stories: [makeStory({ network_id: "network_001" })],
    });
    const vm = buildReportDecisionViewModel(report);
    expect(vm.meshNavigationAvailable).toBe(false);
    expect(vm.investigationPriorities[0]!.networkLabel).toBe("network_001");
    expect(JSON.stringify(vm)).not.toContain('"home"');
  });
});
