import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReportSummary } from "@zigbeelens/shared";
import { getDialogFocusable } from "@/components/reports/dialogFocusable";

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
    decision_summary: {
      subject_count: 1,
      status_counts: { watch: 1 },
      coverage_warning_count: 0,
      overall_status: "watch",
      highest_priority: "medium",
      priority_counts: {},
    },
    generated_at: "2026-07-21T00:00:00Z",
    device_stories: [{ friendly_name: "Should not render full story" }],
    investigation_priorities: [{ id: "p1" }],
    data_coverage_warnings: [],
    incidents: [],
    collector_status: {},
    config_summary: {},
    domain_details: {
      networks: [{}],
      devices: [{}],
      device_details: [],
      router_risks: [],
      topology_snapshot_count: 0,
    },
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

const summary: ReportSummary = {
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
};

function renderDialog(
  props: Partial<React.ComponentProps<typeof ContextualReportDialog>> = {},
) {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  const returnFocusRef = { current: document.createElement("button") };
  returnFocusRef.current.textContent = "Launcher";
  document.body.appendChild(returnFocusRef.current);
  const result = render(
    <div>
      <button type="button" data-testid="background-control">
        Background
      </button>
      <ContextualReportDialog
        open
        target={deviceTarget}
        onClose={onClose}
        onCreated={onCreated}
        returnFocusRef={returnFocusRef}
        {...props}
      />
    </div>,
  );
  return { ...result, onClose, onCreated, returnFocusRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  previewReport.mockResolvedValue(previewBody());
  createReport.mockResolvedValue(summary);
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
      <ContextualReportDialog open={false} target={deviceTarget} onClose={() => {}} />,
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
        redaction: expect.objectContaining({
          profile: "standard",
          include_raw_payloads: false,
        }),
      }),
      undefined,
    );
    expect(screen.getByRole("dialog", { name: /create device report/i })).toBeInTheDocument();
    expect(screen.getAllByText("Kitchen Plug").length).toBeGreaterThan(0);
    expect(screen.queryByText("Should not render full story")).not.toBeInTheDocument();
  });

  it("does not restart preview on semantic no-op parent target rerender", async () => {
    const { rerender, onClose, onCreated, returnFocusRef } = renderDialog();
    await waitFor(() => expect(previewReport).toHaveBeenCalledTimes(1));
    rerender(
      <div>
        <button type="button" data-testid="background-control">
          Background
        </button>
        <ContextualReportDialog
          open
          target={{ ...deviceTarget }}
          onClose={onClose}
          onCreated={onCreated}
          returnFocusRef={returnFocusRef}
        />
      </div>,
    );
    await waitFor(() => expect(screen.getByText(/Decision summary/i)).toBeInTheDocument());
    expect(previewReport).toHaveBeenCalledTimes(1);
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

  it("disables Save until the current preview is accepted", async () => {
    let resolvePreview!: (value: unknown) => void;
    previewReport.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePreview = resolve;
        }),
    );
    renderDialog();
    expect(screen.getByRole("button", { name: "Save report" })).toBeDisabled();
    resolvePreview(previewBody());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save report" })).not.toBeDisabled(),
    );
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
    resolveCreate(summary);
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(download).not.toHaveBeenCalled();
  });

  it("after save, Download saved report does not create again", async () => {
    renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    await screen.findByText("Report saved.");
    expect(screen.queryByRole("button", { name: "Save report" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download saved report" }));
    await waitFor(() => expect(download).toHaveBeenCalledWith("rep-1", undefined));
    expect(createReport).toHaveBeenCalledTimes(1);
    expect(triggerDownload).toHaveBeenCalledTimes(1);
  });

  it("Save and download creates once; Retry download uses the same ID", async () => {
    download.mockRejectedValueOnce(new Error("dl fail"));
    const { onCreated } = renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save and download" }));
    await waitFor(() =>
      expect(
        screen.getByText(/Report saved, but download could not be started/i),
      ).toBeInTheDocument(),
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
  });

  it("changing format after save requests a new preview and allows one new create", async () => {
    renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    await screen.findByText("Report saved.");
    const before = previewReport.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    await waitFor(() => expect(previewReport.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save report" })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    await waitFor(() => expect(createReport).toHaveBeenCalledTimes(2));
    expect(createReport.mock.calls[1]![0].format).toBe("yaml");
  });

  it("semantic no-op rerender while create is pending does not restart preview or stick at Saving", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { rerender, onClose, onCreated, returnFocusRef } = renderDialog();
    await screen.findByText(/Decision summary/i);
    const previewCalls = previewReport.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    rerender(
      <div>
        <button type="button" data-testid="background-control">
          Background
        </button>
        <ContextualReportDialog
          open
          target={{ ...deviceTarget }}
          onClose={onClose}
          onCreated={onCreated}
          returnFocusRef={returnFocusRef}
        />
      </div>,
    );
    expect(previewReport.mock.calls.length).toBe(previewCalls);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeInTheDocument();
    resolveCreate(summary);
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Report saved.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Saving…" })).not.toBeInTheDocument();
  });

  it("target change while create is pending does not apply stale onCreated", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const onCreatedA = vi.fn();
    const onCreatedB = vi.fn();
    const returnFocusRef = { current: document.createElement("button") };
    document.body.appendChild(returnFocusRef.current);
    const { rerender } = render(
      <ContextualReportDialog
        open
        target={deviceTarget}
        onClose={() => {}}
        onCreated={onCreatedA}
        returnFocusRef={returnFocusRef}
      />,
    );
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    rerender(
      <ContextualReportDialog
        open
        target={{
          scope: "device",
          networkId: "home",
          deviceIeee: "0xdef",
          subjectLabel: "Other Plug",
        }}
        onClose={() => {}}
        onCreated={onCreatedB}
        returnFocusRef={returnFocusRef}
      />,
    );
    expect(screen.getByRole("dialog", { name: /create device report/i })).toHaveTextContent(
      "Other Plug",
    );
    expect(screen.queryByText("Kitchen Plug")).not.toBeInTheDocument();
    resolveCreate(summary);
    await waitFor(() =>
      expect(
        screen.getByText(/may have been saved for the previous selection/i),
      ).toBeInTheDocument(),
    );
    expect(onCreatedA).not.toHaveBeenCalled();
    expect(onCreatedB).not.toHaveBeenCalled();
    expect(screen.queryByText("Report saved.")).not.toBeInTheDocument();
  });

  it("never shows an old preview under a new target label", async () => {
    let resolveFirst!: (value: unknown) => void;
    previewReport.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const returnFocusRef = { current: document.createElement("button") };
    const { rerender } = render(
      <ContextualReportDialog
        open
        target={deviceTarget}
        onClose={() => {}}
        returnFocusRef={returnFocusRef}
      />,
    );
    expect(screen.getByText("Loading preview…")).toBeInTheDocument();
    previewReport.mockResolvedValueOnce(
      previewBody({
        raw_counts: { networks_included: 9, devices_included: 9, incidents_included: 9 },
      }),
    );
    rerender(
      <ContextualReportDialog
        open
        target={{
          scope: "device",
          networkId: "home",
          deviceIeee: "0xdef",
          subjectLabel: "Other Plug",
        }}
        onClose={() => {}}
        returnFocusRef={returnFocusRef}
      />,
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Other Plug");
    expect(screen.queryByText("Kitchen Plug")).not.toBeInTheDocument();
    resolveFirst(previewBody());
    await waitFor(() => expect(screen.getByText(/Decision summary/i)).toBeInTheDocument());
    expect(screen.queryByText("Kitchen Plug")).not.toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Networks").closest("div")).toHaveTextContent("9");
  });

  it("copies preview markdown and soft-fails on clipboard errors", async () => {
    renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Copy preview Markdown summary" }));
    await waitFor(() =>
      expect(writeClipboard).toHaveBeenCalledWith("# Device preview", 1),
    );
    writeClipboard.mockRejectedValueOnce(new Error("denied"));
    fireEvent.click(screen.getByRole("button", { name: "Copy preview Markdown summary" }));
    expect(await screen.findByText("Could not copy preview Markdown.")).toBeInTheDocument();
  });

  it("announces format and redaction profile selection with aria-pressed", async () => {
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText(/Decision summary/i);
    const formatGroup = screen.getByRole("group", { name: "Format" });
    expect(within(formatGroup).getByRole("button", { name: "JSON" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const profileGroup = screen.getByRole("group", { name: "Redaction profile" });
    expect(within(profileGroup).getByRole("button", { name: "Standard" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(within(profileGroup).getByRole("button", { name: "Public safe" }));
    await waitFor(() => {
      expect(within(profileGroup).getByRole("button", { name: "Public safe" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(within(profileGroup).getByRole("button", { name: "Standard" })).toHaveAttribute(
        "aria-pressed",
        "false",
      );
    });
    const last = previewReport.mock.calls.at(-1)?.[0];
    expect(last.redaction.profile).toBe("public_safe");
    expect(last.redaction.preserve_friendly_names).toBe(false);
  });

  it("traps Tab among visible controls and excludes closed Advanced inputs", async () => {
    const user = userEvent.setup();
    const { onClose, returnFocusRef } = renderDialog();
    const dialog = await screen.findByRole("dialog");
    await screen.findByText(/Decision summary/i);
    const close = within(dialog).getByRole("button", { name: "Close" });
    expect(close).toHaveFocus();

    const focusable = getDialogFocusable(dialog);
    expect(focusable.some((el) => el.tagName === "INPUT")).toBe(false);
    expect(focusable.some((el) => el.tagName === "SUMMARY")).toBe(true);

    const last = focusable[focusable.length - 1]!;
    last.focus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(last);

    expect(dialog.contains(screen.getByTestId("background-control"))).toBe(false);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(returnFocusRef.current).toHaveFocus());
  });

  it("includes Advanced checkboxes in the trap when open", async () => {
    const user = userEvent.setup();
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    await screen.findByText(/Decision summary/i);
    await user.click(within(dialog).getByText("Advanced redaction"));
    await waitFor(() => {
      expect(getDialogFocusable(dialog).some((el) => el.tagName === "INPUT")).toBe(true);
    });
  });

  it("includes Retry in focus order when preview fails", async () => {
    previewReport.mockRejectedValueOnce(new Error("preview failed"));
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    expect(await screen.findByText("preview failed")).toBeInTheDocument();
    const focusable = getDialogFocusable(dialog);
    expect(focusable.some((el) => /try again/i.test(el.textContent ?? ""))).toBe(true);
  });

  it("scenario change while create is pending does not call the new onCreated", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const onCreatedA = vi.fn();
    const onCreatedB = vi.fn();
    const returnFocusRef = { current: document.createElement("button") };
    const { rerender } = render(
      <ContextualReportDialog
        open
        target={deviceTarget}
        scenario="alpha"
        onClose={() => {}}
        onCreated={onCreatedA}
        returnFocusRef={returnFocusRef}
      />,
    );
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    rerender(
      <ContextualReportDialog
        open
        target={deviceTarget}
        scenario="beta"
        onClose={() => {}}
        onCreated={onCreatedB}
        returnFocusRef={returnFocusRef}
      />,
    );
    resolveCreate(summary);
    await waitFor(() =>
      expect(
        screen.getByText(/may have been saved for the previous selection/i),
      ).toBeInTheDocument(),
    );
    expect(onCreatedA).not.toHaveBeenCalled();
    expect(onCreatedB).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save report" })).not.toBeDisabled(),
    );
  });

  it("unmount while create is pending does not throw or call onCreated", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const onCreated = vi.fn();
    const { unmount } = renderDialog({ onCreated });
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    unmount();
    resolveCreate(summary);
    await Promise.resolve();
    await Promise.resolve();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("Escape does not close while creating", async () => {
    let resolveCreate!: (value: ReportSummary) => void;
    createReport.mockImplementation(
      () =>
        new Promise<ReportSummary>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { onClose } = renderDialog();
    await screen.findByText(/Decision summary/i);
    fireEvent.click(screen.getByRole("button", { name: "Save report" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    resolveCreate(summary);
    await screen.findByText("Report saved.");
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
