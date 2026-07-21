import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReportSummary } from "@zigbeelens/shared";

const scenarioState = vi.hoisted(() => {
  let scenario = "";
  const listeners = new Set<() => void>();
  return {
    get: () => scenario,
    set: (next: string) => {
      scenario = next;
      listeners.forEach((listener) => listener());
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    reset: () => {
      scenario = "";
    },
  };
});

vi.mock("@/context/ScenarioContext", async () => {
  const React = await import("react");
  return {
    useScenario: () => {
      const [, setTick] = React.useState(0);
      React.useEffect(
        () => scenarioState.subscribe(() => setTick((value) => value + 1)),
        [],
      );
      return { scenario: scenarioState.get() };
    },
  };
});

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
  downloadStoredReport: vi.fn(async () => ({
    blob: new Blob(["{}"], { type: "application/json" }),
    filename: "report.json",
    contentType: "application/json",
    authGeneration: 1,
  })),
  triggerBrowserDownload: vi.fn(async () => {}),
  writeProtectedClipboardText: vi.fn(async (text: string) => {
    await navigator.clipboard.writeText(text);
  }),
  ApiError: class ApiError extends Error {},
}));

import {
  api,
  downloadStoredReport,
  triggerBrowserDownload,
  writeProtectedClipboardText,
} from "@/lib/api";
import { ReportsPage } from "./ReportsPage";

const listReports = api.listReports as Mock;
const previewReport = api.previewReport as Mock;
const createReport = api.createReport as Mock;
const deleteReport = api.deleteReport as Mock;
const reportDetail = api.report as Mock;
const networks = api.networks as Mock;
const devices = api.devices as Mock;
const incidents = api.incidents as Mock;

function makeStored(overrides: Partial<ReportSummary> = {}): ReportSummary {
  return {
    id: "rep-1",
    generated_at: "2026-07-21T00:32:00Z",
    redaction_applied: true,
    incident_count: 0,
    device_count: 2,
    network_count: 1,
    summary: "Network report summary",
    format: "json",
    scope: "network",
    redaction_profile: "standard",
    ...overrides,
  };
}

function makePreview() {
  return {
    id: "preview",
    product: "ZigbeeLens",
    report_version: 3,
    format: "json",
    scope: "full",
    version: "test",
    markdown_summary: "# Full preview",
    limitations: [],
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
      subject_count: 2,
      status_counts: { no_notable_change: 2 },
      coverage_warning_count: 0,
    },
    generated_at: "2026-07-21T00:00:00Z",
    device_stories: [],
    investigation_priorities: [],
    data_coverage_warnings: [],
    incidents: [],
    collector_status: {},
    config_summary: {},
    domain_details: { networks: [{}], devices: [{}, {}], device_details: [], router_risks: [] },
    events_or_timeline: [],
    raw_counts: { networks_included: 1, devices_included: 2, incidents_included: 0 },
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  scenarioState.reset();
  vi.clearAllMocks();
  listReports.mockResolvedValue([]);
  previewReport.mockResolvedValue(makePreview());
  createReport.mockResolvedValue(makeStored({ id: "rep-new", scope: "full" }));
  deleteReport.mockResolvedValue(undefined);
  reportDetail.mockResolvedValue({
    report_version: 3,
    markdown_summary: "# stored",
  });
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(async () => {}) },
    configurable: true,
  });
});

describe("ReportsPage saved history", () => {
  it("mounts with listReports only — no target discovery or preview", async () => {
    renderPage();
    await waitFor(() => expect(listReports).toHaveBeenCalledTimes(1));
    expect(networks).not.toHaveBeenCalled();
    expect(devices).not.toHaveBeenCalled();
    expect(incidents).not.toHaveBeenCalled();
    expect(previewReport).not.toHaveBeenCalled();
  });

  it("leads with Saved reports and Create full report", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create full report" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Saved reports")).toBeInTheDocument();
    expect(screen.queryByText("Report type")).not.toBeInTheDocument();
    expect(screen.queryByText("Choose a target")).not.toBeInTheDocument();
  });

  it("shows empty guidance without target pickers", async () => {
    renderPage();
    expect(await screen.findByText("No saved reports yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/Create reports from a device, incident, network, or Mesh investigation/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Network")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Incident")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Device")).not.toBeInTheDocument();
  });

  it("opens a fixed full-scope dialog and previews once", async () => {
    renderPage();
    await screen.findByText("No saved reports yet.");
    fireEvent.click(screen.getAllByRole("button", { name: "Create full report" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: /create full evidence report/i });
    expect(within(dialog).getAllByText("Full ZigbeeLens evidence").length).toBeGreaterThan(0);
    await waitFor(() => expect(previewReport).toHaveBeenCalledTimes(1));
    expect(previewReport).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: "full",
        network_id: null,
        incident_id: null,
        device: null,
      }),
      undefined,
    );
  });

  it("creates a v3 full report and refreshes saved list", async () => {
    listReports.mockResolvedValueOnce([]).mockResolvedValue([makeStored({ id: "rep-new", scope: "full" })]);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Create full report" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    await waitFor(() => expect(createReport).toHaveBeenCalledTimes(1));
    expect(createReport.mock.calls[0]![0]).toMatchObject({
      scope: "full",
      format: "json",
    });
    expect(createReport.mock.calls[0]![0].report_version).toBeUndefined();
    await waitFor(() => expect(listReports.mock.calls.length).toBeGreaterThan(1));
  });

  it("renders stored rows with accessible actions", async () => {
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    expect(await screen.findByText("Network report summary")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Download network JSON report generated/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Copy Markdown from network report generated/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Delete network report generated/i }),
    ).toBeInTheDocument();
  });

  it("downloads via credentialed stored-report helper", async () => {
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /Download network JSON report generated/i }),
    );
    await waitFor(() => expect(downloadStoredReport).toHaveBeenCalledWith("rep-1", undefined));
    expect(triggerBrowserDownload).toHaveBeenCalled();
  });

  it("copies stored markdown with protected clipboard", async () => {
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /Copy Markdown from network report generated/i }),
    );
    await waitFor(() => expect(reportDetail).toHaveBeenCalledWith("rep-1", undefined));
    expect(writeProtectedClipboardText).toHaveBeenCalled();
  });

  it("requires delete confirmation and retains the row on failure", async () => {
    listReports.mockResolvedValue([makeStored()]);
    deleteReport.mockRejectedValueOnce(new Error("nope"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Delete network report generated/i }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(deleteReport).toHaveBeenCalledWith("rep-1"));
    expect(screen.getByText("Network report summary")).toBeInTheDocument();
  });

  it("uses ordinal accessible names when human context collides", async () => {
    const row = makeStored();
    listReports.mockResolvedValue([
      row,
      { ...row, id: "rep-2" },
    ]);
    renderPage();
    expect(
      await screen.findByRole("button", {
        name: /Download network JSON report generated .*, item 1 of 2/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Download network JSON report generated .*, item 2 of 2/i,
      }),
    ).toBeInTheDocument();
  });

  it("source contract: no target pickers or mount-time discovery in ReportsPage", () => {
    const source = readFileSync(
      path.join(__dirname, "ReportsPage.tsx"),
      "utf8",
    );
    expect(source).not.toMatch(/api\.networks\(/);
    expect(source).not.toMatch(/api\.devices\(/);
    expect(source).not.toMatch(/api\.incidents\(/);
    expect(source).not.toMatch(/previewReport/);
    expect(source).not.toMatch(/Report type/);
    expect(source).not.toMatch(/Select a network/);
    expect(source).not.toMatch(/Select an incident/);
    expect(source).not.toMatch(/Select a device/);
    expect(source).toMatch(/listReports/);
    expect(source).toMatch(/Create full report/);
    expect(source).toMatch(/ContextualReportDialog/);
  });
});
