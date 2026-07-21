import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { DeviceDetail, Incident } from "@zigbeelens/shared";
import type { DeviceStoryDto } from "@/types/devices";
import { api } from "@/lib/api";
import { DeviceDetailPage } from "./DevicesPage";
import {
  decisionStatusLabel,
  headlineText,
} from "@/viewModels/decisionCopy";

const mockState = vi.hoisted(() => ({
  detail: null as DeviceDetail | null,
  incidents: [] as Incident[],
  story: null as DeviceStoryDto | null,
  scenario: "",
}));

vi.mock("@/lib/api", () => ({
  api: {
    device: vi.fn(async () => mockState.detail),
    incidents: vi.fn(async () => ({ items: mockState.incidents })),
    deviceStory: vi.fn(async () => mockState.story),
    topologyDeviceSnapshotHistory: vi.fn(async () => ({
      network_id: "home",
      device_ieee: "0xa1",
      friendly_name: "Kitchen Plug",
      has_current_issue: false,
      availability_tracking: { enabled: true, earliest_observation_at: null },
      latest_snapshot: null,
      snapshots: [],
      topology_facts: {
        stale_threshold_hours: null,
        device_facts: [],
        comparison_facts_by_snapshot_id: {},
      },
    })),
  },
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: mockState.scenario,
    status: { topology: { enabled: true } },
  }),
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (fetcher: () => unknown) => {
    const source = fetcher.toString();
    // Invoke so scenario args are recorded on api mocks.
    void fetcher();
    if (source.includes("incidents")) {
      return {
        data: mockState.incidents.filter((inc) =>
          inc.affected_devices.some(
            (d) => d.network_id === "home" && d.ieee_address === "0xa1",
          ),
        ),
        loading: false,
        error: null,
        refetch: vi.fn(),
      };
    }
    if (source.includes("topologyDeviceSnapshotHistory")) {
      return {
        data: {
          network_id: "home",
          device_ieee: "0xa1",
          friendly_name: "Kitchen Plug",
          has_current_issue: false,
          availability_tracking: { enabled: true, earliest_observation_at: null },
          latest_snapshot: null,
          snapshots: [],
          topology_facts: {
            stale_threshold_hours: null,
            device_facts: [],
            comparison_facts_by_snapshot_id: {},
          },
        },
        loading: false,
        error: null,
        refetch: vi.fn(),
      };
    }
    return {
      data: mockState.detail,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
  },
}));

function makeDetail(overrides: Partial<DeviceDetail> = {}): DeviceDetail {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "Kitchen Plug",
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    decision: { status: "no_notable_change", priority: "none", headline_code: "device_no_notable_change", coverage_label_codes: [] },
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-13T01:00:00Z",
    last_payload_at: "2026-07-13T01:05:00Z",
    ha_area: "Kitchen",
    decision: {
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      coverage_label_codes: ["availability_tracking_off"],
    },
    definition: null,
    supported: true,
    recent_availability_changes: [],
    recent_events: [],
    recent_bridge_logs: [],
    diagnostic: {
      classification: "healthy",
      severity: "healthy",
      scope: "device",
      confidence: "high",
      summary: "Legacy diagnostic summary",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    trends: [],
    ...overrides,
  };
}

function makeStory(overrides: Partial<DeviceStoryDto> = {}): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: "0xa1",
    status: "review_first",
    priority: "high",
    headline_code: "current_issue_present",
    reasons: [{ code: "current_issue_present", params: {} }],
    evidence: [],
    limitations: [{ code: "route_hints_not_live_routing", params: {} }],
    suggested_checks: [{ code: "confirm_powered", params: {} }],
    coverage: [
      {
        dimension: "availability",
        state: "off",
        label_code: "availability_tracking_off",
        params: {},
      },
    ],
    timeline: [],
    ...overrides,
  };
}

function makeIncident(): Incident {
  return {
    id: "inc-1",
    type: "single_device_unavailable",
    status: "open",
    severity: "incident",
    scope: "device",
    confidence: "medium",
    title: "Device unavailable",
    summary: "Kitchen Plug stopped reporting.",
    interpretation: "Tracked as an incident record.",
    network_ids: ["home"],
    affected_device_count: 1,
    affected_devices: [
      {
        network_id: "home",
        ieee_address: "0xa1",
        friendly_name: "Kitchen Plug",
        decision: {
          status: "no_notable_change",
          priority: "none",
          headline_code: "device_no_notable_change",
          coverage_label_codes: [],
        },
      },
    ],
    opened_at: "2026-07-13T00:00:00Z",
    updated_at: "2026-07-13T00:01:00Z",
    resolved_at: null,
    evidence: [],
    counter_evidence: [],
    limitations: [],
    timeline: [],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      summary: "Device unavailable",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
  };
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/devices/home/0xa1"]}>
      <Routes>
        <Route path="/devices/:networkId/:ieeeAddress" element={<DeviceDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DeviceDetailPage decision authority", () => {
  beforeEach(() => {
    mockState.detail = makeDetail();
    mockState.incidents = [];
    mockState.story = makeStory();
    mockState.scenario = "";
    vi.mocked(api.device).mockClear();
    vi.mocked(api.incidents).mockClear();
    vi.mocked(api.deviceStory).mockClear();
  });

  it("renders decision status and Device Story headline", async () => {
    renderDetail();
    expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBeInTheDocument();
    expect(screen.getAllByText(decisionStatusLabel("review_first")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(headlineText("current_issue_present")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
    });
    const story = screen.getByTestId("device-story-section");
    expect(within(story).getByText(/Availability tracking off/i)).toBeInTheDocument();
  });

  it("places Snapshot history after Device Story and before Current state", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByTestId("device-snapshot-history")).toBeInTheDocument();
    });
    const body = document.body.textContent ?? "";
    expect(body.indexOf("Device story")).toBeLessThan(body.indexOf("Snapshot history"));
    expect(body.indexOf("Snapshot history")).toBeLessThan(body.indexOf("Current state"));
    expect(screen.getByRole("link", { name: /raw snapshot/i })).toHaveAttribute(
      "href",
      "/topology/home",
    );
  });

  it("renders data_unavailable through canonical decision copy", () => {
    mockState.detail = makeDetail({
      decision: {
        status: "data_unavailable",
        priority: "none",
        headline_code: "device_data_unavailable",
        coverage_label_codes: [],
      },
    });
    renderDetail();
    expect(screen.getByText("Data unavailable")).toBeInTheDocument();
  });

  it("uses safe unknown copy for unknown future status", () => {
    mockState.detail = makeDetail({
      decision: {
        status: "future_status_v2",
        priority: "high",
        headline_code: "future_headline_v2",
        coverage_label_codes: ["future_coverage_v2"],
      },
    });
    renderDetail();
    expect(screen.getByText("Status unknown")).toBeInTheDocument();
    expect(screen.queryByText("future_status_v2")).not.toBeInTheDocument();
    expect(screen.queryByText("future_headline_v2")).not.toBeInTheDocument();
  });

  it("does not render legacy health/lens badges or competing healthy prose", () => {
    renderDetail();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
    expect(screen.queryByText("Looks fine in lens")).not.toBeInTheDocument();
    expect(screen.queryByText("This device currently looks healthy.")).not.toBeInTheDocument();
    expect(
      screen.queryByText("This currently looks isolated to this device."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("ZigbeeLens has not observed enough data to classify this device yet."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Legacy diagnostic summary")).not.toBeInTheDocument();
  });

  it("keeps related incidents without inventing device status prose from them", () => {
    mockState.incidents = [makeIncident()];
    renderDetail();
    expect(screen.getByText("Device unavailable")).toBeInTheDocument();
    expect(
      screen.queryByText(/part of a correlated incident ZigbeeLens is currently tracking/i),
    ).not.toBeInTheDocument();
  });

  it("retains factual telemetry, identity, HA area and IEEE", () => {
    renderDetail();
    expect(screen.getByText("Online")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("118")).toBeInTheDocument();
    expect(screen.getByText("IKEA")).toBeInTheDocument();
    expect(screen.getByText("TS011F")).toBeInTheDocument();
    expect(screen.getByText("Kitchen")).toBeInTheDocument();
    expect(screen.getAllByText("0xa1").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/End ?[Dd]evice/).length).toBeGreaterThan(0);
  });

  it("does not hard-code decision status mappings in the page source", () => {
    const pagePath = join(dirname(fileURLToPath(import.meta.url)), "DevicesPage.tsx");
    const source = readFileSync(pagePath, "utf8");
    expect(source).not.toMatch(/suggestsLine/);
    expect(source).not.toMatch(/HealthBadge/);
    expect(source).not.toMatch(/LensBucketBadge/);
    expect(source).not.toMatch(/review_first/);
    expect(source).not.toMatch(/worth_reviewing/);
    expect(source).not.toMatch(/improve_data_coverage/);
    expect(source).not.toMatch(/no_notable_change/);
  });

  it("propagates the active scenario to device, incidents, and Device Story", async () => {
    mockState.scenario = "offline_cluster";
    renderDetail();
    await waitFor(() => {
      expect(api.deviceStory).toHaveBeenCalled();
    });
    expect(api.device).toHaveBeenCalledWith("home", "0xa1", "offline_cluster");
    expect(api.incidents).toHaveBeenCalledWith({
      scenario: "offline_cluster",
      network_id: "home",
      device_ieee: "0xa1",
      limit: 50,
    });
    expect(api.deviceStory).toHaveBeenCalledWith("home", "0xa1", "offline_cluster");
  });

  it("keeps Device Detail and Device Story on the same scenario decision", async () => {
    mockState.scenario = "offline_cluster";
    mockState.detail = makeDetail({
      decision: {
        status: "review_first",
        priority: "high",
        headline_code: "current_issue_present",
        coverage_label_codes: ["availability_tracking_off"],
      },
    });
    mockState.story = makeStory({
      status: "review_first",
      priority: "high",
      headline_code: "current_issue_present",
      reasons: [{ code: "current_issue_present", params: {} }],
      coverage: [
        {
          dimension: "availability",
          state: "off",
          label_code: "availability_tracking_off",
          params: {},
        },
      ],
    });

    renderDetail();

    expect(screen.getAllByText(decisionStatusLabel("review_first")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(headlineText("current_issue_present")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
    });
    const story = screen.getByTestId("device-story-section");
    expect(within(story).getAllByText(headlineText("current_issue_present")).length).toBeGreaterThan(
      0,
    );
    expect(within(story).getByText(/Availability tracking off/i)).toBeInTheDocument();
    expect(screen.queryByText(headlineText("stale_last_seen"))).not.toBeInTheDocument();
    expect(screen.queryByText(decisionStatusLabel("watch"))).not.toBeInTheDocument();
  });
});
