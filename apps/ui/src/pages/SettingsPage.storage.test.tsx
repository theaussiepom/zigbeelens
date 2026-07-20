import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";

const storageStatus = vi.fn();
const health = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    storageStatus: (...args: unknown[]) => storageStatus(...args),
    health: (...args: unknown[]) => health(...args),
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
      mqtt_connected: false,
      mqtt_server: "mqtt://localhost",
      configured_networks: [{ id: "home", name: "Home", base_topic: "zigbee2mqtt" }],
      storage_path: "/tmp/x.sqlite",
      storage_ready: true,
      retention_days: 7,
      resolved_incident_retention_days: null,
      report_retention_days: null,
      maintenance_interval_hours: 24,
      features: {},
      data_mode: "mock",
      mock_mode: true,
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
    dataMode: "mock" as const,
    isScenarioMode: true,
  }),
}));

describe("SettingsPage storage card", () => {
  beforeEach(() => {
    storageStatus.mockReset();
    health.mockReset();
    health.mockResolvedValue({ status: "ok", database: "ok", migration_version: 12, collector: {} });
    storageStatus.mockResolvedValue({
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
        malformed_timestamps_by_category: { events: 2 },
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
        schema_version: 12,
      },
      integrity: {
        startup_gates: "quick_and_foreign_keys",
        quick_check: { status: "ok", checked_at: "2026-07-20T00:00:00+00:00", violation_count: 0 },
        foreign_key_check: { status: null, checked_at: null, violation_count: null },
      },
    });
  });

  it("renders retention copy and unknown deletion counts as em dash", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Storage and retention")).toBeInTheDocument();
    expect(screen.getByText("Kept indefinitely")).toBeInTheDocument();
    expect(screen.getByText("Until manually deleted")).toBeInTheDocument();
    expect(screen.getByText("Never run")).toBeInTheDocument();
    // Rows removed unknown → —
    const rows = screen.getAllByText("—");
    expect(rows.length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /purge/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /backup/i })).toBeNull();
  });
});
