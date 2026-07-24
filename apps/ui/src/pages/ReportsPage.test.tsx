import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const liveEvents = vi.hoisted(() => {
  const listeners = new Set<(eventName: string) => void>();
  return {
    emit: (eventName: string) => {
      for (const listener of listeners) listener(eventName);
    },
    subscribe: (listener: (eventName: string) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    reset: () => listeners.clear(),
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

vi.mock("@/lib/events", () => ({
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT:
    "home_assistant_enrichment_updated",
  liveConnection: {
    subscribeEvents: (listener: (e: string) => void) => liveEvents.subscribe(listener),
    subscribeState: () => () => {},
    getState: () => "open",
    isAccessEnabled: () => true,
  },
  LIVE_EVENTS: [],
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
  liveEvents.reset();
  vi.clearAllMocks();
  vi.useRealTimers();
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

afterEach(() => {
  vi.useRealTimers();
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

  it("explains current evidence snapshots without promising legacy report compatibility", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Reports" });
    const explanation = screen.getByText(/Reports are generated from ZigbeeLens/).parentElement;
    expect(explanation).toHaveTextContent("evidence-backed snapshots, not root-cause proof");
    expect(explanation).toHaveTextContent("redacted before any report is stored or downloaded");
    expect(explanation).toHaveTextContent(
      "Historical snapshot evidence is included when available",
    );
    expect(explanation).toHaveTextContent("Saved reports use the current report format");
    expect(explanation).not.toHaveTextContent(/legacy v1\/v2/i);
    expect(explanation).not.toHaveTextContent(/downloadable as originally saved/i);
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
      screen.getByRole("button", { name: /Copy Markdown from network JSON report generated/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Delete network JSON report generated/i }),
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
      await screen.findByRole("button", {
        name: /Copy Markdown from network JSON report generated/i,
      }),
    );
    await waitFor(() => expect(reportDetail).toHaveBeenCalledWith("rep-1", undefined));
    expect(writeProtectedClipboardText).toHaveBeenCalled();
  });

  it("does not copy when report detail fails protocol (non-v3)", async () => {
    listReports.mockResolvedValue([makeStored()]);
    reportDetail.mockRejectedValueOnce(
      Object.assign(new Error("Core returned a malformed decision contract."), {
        kind: "protocol",
      }),
    );
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Copy Markdown from network JSON report generated/i,
      }),
    );
    await waitFor(() => expect(reportDetail).toHaveBeenCalled());
    expect(writeProtectedClipboardText).not.toHaveBeenCalled();
  });

  it("does not copy an empty Markdown string", async () => {
    listReports.mockResolvedValue([makeStored()]);
    reportDetail.mockResolvedValueOnce({ report_version: 3, markdown_summary: "   " });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Copy Markdown from network JSON report generated/i,
      }),
    );
    expect(
      await screen.findByText("Markdown summary is not available for this stored report."),
    ).toBeInTheDocument();
    expect(writeProtectedClipboardText).not.toHaveBeenCalled();
  });

  it("requires delete confirmation and retains the row on failure", async () => {
    listReports.mockResolvedValue([makeStored()]);
    deleteReport.mockRejectedValueOnce(new Error("nope"));
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /Delete network JSON report generated/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(deleteReport).toHaveBeenCalledWith("rep-1"));
    expect(screen.getByText("Network report summary")).toBeInTheDocument();
  });

  it("uses group-local ordinal accessible names when human context collides", async () => {
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

  it("keeps saved rows visible when a background refresh fails", async () => {
    listReports.mockResolvedValueOnce([makeStored()]);
    renderPage();
    expect(await screen.findByText("Network report summary")).toBeInTheDocument();
    listReports.mockRejectedValueOnce(new Error("refresh failed"));
    vi.useFakeTimers();
    await act(async () => {
      liveEvents.emit("reports_updated");
      await vi.advanceTimersByTimeAsync(400);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("Network report summary")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Saved reports could not be refreshed. Showing the last loaded list.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading reports…")).not.toBeInTheDocument();
    vi.useRealTimers();
    listReports.mockResolvedValueOnce([makeStored({ id: "rep-2", summary: "Refreshed" })]);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Refreshed")).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Saved reports could not be refreshed. Showing the last loaded list.",
      ),
    ).not.toBeInTheDocument();
  });

  it("shows refresh failure for an accepted empty list and recovers on Retry", async () => {
    listReports.mockResolvedValueOnce([]);
    renderPage();
    expect(await screen.findByText("No saved reports yet.")).toBeInTheDocument();
    listReports.mockRejectedValueOnce(new Error("refresh failed"));
    vi.useFakeTimers();
    await act(async () => {
      liveEvents.emit("reports_updated");
      await vi.advanceTimersByTimeAsync(400);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("No saved reports yet.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Saved reports could not be refreshed. Showing the last loaded list.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
    vi.useRealTimers();
    listReports.mockResolvedValueOnce([makeStored({ id: "rep-new", summary: "After retry" })]);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("After retry")).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Saved reports could not be refreshed. Showing the last loaded list.",
      ),
    ).not.toBeInTheDocument();
  });

  it("uses per-report busy ownership across concurrent rows and actions", async () => {
    let resolveA!: () => void;
    let resolveB!: () => void;
    const download = downloadStoredReport as Mock;
    download.mockImplementation((id: string) => {
      return new Promise((resolve) => {
        const done = () =>
          resolve({
            blob: new Blob(["{}"], { type: "application/json" }),
            filename: `${id}.json`,
            contentType: "application/json",
            authGeneration: 1,
          });
        if (id === "rep-1") resolveA = done;
        else resolveB = done;
      });
    });
    listReports.mockResolvedValue([
      makeStored({ id: "rep-1", summary: "Report A" }),
      makeStored({ id: "rep-2", summary: "Report B" }),
    ]);
    renderPage();
    const downloadA = await screen.findByRole("button", {
      name: /Download network JSON report generated .*Report A/i,
    });
    const downloadB = screen.getByRole("button", {
      name: /Download network JSON report generated .*Report B/i,
    });
    fireEvent.click(downloadA);
    fireEvent.click(downloadB);
    await waitFor(() => expect(download).toHaveBeenCalledTimes(2));
    expect(downloadA).toBeDisabled();
    expect(downloadB).toBeDisabled();
    // Same-report cross-action blocked while A download is pending.
    fireEvent.click(
      screen.getByRole("button", { name: /Copy Markdown from network JSON report generated .*Report A/i }),
    );
    expect(reportDetail).not.toHaveBeenCalled();
    // Second activation of B remains blocked.
    fireEvent.click(downloadB);
    expect(download).toHaveBeenCalledTimes(2);
    resolveA!();
    await waitFor(() => expect(downloadA).not.toBeDisabled());
    expect(downloadB).toBeDisabled();
    resolveB!();
    await waitFor(() => expect(downloadB).not.toBeDisabled());
  });

  it("refuses a second Confirm delete while delete is pending", async () => {
    let resolveDelete!: () => void;
    deleteReport.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDelete = resolve;
        }),
    );
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /Delete network JSON report generated/i }),
    );
    const confirm = screen.getByRole("button", { name: "Confirm delete" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(deleteReport).toHaveBeenCalledTimes(1));
    expect(confirm).toBeDisabled();
    resolveDelete!();
    await waitFor(() => expect(listReports.mock.calls.length).toBeGreaterThan(1));
  });

  it("blocks copy while download is pending for the same report", async () => {
    let resolveDownload!: () => void;
    (downloadStoredReport as Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDownload = () =>
            resolve({
              blob: new Blob(["{}"], { type: "application/json" }),
              filename: "report.json",
              contentType: "application/json",
              authGeneration: 1,
            });
        }),
    );
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /Download network JSON report generated/i }),
    );
    await waitFor(() => expect(downloadStoredReport).toHaveBeenCalledTimes(1));
    fireEvent.click(
      screen.getByRole("button", { name: /Copy Markdown from network JSON report generated/i }),
    );
    expect(reportDetail).not.toHaveBeenCalled();
    resolveDownload!();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Download network JSON report generated/i }),
      ).not.toBeDisabled(),
    );
  });

  it("returns focus to the empty-state launcher", async () => {
    listReports.mockResolvedValue([]);
    renderPage();
    await screen.findByText("No saved reports yet.");
    const buttons = screen.getAllByRole("button", { name: "Create full report" });
    const emptyLauncher = buttons[buttons.length - 1]!;
    fireEvent.click(emptyLauncher);
    await screen.findByRole("dialog");
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(emptyLauncher).toHaveFocus());
  });

  it("returns focus to the header launcher", async () => {
    listReports.mockResolvedValue([makeStored()]);
    renderPage();
    await screen.findByText("Network report summary");
    const header = screen.getAllByRole("button", { name: "Create full report" })[0]!;
    fireEvent.click(header);
    await screen.findByRole("dialog");
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(header).toHaveFocus());
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
