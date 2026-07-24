import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DashboardPayload,
  DeviceDetail,
  DeviceSummary,
  NetworkSummary,
} from "@zigbeelens/shared";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceStoryDto,
} from "@/types/devices";
import {
  makeDashboardPayload,
  makeDecisionBadge,
  makeDecisionSummary,
  makeNetworkSummary,
} from "@/test/decisionFixtures";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { DevicesPage, DeviceDetailPage } from "@/pages/DevicesPage";
import { NetworkDetailPage, NetworksPage } from "@/pages/NetworksPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { SettingsPage } from "@/pages/SettingsPage";

const apiMocks = vi.hoisted(() => ({
  dashboard: vi.fn(),
  devices: vi.fn(),
  device: vi.fn(),
  deviceStory: vi.fn(),
  deviceCoverage: vi.fn(),
  incidents: vi.fn(),
  network: vi.fn(),
  networks: vi.fn(),
  timeline: vi.fn(),
  topologyDeviceSnapshotHistory: vi.fn(),
  health: vi.fn(),
  storageStatus: vi.fn(),
}));

const scenarioState = vi.hoisted(() => ({
  scenario: "",
  refreshStatus: vi.fn(),
  status: {
    version: "0.1.14",
    uptime_seconds: 1,
    mqtt_connected: true,
    mqtt_server: "mqtt://localhost",
    configured_networks: [
      { id: "home", name: "Home", base_topic: "zigbee2mqtt" },
    ],
    storage_path: "/tmp/zigbeelens-test.sqlite",
    storage_ready: true,
    retention_days: 7,
    resolved_incident_retention_days: null,
    report_retention_days: null,
    maintenance_interval_hours: 24,
    features: { mqtt_discovery: false },
    topology: { enabled: false },
    data_mode: "live",
    mock_mode: false,
    security: {
      mode: "open",
      api_token_configured: false,
      browser_sessions_enabled: false,
      trusted_local_open: true,
      legacy_mutation_guard_enabled: false,
      cors_allowed_origins_count: 0,
      credentialed_cors_enabled: false,
      frame_ancestor_origins_count: 0,
      external_framing_enabled: false,
      content_security_policy_enabled: true,
      session_origin_validation_enabled: false,
    },
  },
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      ...apiMocks,
    },
  };
});

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: scenarioState.scenario,
    status: scenarioState.status,
    refreshStatus: scenarioState.refreshStatus,
    dataMode: "live",
    isScenarioMode: false,
  }),
}));

vi.mock("@/context/BrowserAuthContext", () => ({
  useAuth: () => ({
    authMethod: "trusted_local",
    browserSessionEnabled: false,
    expiresAt: null,
    logout: vi.fn(),
    logoutBusy: false,
    logoutError: null,
  }),
}));

vi.mock("@/components/reports/ContextualReportDialog", () => ({
  ContextualReportDialog: () => null,
}));

function deviceSummary(
  overrides: Partial<DeviceSummary> = {},
): DeviceSummary {
  return {
    network_id: "home",
    ieee_address: "0xa1",
    friendly_name: "z2m_kitchen_lamp",
    device_type: "EndDevice",
    power_source: "Mains",
    availability: "online",
    interview_state: "successful",
    incident_affected: false,
    manufacturer: "IKEA",
    model: "TS011F",
    battery: 62,
    linkquality: 118,
    last_seen: "2026-07-23T01:00:00Z",
    decision: makeDecisionBadge(),
    ...overrides,
  };
}

function deviceDetail(
  overrides: Partial<DeviceDetail> = {},
): DeviceDetail {
  return {
    ...deviceSummary(),
    last_payload_at: "2026-07-23T01:05:00Z",
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
      summary: "No current issue.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    trends: [],
    ...overrides,
  };
}

function deviceStory(
  areaName: string | null,
): DeviceStoryDto {
  return {
    subject_type: "device",
    subject_id: "0xa1",
    status: "no_notable_change",
    priority: "none",
    headline_code: "no_notable_signals",
    reasons: [],
    evidence: [],
    limitations: [],
    suggested_checks: [],
    coverage: [
      areaName
        ? {
            dimension: "ha_enrichment",
            state: "available",
            label_code: "ha_area_linked",
            params: { area_name: areaName },
          }
        : {
            dimension: "ha_enrichment",
            state: "not_configured",
            label_code: "ha_areas_not_linked",
            params: {},
          },
    ],
    related_unresolved_incident_ids: [],
    timeline: [],
  };
}

function emptySnapshotHistory(): DeviceSnapshotHistoryDetail {
  return {
    network_id: "home",
    device_ieee: "0xa1",
    friendly_name: "z2m_kitchen_lamp",
    has_current_issue: false,
    availability_tracking: {
      enabled: true,
      earliest_observation_at: null,
    },
    latest_snapshot: null,
    snapshots: [],
    topology_facts: {
      stale_threshold_hours: null,
      device_facts: [],
      comparison_facts_by_snapshot_id: {},
    },
  };
}

function dashboardWithCoverage(
  coverage: boolean,
): DashboardPayload {
  return makeDashboardPayload({
    generated_at: "2026-07-23T02:00:00+00:00",
    networks: [
      makeNetworkSummary({
        id: "home",
        name: "Home",
        device_count: 1,
      }),
    ],
    data_coverage_warnings: coverage
      ? [
          {
            id: "coverage-home-ha",
            network_id: "home",
            dimension: "ha_enrichment",
            state: "not_configured",
            label_code: "ha_areas_not_linked",
            scope_type: "network",
            params: {},
          },
        ]
      : [],
  });
}

function networkWithCoverage(
  coverageWarningCount: number,
): NetworkSummary {
  return makeNetworkSummary({
    id: "home",
    name: "Home",
    device_count: 1,
    router_count: 0,
    end_device_count: 1,
    decision: makeDecisionBadge(),
    decision_summary: makeDecisionSummary({
      subject_count: 1,
      overall_status: "no_notable_change",
      highest_priority: "none",
      status_counts: { no_notable_change: 1 },
      priority_counts: { none: 1 },
      coverage_warning_count: coverageWarningCount,
    }),
  });
}

const storageStatus = {
  policy: {
    policy_version: 2,
    telemetry_retention_days: 7,
    resolved_incident_retention_days: null,
    report_retention_days: null,
    maintenance_interval_hours: 24,
    topology_max_snapshots_per_network: 30,
  },
  maintenance: {
    running: false,
    last_started_at: null,
    last_completed_at: null,
    last_successful_at: null,
    next_scheduled_at: null,
    last_error_code: null,
    total_rows_deleted: null,
    more_work_pending: false,
    duration_ms: null,
    malformed_timestamps_by_category: {},
    future_timestamps_by_category: {},
    wal_checkpoint: { busy: false },
  },
  footprint: {
    database_bytes: 1024,
    wal_bytes: null,
    shm_bytes: 0,
    total_sqlite_bytes: null,
    page_size: null,
    page_count: null,
    freelist_page_count: null,
    reusable_bytes: null,
    schema_version: 14,
  },
  integrity: {
    startup_gates: "quick_and_foreign_keys",
    quick_check: {
      status: "ok",
      checked_at: "2026-07-23T00:00:00+00:00",
      violation_count: 0,
    },
    foreign_key_check: {
      status: null,
      checked_at: null,
      violation_count: null,
    },
  },
};

function health(matchedDevices: number) {
  return {
    status: "ok",
    database: "ok",
    migration_version: 14,
    collector: {
      enabled: true,
      subscribed_topics_count: 1,
      last_message_at: "2026-07-23T00:00:00+00:00",
      last_error: null,
      networks: [],
    },
    mqtt_discovery: {
      enabled: false,
      connected: false,
      published_entities_count: 0,
      last_publish_at: null,
      last_error: null,
    },
    topology: {
      enabled: false,
      manual_capture_enabled: false,
      capture_in_progress: false,
      last_capture_error: null,
    },
    home_assistant_enrichment: {
      enabled: true,
      matched_devices: matchedDevices,
      last_push_at: "2026-07-23T00:00:00+00:00",
    },
  };
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function emitEnrichmentUpdate() {
  act(() => {
    eventSourceTestState.emit(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT, {
      type: HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    });
    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

async function emitDelayedDashboardCompanion() {
  act(() => {
    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(700);
  });
  await flushAsyncWork();
}

async function emitOrdinaryDashboardUpdate() {
  act(() => {
    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

function metricValue(label: string): string {
  const metric = screen.getByText(label).parentElement;
  if (!metric) throw new Error(`Missing metric ${label}`);
  return metric.textContent ?? "";
}

function rowValue(label: string): string {
  const row = screen.getByText(label, { selector: "dt" }).closest("div");
  const value = row?.querySelector("dd");
  if (!value) throw new Error(`Missing row ${label}`);
  return value.textContent ?? "";
}

beforeEach(() => {
  vi.useFakeTimers();
  for (const mock of Object.values(apiMocks)) mock.mockReset();
  scenarioState.scenario = "";
  scenarioState.refreshStatus.mockReset();
  localStorage.clear();
  liveConnection.resetForTests();
  eventSourceTestState.reset();
  liveConnection.setAccessEnabled(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Home Assistant enrichment live refresh", () => {
  it("updates an open device inventory on rename and falls back after removal", async () => {
    apiMocks.devices
      .mockResolvedValueOnce({
        items: [
          deviceSummary({
            home_assistant_name: "Old Kitchen Lamp",
            home_assistant_area_name: "Old Kitchen",
          }),
        ],
      })
      .mockResolvedValueOnce({
        items: [
          deviceSummary({
            home_assistant_name: "Kitchen Lamp",
            home_assistant_area_name: "Kitchen",
          }),
        ],
      })
      .mockResolvedValueOnce({
        items: [
          deviceSummary({
            home_assistant_name: null,
            home_assistant_area_name: null,
          }),
        ],
      });

    render(
      <MemoryRouter>
        <DevicesPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Old Kitchen Lamp")).toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("Kitchen Lamp")).toBeInTheDocument();
    expect(
      screen.getByText("Zigbee2MQTT: z2m_kitchen_lamp"),
    ).toBeInTheDocument();

    await emitEnrichmentUpdate();
    expect(screen.getByText("z2m_kitchen_lamp")).toBeInTheDocument();
    expect(screen.queryByText("Kitchen Lamp")).not.toBeInTheDocument();
    expect(apiMocks.devices).toHaveBeenCalledTimes(3);
  });

  it("updates open Device Detail and Device Story without refreshing incidents or topology history", async () => {
    apiMocks.device
      .mockResolvedValueOnce(
        deviceDetail({
          home_assistant_name: "Old Kitchen Lamp",
          home_assistant_area_name: "Old Kitchen",
        }),
      )
      .mockResolvedValueOnce(
        deviceDetail({
          home_assistant_name: "Kitchen Lamp",
          home_assistant_area_name: "Kitchen",
        }),
      )
      .mockResolvedValueOnce(
        deviceDetail({
          home_assistant_name: null,
          home_assistant_area_name: null,
        }),
      );
    apiMocks.deviceStory
      .mockResolvedValueOnce(deviceStory("Old Kitchen"))
      .mockResolvedValueOnce(deviceStory("Kitchen"))
      .mockResolvedValueOnce(deviceStory(null));
    apiMocks.incidents.mockResolvedValue({ items: [], total: 0 });
    apiMocks.topologyDeviceSnapshotHistory.mockResolvedValue(
      emptySnapshotHistory(),
    );

    render(
      <MemoryRouter initialEntries={["/devices/home/0xa1"]}>
        <Routes>
          <Route
            path="/devices/:networkId/:ieeeAddress"
            element={<DeviceDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(
      screen.getByRole("heading", { name: "Old Kitchen Lamp" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Old Kitchen").length).toBeGreaterThan(0);

    await emitEnrichmentUpdate();
    expect(
      screen.getByRole("heading", { name: "Kitchen Lamp" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Kitchen").length).toBeGreaterThan(0);
    expect(apiMocks.device).toHaveBeenCalledTimes(2);
    expect(apiMocks.deviceStory).toHaveBeenCalledTimes(2);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);
    expect(apiMocks.topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(1);

    await emitEnrichmentUpdate();
    expect(
      screen.getByRole("heading", { name: "z2m_kitchen_lamp" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Home Assistant area")).not.toBeInTheDocument();
    expect(screen.getByText("HA areas not linked")).toBeInTheDocument();
    expect(apiMocks.device).toHaveBeenCalledTimes(3);
    expect(apiMocks.deviceStory).toHaveBeenCalledTimes(3);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);
    expect(apiMocks.topologyDeviceSnapshotHistory).toHaveBeenCalledTimes(1);
  });

  it("refreshes Overview coverage without refetching incident resources", async () => {
    apiMocks.dashboard
      .mockResolvedValueOnce(dashboardWithCoverage(true))
      .mockResolvedValueOnce(dashboardWithCoverage(false));
    apiMocks.incidents.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Coverage status unknown")).toBeInTheDocument();
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);

    await emitEnrichmentUpdate();
    expect(screen.queryByText("Coverage status unknown")).not.toBeInTheDocument();
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(2);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);
  });

  it("refreshes network summaries exactly once for the real event pair", async () => {
    apiMocks.networks
      .mockResolvedValueOnce({
        items: [networkWithCoverage(1)],
        total: 1,
      })
      .mockResolvedValueOnce({
        items: [networkWithCoverage(0)],
        total: 1,
      });

    render(
      <MemoryRouter>
        <NetworksPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(metricValue("Coverage")).toContain("1");

    await emitEnrichmentUpdate();

    expect(screen.queryByText("Coverage")).not.toBeInTheDocument();
    expect(apiMocks.networks).toHaveBeenCalledTimes(2);
  });

  it("refreshes device and network projections for an ordinary unattributed Dashboard update", async () => {
    apiMocks.devices
      .mockResolvedValueOnce({
        items: [deviceSummary({ home_assistant_name: "Accepted Device" })],
      })
      .mockResolvedValueOnce({
        items: [deviceSummary({ home_assistant_name: "Ordinary Device Update" })],
      });
    apiMocks.networks
      .mockResolvedValueOnce({
        items: [networkWithCoverage(1)],
        total: 1,
      })
      .mockResolvedValueOnce({
        items: [networkWithCoverage(0)],
        total: 1,
      });

    render(
      <MemoryRouter>
        <DevicesPage />
        <NetworksPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(screen.getByText("Accepted Device")).toBeInTheDocument();
    expect(apiMocks.devices).toHaveBeenCalledTimes(1);
    expect(apiMocks.networks).toHaveBeenCalledTimes(1);

    await emitOrdinaryDashboardUpdate();

    expect(screen.getByText("Ordinary Device Update")).toBeInTheDocument();
    expect(apiMocks.devices).toHaveBeenCalledTimes(2);
    expect(apiMocks.networks).toHaveBeenCalledTimes(2);
  });

  it("refreshes network and device projections without refetching incidents or timeline", async () => {
    apiMocks.network
      .mockResolvedValueOnce(networkWithCoverage(1))
      .mockResolvedValueOnce(networkWithCoverage(0));
    apiMocks.devices
      .mockResolvedValueOnce({
        items: [
          deviceSummary({
            decision: makeDecisionBadge({
              status: "improve_data_coverage",
              priority: "medium",
              headline_code: "device_data_coverage_limited",
              coverage_label_codes: ["ha_areas_not_linked"],
            }),
          }),
        ],
      })
      .mockResolvedValueOnce({
        items: [
          deviceSummary({
            home_assistant_name: "Kitchen Lamp",
            home_assistant_area_name: "Kitchen",
          }),
        ],
      });
    apiMocks.incidents.mockResolvedValue({ items: [], total: 0 });
    apiMocks.timeline.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter initialEntries={["/networks/home"]}>
        <Routes>
          <Route
            path="/networks/:networkId"
            element={<NetworkDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(metricValue("Coverage warnings")).toContain("1");

    await emitEnrichmentUpdate();
    expect(metricValue("Coverage warnings")).toContain("0");
    expect(apiMocks.network).toHaveBeenCalledTimes(2);
    expect(apiMocks.devices).toHaveBeenCalledTimes(2);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(2);
    expect(apiMocks.timeline).toHaveBeenCalledTimes(1);
  });

  it("ignores an attributed Dashboard companion even after the debounce window", async () => {
    apiMocks.dashboard
      .mockResolvedValueOnce(dashboardWithCoverage(true))
      .mockResolvedValueOnce(dashboardWithCoverage(false))
      .mockResolvedValueOnce(dashboardWithCoverage(false));
    apiMocks.incidents.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();

    act(() => {
      eventSourceTestState.emit(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT, {
        type: HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });
    await flushAsyncWork();
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(2);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);

    await emitDelayedDashboardCompanion();
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(2);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);

    act(() => {
      eventSourceTestState.emit("dashboard_updated", {
        type: "dashboard_updated",
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });
    await flushAsyncWork();
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(3);
    expect(apiMocks.incidents).toHaveBeenCalledTimes(1);
  });

  it("refreshes Settings enrichment health without refetching storage", async () => {
    apiMocks.health
      .mockResolvedValueOnce(health(1))
      .mockResolvedValueOnce(health(2));
    apiMocks.storageStatus.mockResolvedValue(storageStatus);

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(rowValue("Matched devices")).toBe("1");

    await emitEnrichmentUpdate();
    expect(rowValue("Matched devices")).toBe("2");
    expect(apiMocks.health).toHaveBeenCalledTimes(2);
    expect(apiMocks.storageStatus).toHaveBeenCalledTimes(1);
  });

  it("labels a retained enrichment count as last accepted after a failed refresh", async () => {
    apiMocks.health
      .mockResolvedValueOnce(health(1))
      .mockRejectedValueOnce(new Error("injected health refresh failure"));
    apiMocks.storageStatus.mockResolvedValue(storageStatus);

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    await flushAsyncWork();
    expect(rowValue("Matched devices")).toBe("1");

    await emitEnrichmentUpdate();

    expect(rowValue("Matched devices")).toBe("1");
    expect(
      screen.getByText(
        "Core health refresh failed — showing the last accepted status.",
      ),
    ).toBeInTheDocument();
    expect(apiMocks.health).toHaveBeenCalledTimes(2);
    expect(apiMocks.storageStatus).toHaveBeenCalledTimes(1);
  });
});
