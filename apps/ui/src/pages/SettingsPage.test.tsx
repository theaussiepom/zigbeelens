import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";

type LiveResourceState = {
  data: unknown;
  error: string | null;
  loading: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

const storagePayload = {
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
    quick_check: { status: "ok", checked_at: "2026-07-20T00:00:00+00:00", violation_count: 0 },
    foreign_key_check: { status: null, checked_at: null, violation_count: null },
  },
};

const zeroHealth = {
  status: "ok",
  database: "ok",
  migration_version: 14,
  collector: {
    enabled: true,
    subscribed_topics_count: 0,
    last_message_at: null,
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
    enabled: true,
    manual_capture_enabled: false,
    capture_in_progress: false,
    last_capture_error: null,
  },
  home_assistant_enrichment: {
    enabled: false,
    matched_devices: 0,
    last_push_at: null,
  },
};

const positiveHealth = {
  ...zeroHealth,
  collector: {
    ...zeroHealth.collector,
    subscribed_topics_count: 4,
    last_message_at: "2026-07-20T00:00:00+00:00",
  },
  mqtt_discovery: {
    ...zeroHealth.mqtt_discovery,
    enabled: true,
    connected: true,
    published_entities_count: 12,
  },
  home_assistant_enrichment: {
    enabled: true,
    matched_devices: 3,
    last_push_at: "2026-07-20T00:00:00+00:00",
  },
};

let healthResource: LiveResourceState;
let storageResource: LiveResourceState;

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (
    _loader: () => Promise<unknown>,
    _deps: unknown[],
    opts?: { refetchOn?: string[] },
  ) => {
    if (opts?.refetchOn?.includes("storage_maintenance_completed")) {
      return storageResource;
    }
    if (opts?.refetchOn?.includes("collector_status")) {
      return healthResource;
    }
    return { data: null, error: null, loading: false, refetch: vi.fn() };
  },
}));

vi.mock("@/lib/api", () => ({
  api: {
    storageStatus: vi.fn(),
    health: vi.fn(),
  },
}));

vi.mock("@/context/BrowserAuthContext", () => ({
  useAuth: () => ({
    authMethod: "none",
    browserSessionEnabled: false,
    expiresAt: null,
    logout: vi.fn(),
    logoutBusy: false,
    logoutError: null,
  }),
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    status: {
      version: "0.0.0-test",
      uptime_seconds: 1,
      mqtt_connected: true,
      mqtt_server: "mqtt://localhost",
      configured_networks: [{ id: "home", name: "Home", base_topic: "zigbee2mqtt" }],
      storage_path: "/tmp/x.sqlite",
      storage_ready: true,
      retention_days: 7,
      resolved_incident_retention_days: null,
      report_retention_days: null,
      maintenance_interval_hours: 24,
      features: { mqtt_discovery: true },
      topology: { enabled: true },
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
    refreshStatus: vi.fn(),
    scenario: "",
    dataMode: "live" as const,
    isScenarioMode: false,
  }),
}));

function rowValue(label: string): string {
  const dt = screen.getByText(label, { selector: "dt" });
  const row = dt.closest("div");
  const dd = row?.querySelector("dd");
  if (!dd) throw new Error(`missing dd for ${label}`);
  return dd.textContent ?? "";
}

describe("SettingsPage health counts", () => {
  beforeEach(() => {
    healthResource = {
      data: null,
      error: null,
      loading: true,
      refetch: vi.fn(),
    };
    storageResource = {
      data: storagePayload,
      error: null,
      loading: false,
      refetch: vi.fn(),
    };
  });

  it("shows unknown for subscribed topics, published entities, and matched devices while health loads", () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(rowValue("Subscribed topics")).toBe("—");
    expect(rowValue("Published entities")).toBe("—");
    expect(rowValue("Matched devices")).toBe("—");
    expect(rowValue("Publisher connected")).toBe("—");
    // Collector Enabled is health-owned; MQTT Discovery Enabled may still use config.
    const enabledLabels = screen.getAllByText("Enabled", { selector: "dt" });
    expect(enabledLabels[0]?.closest("div")?.querySelector("dd")?.textContent).toBe("—");
    expect(enabledLabels[1]?.closest("div")?.querySelector("dd")?.textContent).toBe("yes");
  });

  it("keeps unknown counts when health failed with no accepted data", () => {
    healthResource = {
      data: null,
      error: "health unavailable",
      loading: false,
      refetch: vi.fn(),
    };
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(rowValue("Subscribed topics")).toBe("—");
    expect(rowValue("Published entities")).toBe("—");
    expect(rowValue("Matched devices")).toBe("—");
  });

  it("renders explicit measured zero counts when health is accepted", () => {
    healthResource = {
      data: zeroHealth,
      error: null,
      loading: false,
      refetch: vi.fn(),
    };
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(rowValue("Subscribed topics")).toBe("0");
    expect(rowValue("Published entities")).toBe("0");
    expect(rowValue("Matched devices")).toBe("0");
  });

  it("renders positive measured counts when health is accepted", () => {
    healthResource = {
      data: positiveHealth,
      error: null,
      loading: false,
      refetch: vi.fn(),
    };
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(rowValue("Subscribed topics")).toBe("4");
    expect(rowValue("Published entities")).toBe("12");
    expect(rowValue("Matched devices")).toBe("3");
  });

  it("keeps previously accepted health counts visible after a refresh failure", () => {
    healthResource = {
      data: positiveHealth,
      error: "refresh failed",
      loading: false,
      refetch: vi.fn(),
    };
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(rowValue("Subscribed topics")).toBe("4");
    expect(rowValue("Published entities")).toBe("12");
    expect(rowValue("Matched devices")).toBe("3");
  });
});
