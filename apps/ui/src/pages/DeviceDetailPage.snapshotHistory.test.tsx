import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import type { DeviceDetail, Incident } from "@zigbeelens/shared";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
  DeviceStoryDto,
} from "@/types/devices";
import { ApiError, api } from "@/lib/api";
import { SNAPSHOT_HISTORY_UNAVAILABLE_COPY } from "@/lib/meshGraphCopy";
import {
  decisionStatusLabel,
  headlineText,
} from "@/viewModels/decisionCopy";
import { DeviceDetailPage } from "./DevicesPage";

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: () => () => {},
    subscribeState: () => () => {},
    getState: () => "open",
    isAccessEnabled: () => true,
  },
  LIVE_EVENTS: [],
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: { topology: { enabled: true } },
  }),
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
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-13T01:00:00Z",
    last_payload_at: "2026-07-13T01:05:00Z",
    home_assistant_area_name: "Kitchen",
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
    related_unresolved_incident_ids: [],
    timeline: [],
    ...overrides,
  };
}

function historyRow(overrides: Partial<DeviceSnapshotHistoryRow> = {}): DeviceSnapshotHistoryRow {
  return {
    snapshot_id: "snap-latest",
    captured_at: "2026-07-13T02:00:00Z",
    is_latest: true,
    is_usable: true,
    links_for_device_count: 1,
    route_hints_for_device_count: 0,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: null,
    ...overrides,
  };
}

function emptyHistory(
  overrides: Partial<DeviceSnapshotHistoryDetail> = {},
): DeviceSnapshotHistoryDetail {
  return {
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
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let navigateRef: ((to: string) => void) | null = null;

function NavigateProbe() {
  const navigate = useNavigate();
  navigateRef = navigate;
  return null;
}

function renderDevice(path = "/devices/home/0xa1") {
  navigateRef = null;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <NavigateProbe />
      <Routes>
        <Route path="/devices/:networkId/:ieeeAddress" element={<DeviceDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DeviceDetailPage independent snapshot history lifecycle", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    navigateRef = null;
  });

  it("keeps Device Detail mounted while snapshot history is pending", async () => {
    const history = deferred<DeviceSnapshotHistoryDetail>();
    vi.spyOn(api, "device").mockResolvedValue(makeDetail());
    vi.spyOn(api, "incidents").mockResolvedValue({
      items: [] as Incident[],
      total: 0,
      next_cursor: null,
    });
    vi.spyOn(api, "deviceStory").mockResolvedValue(makeStory());
    vi.spyOn(api, "topologyDeviceSnapshotHistory").mockReturnValue(history.promise);

    renderDevice();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBeInTheDocument();
    });
    expect(screen.getAllByText(decisionStatusLabel("review_first")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(headlineText("current_issue_present")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
    });
    expect(screen.getByText("Current state")).toBeInTheDocument();
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("Loading snapshot history…")).toBeInTheDocument();

    history.resolve(emptyHistory());
    await waitFor(() => {
      expect(screen.queryByText("Loading snapshot history…")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBeInTheDocument();
    expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
  });

  it("keeps the page mounted when snapshot history rejects", async () => {
    vi.spyOn(api, "device").mockResolvedValue(makeDetail());
    vi.spyOn(api, "incidents").mockResolvedValue({
      items: [] as Incident[],
      total: 0,
      next_cursor: null,
    });
    vi.spyOn(api, "deviceStory").mockResolvedValue(makeStory());
    vi.spyOn(api, "topologyDeviceSnapshotHistory").mockRejectedValue(
      new ApiError("history unavailable", 503),
    );

    renderDevice();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(SNAPSHOT_HISTORY_UNAVAILABLE_COPY)).toBeInTheDocument();
    });
    expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
    expect(screen.getByText("Current state")).toBeInTheDocument();
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("updates snapshot history later without remounting the rest of the page", async () => {
    const history = deferred<DeviceSnapshotHistoryDetail>();
    vi.spyOn(api, "device").mockResolvedValue(makeDetail());
    vi.spyOn(api, "incidents").mockResolvedValue({
      items: [] as Incident[],
      total: 0,
      next_cursor: null,
    });
    vi.spyOn(api, "deviceStory").mockResolvedValue(makeStory());
    vi.spyOn(api, "topologyDeviceSnapshotHistory").mockReturnValue(history.promise);

    renderDevice();
    await waitFor(() => {
      expect(screen.getByText("Loading snapshot history…")).toBeInTheDocument();
    });
    const heading = screen.getByRole("heading", { name: "Kitchen Plug" });

    history.resolve(
      emptyHistory({
        latest_snapshot: historyRow({ links_for_device_count: 1 }),
      }),
    );

    await waitFor(() => {
      expect(screen.getByText(/latest snapshot/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBe(heading);
    expect(screen.getByTestId("device-story-section")).toBeInTheDocument();
    expect(screen.getByText("Current state")).toBeInTheDocument();
    expect(screen.getByText(/1 link shown/i)).toBeInTheDocument();
  });

  it("ignores a stale history response after the device route changes", async () => {
    const first = deferred<DeviceSnapshotHistoryDetail>();
    const second = deferred<DeviceSnapshotHistoryDetail>();
    let historyCalls = 0;
    vi.spyOn(api, "device").mockImplementation(async (_network, ieee) =>
      makeDetail({
        ieee_address: ieee,
        friendly_name: ieee === "0xa1" ? "Kitchen Plug" : "Hall Sensor",
      }),
    );
    vi.spyOn(api, "incidents").mockResolvedValue({
      items: [] as Incident[],
      total: 0,
      next_cursor: null,
    });
    vi.spyOn(api, "deviceStory").mockImplementation(async (_network, ieee) =>
      makeStory({
        subject_id: ieee,
      }),
    );
    vi.spyOn(api, "topologyDeviceSnapshotHistory").mockImplementation(async () => {
      historyCalls += 1;
      return historyCalls === 1 ? first.promise : second.promise;
    });

    renderDevice("/devices/home/0xa1");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Kitchen Plug" })).toBeInTheDocument();
    });
    expect(screen.getByText("Loading snapshot history…")).toBeInTheDocument();
    expect(navigateRef).toBeTruthy();

    act(() => {
      navigateRef!("/devices/home/0xb2");
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Hall Sensor" })).toBeInTheDocument();
    });

    first.resolve(
      emptyHistory({
        device_ieee: "0xa1",
        friendly_name: "Kitchen Plug",
        latest_snapshot: historyRow({
          snapshot_id: "stale-a1",
          links_for_device_count: 9,
        }),
      }),
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByText(/9 links shown/i)).not.toBeInTheDocument();

    second.resolve(
      emptyHistory({
        device_ieee: "0xb2",
        friendly_name: "Hall Sensor",
        latest_snapshot: historyRow({
          snapshot_id: "fresh-b2",
          captured_at: "2026-07-13T03:00:00Z",
          links_for_device_count: 2,
        }),
      }),
    );

    await waitFor(() => {
      expect(screen.getByText(/2 links shown/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/9 links shown/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hall Sensor" })).toBeInTheDocument();
  });
});
