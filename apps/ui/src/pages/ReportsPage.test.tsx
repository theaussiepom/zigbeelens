import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type {
  DataCoverageWarningSummary,
  InvestigationPrioritySummary,
  ReportDetail,
  ReportDeviceStory,
  ReportSummary,
} from "@zigbeelens/shared";
import { buildDeviceStoryViewModel } from "@/viewModels/topology/deviceStoryViewModel";
import { limitationText, reasonText, suggestedCheckText } from "@/viewModels/decisionCopy";

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({ scenario: "" }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    networks: vi.fn(),
    incidents: vi.fn(),
    devices: vi.fn(),
    previewReport: vi.fn(),
    createReport: vi.fn(),
    listReports: vi.fn(),
    report: vi.fn(),
    deleteReport: vi.fn(),
  },
  downloadReportUrl: vi.fn(() => "/api/reports/r1/download"),
  ApiError: class ApiError extends Error {},
}));

import { api } from "@/lib/api";
import { ReportsPage } from "./ReportsPage";

const previewReport = api.previewReport as Mock;
const createReport = api.createReport as Mock;
const listReports = api.listReports as Mock;

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
    evidence: [],
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

function makeLegacyReport(): ReportDetail {
  return {
    id: "report-preview",
    product: "ZigbeeLens",
    report_version: 1,
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
    summary: {
      overall_state: "incident",
      current_finding: "4 devices became unavailable on Home2.",
      networks_monitored: 2,
      total_devices: 164,
      active_incidents: 1,
      watching_incidents: 0,
      unavailable_devices: 4,
      router_risks: 1,
      stale_devices: 3,
      weak_links: 6,
      low_battery_devices: 2,
    },
    config_summary: {},
    collector: {},
    networks: [],
    devices: [],
    device_details: [],
    router_risks: [],
    incidents: [],
    timeline: [],
    health_snapshot: {
      timestamp: "2026-06-14T15:30:00+00:00",
      overall_severity: "incident",
      overall_health: "unavailable",
      network_count: 2,
      device_count: 164,
      unavailable_count: 4,
      incident_count: 1,
      networks: [],
    },
    diagnostic_conclusions: [],
    limitations: [{ id: "lim-root", summary: "ZigbeeLens does not prove root cause." }],
    raw_counts: { events_included: 10, devices_included: 164, incidents_included: 1 },
    markdown_summary: "# ZigbeeLens diagnostic report\n\nGenerated: 2026-06-14",
  };
}

function makeDecisionReport(overrides: Partial<ReportDetail> = {}): ReportDetail {
  const story = makeStory();
  return {
    ...makeLegacyReport(),
    report_version: 2,
    summary: null,
    decision_summary: {
      device_story_count: 1,
      status_counts: { watch: 1 },
      priority_counts: { low: 1 },
    },
    investigation_priorities: [makePriority()],
    device_stories: [story],
    data_coverage_warnings: [makeCoverageWarning()],
    networks: [{ id: "home", name: "Home", base_topic: "zigbee2mqtt/home" }],
    raw_counts: { events_included: 0, devices_included: 1, incidents_included: 0 },
    markdown_summary: "# ZigbeeLens evidence report\n\nGenerated: 2026-06-14",
    ...overrides,
  };
}

function makeStored(): ReportSummary {
  return {
    id: "r1",
    generated_at: "2026-06-14T15:30:00+00:00",
    redaction_applied: true,
    incident_count: 1,
    device_count: 164,
    network_count: 2,
    summary: "4 devices became unavailable on Home2.",
    format: "json",
    scope: "full",
    redaction_profile: "standard",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (api.networks as Mock).mockResolvedValue({
    items: [{ id: "home", name: "Home", base_topic: "zigbee2mqtt/home" }],
    total: 1,
  });
  (api.incidents as Mock).mockResolvedValue({ items: [], total: 0, limit: 100, next_cursor: null });
  (api.devices as Mock).mockResolvedValue({ items: [], total: 0 });
  previewReport.mockResolvedValue(makeDecisionReport());
  createReport.mockResolvedValue(makeStored());
  listReports.mockResolvedValue([]);
});

function renderReportsPage() {
  return render(
    <MemoryRouter>
      <ReportsPage />
    </MemoryRouter>,
  );
}

describe("ReportsPage", () => {
  it("renders scope, format, and profile selector controls", async () => {
    renderReportsPage();
    expect(screen.getByText("Full evidence")).toBeInTheDocument();
    expect(screen.getByText("JSON")).toBeInTheDocument();
    expect(screen.getByText("YAML")).toBeInTheDocument();
    expect(screen.getByText("Public safe")).toBeInTheDocument();
    expect(screen.getByText("Strict")).toBeInTheDocument();
    await screen.findByText("Topology evidence gap");
  });

  it("shows the secret-redaction safety notice", async () => {
    renderReportsPage();
    expect(screen.getByText(/not root-cause proof/i)).toBeInTheDocument();
    expect(screen.getByText(/are redacted before any/i)).toBeInTheDocument();
    await screen.findByText("Topology evidence gap");
  });

  it("previews decision report sections and preserves summary actions", async () => {
    renderReportsPage();
    expect(await screen.findByText("Topology evidence gap")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate & store report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download json/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy markdown summary/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download markdown/i })).toBeInTheDocument();
  });

  it("renders device stories with reasons, limitations, checks, and coverage", async () => {
    const story = makeStory();
    const storyVm = buildDeviceStoryViewModel({
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

    renderReportsPage();
    const deviceStory = await screen.findByTestId("report-device-story");

    expect(within(deviceStory).getByText(storyVm.reasons[0]!)).toBeInTheDocument();
    expect(within(deviceStory).getByText(storyVm.limitations[0]!)).toBeInTheDocument();
    expect(within(deviceStory).getByText(storyVm.suggestedChecks[0]!)).toBeInTheDocument();
    expect(within(deviceStory).getByText("Route hints unavailable")).toBeInTheDocument();
    expect(within(deviceStory).getByText(reasonText("latest_snapshot_no_links", {}))).toBeInTheDocument();
    expect(within(deviceStory).getByText(limitationText("absence_from_latest_not_failure", {}))).toBeInTheDocument();
    expect(within(deviceStory).getByText(suggestedCheckText("compare_earlier_snapshot", {}))).toBeInTheDocument();
  });

  it("does not render SeverityBadge or legacy health stats as the primary preview", async () => {
    renderReportsPage();
    await screen.findByText("Topology evidence gap");

    expect(screen.queryByText("Router risks")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Unavailable$/)).not.toBeInTheDocument();
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
    expect(screen.queryByText("Weak links")).not.toBeInTheDocument();
    expect(screen.queryByText("Low battery")).not.toBeInTheDocument();
    expect(screen.queryByText("4 devices became unavailable on Home2.")).not.toBeInTheDocument();
    expect(document.querySelector('[data-severity]')).toBeNull();
  });

  it("shows legacy notice for version 1 reports while keeping markdown and actions", async () => {
    previewReport.mockResolvedValue(makeLegacyReport());
    renderReportsPage();

    expect(
      await screen.findByText(/earlier report format/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/ZigbeeLens diagnostic report/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate & store report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy markdown summary/i })).toBeInTheDocument();
    expect(screen.queryByText("Router risks")).not.toBeInTheDocument();
    expect(screen.queryByText("4 devices became unavailable on Home2.")).not.toBeInTheDocument();
  });

  it("does not leak unknown decision codes in the preview", async () => {
    previewReport.mockResolvedValue(
      makeDecisionReport({
        device_stories: [
          makeStory({
            status: "future_story_status",
            headline_code: "future_headline_code",
            reasons: [{ code: "future_reason_code", params: {} }],
            limitations: [{ code: "future_limitation_code", params: {} }],
            suggested_checks: [{ code: "future_check_code", params: {} }],
            coverage: [
              {
                dimension: "route_hints",
                state: "not_observed",
                label_code: "future_coverage_code",
                params: {},
              },
            ],
          }),
        ],
        decision_summary: {
          device_story_count: 1,
          status_counts: { future_story_status: 1 },
          priority_counts: {},
        },
      }),
    );

    renderReportsPage();
    await screen.findByTestId("report-device-story");

    const preview = document.querySelector('[data-testid="report-device-story"]');
    expect(preview?.textContent ?? "").not.toContain("future_story_status");
    expect(preview?.textContent ?? "").not.toContain("future_headline_code");
    expect(preview?.textContent ?? "").not.toContain("future_reason_code");
    expect(preview?.textContent ?? "").not.toContain("future_limitation_code");
    expect(preview?.textContent ?? "").not.toContain("future_check_code");
    expect(preview?.textContent ?? "").not.toContain("future_coverage_code");
    expect(within(preview!).getByText("Status unknown")).toBeInTheDocument();
  });

  it("re-requests the preview when the redaction profile changes", async () => {
    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    fireEvent.click(screen.getByText("Public safe"));
    await waitFor(() => {
      const profiles = previewReport.mock.calls.map((c) => c[0].redaction.profile);
      expect(profiles).toContain("public_safe");
    });
  });

  it("generates a report via the API", async () => {
    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    fireEvent.click(screen.getByRole("button", { name: /generate & store report/i }));
    await waitFor(() => expect(createReport).toHaveBeenCalled());
  });

  it("copies the markdown summary", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    fireEvent.click(screen.getByRole("button", { name: /copy markdown summary/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("ZigbeeLens")));
  });

  it("renders stored reports with a download link", async () => {
    listReports.mockResolvedValue([makeStored()]);
    renderReportsPage();
    expect(await screen.findByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/api/reports/r1/download",
    );
  });

  it("shows an empty state when there are no stored reports", async () => {
    renderReportsPage();
    expect(await screen.findByText(/no stored reports yet/i)).toBeInTheDocument();
  });

  it("does not switch on review_first, current_finding, or lens interpretation in source", () => {
    const source = readFileSync(
      path.resolve(import.meta.dirname, "./ReportsPage.tsx"),
      "utf8",
    );

    expect(source).not.toMatch(/review_first/);
    expect(source).not.toMatch(/current_finding/);
    expect(source).not.toMatch(/overall_state/);
    expect(source).not.toMatch(/health_summary/);
    expect(source).not.toMatch(/lens_bucket/);
    expect(source).not.toMatch(/SeverityBadge/);
    expect(source).not.toMatch(/router_risks/);
    expect(source).not.toMatch(/unavailable_devices/);
    expect(source).not.toMatch(/selectors\.data\?\.networks/);
    expect(source).toMatch(/buildReportDecisionViewModel\(report\)/);
  });

  it("loads selector inventories lazily by selected scope", async () => {
    const networks = api.networks as Mock;
    const incidents = api.incidents as Mock;
    const devices = api.devices as Mock;

    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    expect(previewReport).toHaveBeenCalled();
    expect(networks).not.toHaveBeenCalled();
    expect(incidents).not.toHaveBeenCalled();
    expect(devices).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Network"));
    await waitFor(() => expect(networks).toHaveBeenCalled());
    expect(incidents).not.toHaveBeenCalled();
    expect(devices).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Incident"));
    await waitFor(() => expect(incidents).toHaveBeenCalledTimes(1));
    expect(devices).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Device"));
    await waitFor(() => expect(devices).toHaveBeenCalled());
  });

  it("loads one incident page and appends on Load more without auto-follow", async () => {
    const incidents = api.incidents as Mock;
    const page1 = [
      {
        id: "inc-1",
        title: "First incident",
        status: "open",
        type: "single_device_unavailable",
        severity: "incident",
        scope: "device",
        confidence: "medium",
        summary: "s",
        interpretation: "",
        network_ids: ["home"],
        affected_device_count: 0,
        affected_devices: [],
        opened_at: "2026-07-16T00:00:00Z",
        updated_at: "2026-07-16T00:00:00Z",
        evidence: [],
        counter_evidence: [],
        limitations: [],
        timeline: [],
        conclusion: {
          classification: "single_device_unavailable",
          severity: "incident",
          scope: "device",
          confidence: "medium",
          summary: "s",
          evidence: [],
          counter_evidence: [],
          limitations: [],
        },
      },
    ];
    const page2 = [
      {
        ...page1[0],
        id: "inc-2",
        title: "Second incident",
      },
      {
        ...page1[0],
        id: "inc-1",
        title: "First incident duplicate",
      },
    ];
    incidents
      .mockResolvedValueOnce({
        items: page1,
        total: 3,
        limit: 100,
        next_cursor: "cursor-page-2",
      })
      .mockResolvedValueOnce({
        items: page2,
        total: 3,
        limit: 100,
        next_cursor: null,
      });

    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    fireEvent.click(screen.getByText("Incident"));

    await waitFor(() => expect(incidents).toHaveBeenCalledTimes(1));
    expect(incidents.mock.calls[0]?.[0]).toMatchObject({ limit: 100 });
    expect(incidents.mock.calls[0]?.[0]?.cursor).toBeUndefined();

    // No automatic second page request.
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "First incident" })).toBeInTheDocument();
    });
    expect(incidents).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Incident"), { target: { value: "inc-1" } });
    expect(screen.getByLabelText("Incident")).toHaveValue("inc-1");

    fireEvent.click(screen.getByRole("button", { name: /load more incidents/i }));
    await waitFor(() => expect(incidents).toHaveBeenCalledTimes(2));
    expect(incidents.mock.calls[1]?.[0]).toMatchObject({
      limit: 100,
      cursor: "cursor-page-2",
    });

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Second incident" })).toBeInTheDocument();
    });
    // Duplicate ID from page 2 is not appended twice.
    expect(screen.getAllByRole("option", { name: /First incident/i })).toHaveLength(1);
    expect(screen.getByLabelText("Incident")).toHaveValue("inc-1");
    expect(screen.queryByRole("button", { name: /load more incidents/i })).not.toBeInTheDocument();
  });

  it("keeps existing incident options when a later page fails", async () => {
    const incidents = api.incidents as Mock;
    incidents
      .mockResolvedValueOnce({
        items: [
          {
            id: "inc-1",
            title: "Kept incident",
            status: "open",
            type: "single_device_unavailable",
            severity: "incident",
            scope: "device",
            confidence: "medium",
            summary: "s",
            interpretation: "",
            network_ids: ["home"],
            affected_device_count: 0,
            affected_devices: [],
            opened_at: "2026-07-16T00:00:00Z",
            updated_at: "2026-07-16T00:00:00Z",
            evidence: [],
            counter_evidence: [],
            limitations: [],
            timeline: [],
            conclusion: {
              classification: "single_device_unavailable",
              severity: "incident",
              scope: "device",
              confidence: "medium",
              summary: "s",
              evidence: [],
              counter_evidence: [],
              limitations: [],
            },
          },
        ],
        total: 2,
        limit: 100,
        next_cursor: "cursor-fail",
      })
      .mockRejectedValueOnce(new Error("page failed"));

    renderReportsPage();
    await screen.findByText("Topology evidence gap");
    fireEvent.click(screen.getByText("Incident"));
    await screen.findByRole("option", { name: "Kept incident" });

    fireEvent.click(screen.getByRole("button", { name: /load more incidents/i }));
    await waitFor(() => expect(screen.getByText("page failed")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Kept incident" })).toBeInTheDocument();
  });

  it("hides Mesh links for anonymised public_safe reports", async () => {
    previewReport.mockResolvedValue(
      makeDecisionReport({
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
        networks: [{ id: "network_001", name: "network_001", base_topic: "topic_001" }],
        investigation_priorities: [
          makePriority({ network_id: "network_001", title: "Anon priority title" }),
        ],
        data_coverage_warnings: [
          makeCoverageWarning({ network_id: "network_001" }),
        ],
        device_stories: [makeStory({ network_id: "network_001" })],
      }),
    );

    renderReportsPage();
    expect(await screen.findByText("Anon priority title")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /review mesh/i })).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain("/topology/network_001");
    expect(document.body.textContent ?? "").not.toMatch(/\bhome\b/);
  });

  it("keeps Mesh links for preserved-network reports", async () => {
    renderReportsPage();
    expect(await screen.findByText("Topology evidence gap")).toBeInTheDocument();
    const meshLinks = screen.getAllByRole("link", { name: /review mesh/i });
    expect(meshLinks.length).toBeGreaterThan(0);
    expect(meshLinks[0]).toHaveAttribute("href", "/topology/home");
  });
});
