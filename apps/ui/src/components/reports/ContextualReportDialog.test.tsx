import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReportSummary } from "@zigbeelens/shared";

vi.mock("@/lib/api", () => ({
  api: {
    previewReport: vi.fn(),
    createReport: vi.fn(),
  },
  downloadStoredReport: vi.fn(),
  triggerBrowserDownload: vi.fn(),
  writeProtectedClipboardText: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

vi.mock("@/lib/authRuntime", () => ({
  authRuntime: {
    getAccessGeneration: () => 1,
  },
}));

import {
  api,
  downloadStoredReport,
  triggerBrowserDownload,
  writeProtectedClipboardText,
} from "@/lib/api";
import { ContextualReportDialog } from "./ContextualReportDialog";

const previewReport = api.previewReport as Mock;
const createReport = api.createReport as Mock;
const download = downloadStoredReport as Mock;
const triggerDownload = triggerBrowserDownload as Mock;
const writeClipboard = writeProtectedClipboardText as Mock;

function previewBody(overrides: Record<string, unknown> = {}) {
  return {
    id: "preview",
    product: "ZigbeeLens",
    report_version: 3,
    format: "json",
    scope: "device",
    version: "test",
    markdown_summary: "# Device preview",
    limitations: [{ code: "coverage_gap" }],
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
    decision_summary: { subject_count: 1, status_counts: { watch: 1 }, coverage_warning_count: 0 },
    generated_at: "2026-07-21T00:00:00Z",
    device_stories: [{ friendly_name: "Should not render full story" }],
    investigation_priorities: [{ id: "p1" }],
    data_coverage_warnings: [],
    incidents: [],
    collector_status: {},
    config_summary: {},
    domain_details: { networks: [{}], devices: [{}], device_details: [], router_risks: [] },
    events_or_timeline: [],
    raw_counts: { networks_included: 1, devices_included: 1, incidents_included: 0 },
    ...overrides,
  };
}

const deviceTarget = {
  scope: "device" as const,
  networkId: "home",
  deviceIeee: "0xabc",
  subjectLabel: "Kitchen Plug",
};

function renderDialog(
  props: Partial<React.ComponentProps<typeof ContextualReportDialog>> = {},
) {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  const returnFocusRef = { current: document.createElement("button") };
  document.body.appendChild(returnFocusRef.current);
  const result = render(
    <ContextualReportDialog
      open
      target={deviceTarget}
      onClose={onClose}
      onCreated={onCreated}
      returnFocusRef={returnFocusRef}
      {...props}
    />,
  );
  return { ...result, onClose, onCreated, returnFocusRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  previewReport.mockResolvedValue(previewBody());
  createReport.mockResolvedValue({
    id: "rep-1",
    generated_at: "2026-07-21T00:00:00Z",
    redaction_applied: true,
    incident_count: 0,
    device_count: 1,
    network_count: 1,
    summary: "Device report",
    format: "json",
    scope: "device",
    redaction_profile: "standard",
  } satisfies ReportSummary);
  download.mockResolvedValue({
    blob: new Blob(["{}"], { type: "application/json" }),
    filename: "report.json",
    contentType: "application/json",
    authGeneration: 1,
  });
  triggerDownload.mockResolvedValue(undefined);
  writeClipboard.mockResolvedValue(undefined);
});

describe("ContextualReportDialog", () => {
  it("makes no preview request when closed", () => {
    render(
      <ContextualReportDialog
        open={false}
        target={deviceTarget}
        onClose={() => {}}
      />,
    );
    expect(previewReport).not.toHaveBeenCalled();
  });

  it("requests one compact preview for the fixed target when opened", async () => {
    renderDialog();
    await waitFor(() => expect(previewReport).toHaveBeenCalledTimes(1));
    expect(previewReport).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: "device",
        network_id: "home",
        device: "0xabc",
        incident_id: null,
        format: "json",
        redaction: expect.objectContaining({ profile: "standard", include_raw_payloads: false }),
      }),
      undefined,
    );
    expect(screen.getByRole("dialog", { name: /create device report/i })).toBeInTheDocument();
    expect(screen.getAllByText("Kitchen Plug").length).toBeGreaterThan(0);
    expect(screen.queryByText("Should not render full story")).not.toBeInTheDocument();
    expect(screen.queryByText("What to check first")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^network$/i })).not.toBeInTheDocument();
  });

  it("retries preview after an error", async () => {
    previewReport.mockRejectedValueOnce(new Error("preview failed"));
    renderDialog();
    expect(await screen.findByText("preview failed")).toBeInTheDocument();
    previewReport.mockResolvedValueOnce(previewBody());
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(previewReport).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Decision summary/i)).toBeInTheDocument();
  });

  it("Save report is single-flight and invokes onCreated once", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { onCreated } = renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    fireEvent.click(screen.getByRole("button", { name: "Saving…" }));
    expect(createReport).toHaveBeenCalledTimes(1);
    resolveCreate({
      id: "rep-1",
      generated_at: "2026-07-21T00:00:00Z",
      redaction_applied: true,
      incident_count: 0,
      device_count: 1,
      network_count: 1,
      summary: "Device report",
      format: "json",
      scope: "device",
      redaction_profile: "standard",
    });
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(download).not.toHaveBeenCalled();
  });

  it("Save and download creates once and retries download without recreating", async () => {
    download.mockRejectedValueOnce(new Error("dl fail"));
    const { onCreated } = renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save and download" }));
    await waitFor(() =>
      expect(screen.getByText(/Report saved, but download could not be started/i)).toBeInTheDocument(),
    );
    expect(createReport).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
    download.mockResolvedValueOnce({
      blob: new Blob(["{}"], { type: "application/json" }),
      filename: "report.json",
      contentType: "application/json",
      authGeneration: 1,
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry download" }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(2));
    expect(download).toHaveBeenNthCalledWith(1, "rep-1", undefined);
    expect(download).toHaveBeenNthCalledWith(2, "rep-1", undefined);
    expect(createReport).toHaveBeenCalledTimes(1);
    expect(triggerDownload).toHaveBeenCalledTimes(1);
  });

  it("copies preview markdown when preview is ready", async () => {
    renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Copy preview Markdown summary" }));
    await waitFor(() =>
      expect(writeClipboard).toHaveBeenCalledWith("# Device preview", 1),
    );
  });

  it("Escape closes when idle and restores focus", async () => {
    const { onClose, returnFocusRef } = renderDialog();
    await screen.findByRole("dialog");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(returnFocusRef.current).toHaveFocus());
  });

  it("changing profile resets overrides to profile defaults", async () => {
    renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Public safe" }));
    await waitFor(() => {
      const last = previewReport.mock.calls.at(-1)?.[0];
      expect(last.redaction.profile).toBe("public_safe");
      expect(last.redaction.preserve_friendly_names).toBe(false);
      expect(last.redaction.include_raw_payloads).toBe(false);
    });
  });
});
