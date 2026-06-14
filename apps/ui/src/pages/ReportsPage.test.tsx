import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReportDetail, ReportSummary } from "@zigbeelens/shared";

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

function makeReport(): ReportDetail {
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
  (api.networks as Mock).mockResolvedValue({ items: [], total: 0 });
  (api.incidents as Mock).mockResolvedValue({ items: [], total: 0 });
  (api.devices as Mock).mockResolvedValue({ items: [], total: 0 });
  previewReport.mockResolvedValue(makeReport());
  createReport.mockResolvedValue(makeStored());
  listReports.mockResolvedValue([]);
});

describe("ReportsPage", () => {
  it("renders scope, format, and profile selector controls", async () => {
    render(<ReportsPage />);
    expect(screen.getByText("Full diagnostic")).toBeInTheDocument();
    expect(screen.getByText("JSON")).toBeInTheDocument();
    expect(screen.getByText("YAML")).toBeInTheDocument();
    expect(screen.getByText("Public safe")).toBeInTheDocument();
    expect(screen.getByText("Strict")).toBeInTheDocument();
    await screen.findByText("4 devices became unavailable on Home2.");
  });

  it("shows the secret-redaction safety notice", async () => {
    render(<ReportsPage />);
    expect(screen.getByText(/not root-cause proof/i)).toBeInTheDocument();
    expect(screen.getByText(/are redacted before any/i)).toBeInTheDocument();
    await screen.findByText("4 devices became unavailable on Home2.");
  });

  it("previews the report and shows summary actions", async () => {
    render(<ReportsPage />);
    expect(await screen.findByText("4 devices became unavailable on Home2.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate & store report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download json/i })).toBeInTheDocument();
  });

  it("re-requests the preview when the redaction profile changes", async () => {
    render(<ReportsPage />);
    await screen.findByText("4 devices became unavailable on Home2.");
    fireEvent.click(screen.getByText("Public safe"));
    await waitFor(() => {
      const profiles = previewReport.mock.calls.map((c) => c[0].redaction.profile);
      expect(profiles).toContain("public_safe");
    });
  });

  it("generates a report via the API", async () => {
    render(<ReportsPage />);
    await screen.findByText("4 devices became unavailable on Home2.");
    fireEvent.click(screen.getByRole("button", { name: /generate & store report/i }));
    await waitFor(() => expect(createReport).toHaveBeenCalled());
  });

  it("copies the markdown summary", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(<ReportsPage />);
    await screen.findByText("4 devices became unavailable on Home2.");
    fireEvent.click(screen.getByRole("button", { name: /copy markdown summary/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("ZigbeeLens")));
  });

  it("renders stored reports with a download link", async () => {
    listReports.mockResolvedValue([makeStored()]);
    render(<ReportsPage />);
    expect(await screen.findByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/api/reports/r1/download",
    );
  });

  it("shows an empty state when there are no stored reports", async () => {
    render(<ReportsPage />);
    expect(await screen.findByText(/no stored reports yet/i)).toBeInTheDocument();
  });
});
