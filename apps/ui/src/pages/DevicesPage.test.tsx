import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DeviceSummary } from "@zigbeelens/shared";
import { DevicesPage } from "./DevicesPage";
import { DEVICE_DECISION_FILTER_OPTIONS } from "@/viewModels/devices/deviceRowViewModel";

const mockState = vi.hoisted(() => ({
  devices: [] as DeviceSummary[],
}));

vi.mock("@/lib/api", () => ({
  api: {
    devices: vi.fn(async () => ({ items: mockState.devices })),
  },
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({ scenario: "", status: { topology: { enabled: true } } }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: () => ({
    data: mockState.devices,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

function makeDevice(overrides: Partial<DeviceSummary> = {}): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-13T01:00:00Z",
    decision: {
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: ["availability_tracking_off"],
    },
    ha_area: "Kitchen",
    ...overrides,
  };
}

function renderDevices() {
  return render(
    <MemoryRouter>
      <DevicesPage />
    </MemoryRouter>,
  );
}

describe("DevicesPage decision inventory", () => {
  beforeEach(() => {
    mockState.devices = [
      makeDevice({
        ieee_address: "0xwatch",
        friendly_name: "Watch Sensor",
        decision: {
          status: "watch",
          priority: "medium",
          headline_code: "stale_last_seen",
          coverage_label_codes: [],
        },
      }),
      makeDevice({
        ieee_address: "0xrev",
        friendly_name: "Review Plug",
        availability: "offline",
        decision: {
          status: "review_first",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: ["availability_tracking_off", "ha_areas_not_linked"],
        },
      }),
      makeDevice({
        ieee_address: "0xfuture",
        friendly_name: "Future Status",
        decision: {
          status: "future_status_v2",
          priority: "high",
          headline_code: "future_headline_v2",
          coverage_label_codes: ["future_coverage_v2"],
        },
      }),
    ];
  });

  it("renders decision badge as primary status and omits legacy lens bucket labels", () => {
    renderDevices();
    expect(screen.getByRole("columnheader", { name: "Decision" })).toBeInTheDocument();
    expect(screen.getAllByText("Review first").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Watch").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Status unknown").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Legacy lens says unavailable")).not.toBeInTheDocument();
  });

  it("uses mapped decision filter labels and filters by raw status", () => {
    renderDevices();
    const decisionSelect = screen.getByLabelText("Decision");
    for (const option of DEVICE_DECISION_FILTER_OPTIONS) {
      expect(within(decisionSelect).getByRole("option", { name: option.label })).toHaveValue(
        option.value,
      );
    }
    fireEvent.change(decisionSelect, { target: { value: "review_first" } });
    expect(screen.getByText("Review Plug")).toBeInTheDocument();
    expect(screen.queryByText("Watch Sensor")).not.toBeInTheDocument();
  });

  it("keeps unknown statuses visible under All decisions", () => {
    renderDevices();
    expect(screen.getByText("Future Status")).toBeInTheDocument();
    expect(screen.queryByText("future_status_v2")).not.toBeInTheDocument();
    expect(screen.queryByText("future_coverage_v2")).not.toBeInTheDocument();
    expect(screen.queryByText("availability_tracking_off")).not.toBeInTheDocument();
  });

  it("filters availability and coverage independently", () => {
    renderDevices();
    fireEvent.change(screen.getByLabelText("Availability"), {
      target: { value: "offline" },
    });
    expect(screen.getByText("Review Plug")).toBeInTheDocument();
    expect(screen.queryByText("Watch Sensor")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Availability"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Coverage"), {
      target: { value: "limitations" },
    });
    expect(screen.getByText("Review Plug")).toBeInTheDocument();
    expect(screen.queryByText("Watch Sensor")).not.toBeInTheDocument();
  });

  it("searches name, IEEE, manufacturer/model, and explicit area", () => {
    renderDevices();
    const search = screen.getByPlaceholderText(/Name, IEEE/i);

    fireEvent.change(search, { target: { value: "Watch Sensor" } });
    expect(screen.getByText("Watch Sensor")).toBeInTheDocument();
    expect(screen.queryByText("Review Plug")).not.toBeInTheDocument();
  });

  it("orders rows by decision priority", () => {
    renderDevices();
    const names = screen.getAllByRole("row").slice(1).map((row) => {
      const cell = within(row).getAllByRole("cell")[0];
      return cell.textContent ?? "";
    });
    expect(names[0]).toContain("Review Plug");
    expect(names[1]).toContain("Watch Sensor");
    const unknownIndex = names.findIndex((n) => n.includes("Future Status"));
    expect(unknownIndex).toBeGreaterThan(1);
  });

  it("links to device detail and mesh routes", () => {
    renderDevices();
    expect(screen.getAllByRole("link", { name: "View device →" })[0]).toHaveAttribute(
      "href",
      "/devices/home/0xrev",
    );
    expect(screen.getAllByRole("link", { name: "Review in Mesh" })[0]).toHaveAttribute(
      "href",
      "/topology/home",
    );
  });

  it("does not hard-code decision status mappings in the page source", () => {
    const pagePath = join(dirname(fileURLToPath(import.meta.url)), "DevicesPage.tsx");
    const source = readFileSync(pagePath, "utf8");
    expect(source).not.toMatch(/review_first/);
    expect(source).not.toMatch(/worth_reviewing/);
    expect(source).not.toMatch(/improve_data_coverage/);
    expect(source).not.toMatch(/no_notable_change/);
  });
});
