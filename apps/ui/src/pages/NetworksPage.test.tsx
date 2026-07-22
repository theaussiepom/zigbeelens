import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Incident, TimelineEvent } from "@zigbeelens/shared";
import { makeNetworkSummary } from "@/test/decisionFixtures";
import { NetworkDetailPage } from "./NetworksPage";

type ResourceState = {
  data: unknown;
  error: string | null;
  loading: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

const resources = vi.hoisted(() => ({
  network: null as ResourceState | null,
  devices: null as ResourceState | null,
  activeIncidents: null as ResourceState | null,
  resolvedIncidents: null as ResourceState | null,
  timeline: null as ResourceState | null,
}));

vi.mock("@/hooks/useLiveResource", () => ({
  useLiveResource: (fetcher: () => unknown) => {
    const source = fetcher.toString();
    if (source.includes("api.network(")) return resources.network;
    if (source.includes("api.devices(")) return resources.devices;
    if (source.includes("watching")) return resources.activeIncidents;
    if (source.includes("resolved")) return resources.resolvedIncidents;
    if (source.includes("api.timeline(")) return resources.timeline;
    throw new Error(`Unexpected resource: ${source}`);
  },
}));

vi.mock("@/lib/api", () => ({
  api: {
    network: vi.fn(),
    devices: vi.fn(),
    incidents: vi.fn(),
    timeline: vi.fn(),
  },
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: "",
    status: { topology: { enabled: false } },
  }),
}));

vi.mock("@/components/reports/ContextualReportDialog", () => ({
  ContextualReportDialog: () => null,
}));

function state(data: unknown, overrides: Partial<ResourceState> = {}): ResourceState {
  return {
    data,
    error: null,
    loading: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    title: "Kitchen sensor incident",
    status: "open",
    type: "single_device_unavailable",
    severity: "watch",
    scope: "device",
    confidence: "medium",
    summary: "Stored incident evidence.",
    interpretation: "",
    network_ids: ["home"],
    affected_device_count: 0,
    affected_devices: [],
    opened_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T01:00:00Z",
    resolved_at: null,
    evidence: [],
    counter_evidence: [],
    limitations: [],
    timeline: [],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "watch",
      scope: "device",
      confidence: "medium",
      summary: "Stored incident evidence.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

function makeTimelineEvent(overrides: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id: "event-1",
    timestamp: "2026-07-20T01:00:00Z",
    kind: "availability",
    severity: "watch",
    network_id: "home",
    title: "Device availability changed",
    summary: "Stored timeline evidence.",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/networks/home"]}>
      <Routes>
        <Route path="/networks/:networkId" element={<NetworkDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  resources.network = state(makeNetworkSummary({ device_count: 1 }));
  resources.devices = state([]);
  resources.activeIncidents = state([]);
  resources.resolvedIncidents = state([]);
  resources.timeline = state([]);
});

describe("NetworkDetailPage active incident resource states", () => {
  it("shows section-local loading without factual empty copy", () => {
    resources.activeIncidents = state(null, { loading: true });
    renderPage();
    expect(screen.getByText("Loading active incidents…")).toBeInTheDocument();
    expect(screen.queryByText("No active incidents on this network")).not.toBeInTheDocument();
  });

  it("shows section-local unavailable state with Retry", () => {
    resources.activeIncidents = state(null, { error: "request failed" });
    renderPage();
    expect(screen.getByText("Active incidents are unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry active incidents" })).toBeInTheDocument();
    expect(screen.queryByText("No active incidents on this network")).not.toBeInTheDocument();
  });

  it("shows factual empty copy only for an accepted empty result", () => {
    renderPage();
    expect(screen.getByText("No active incidents on this network")).toBeInTheDocument();
  });

  it("renders accepted incidents", () => {
    resources.activeIncidents = state([makeIncident()]);
    renderPage();
    expect(screen.getByText("Kitchen sensor incident")).toBeInTheDocument();
    expect(screen.queryByText("No active incidents on this network")).not.toBeInTheDocument();
  });

  it("retains accepted incidents and adds a refresh warning with Retry", () => {
    resources.activeIncidents = state([makeIncident()], { error: "refresh failed" });
    renderPage();
    expect(screen.getByText("Kitchen sensor incident")).toBeInTheDocument();
    expect(
      screen.getByText("Active incidents could not be refreshed. Showing the last loaded results."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry active incidents" })).toBeInTheDocument();
  });
});

describe("NetworkDetailPage recent timeline resource states", () => {
  it("shows section-local loading without factual empty copy", () => {
    resources.timeline = state(null, { loading: true });
    renderPage();
    expect(screen.getByText("Loading recent events…")).toBeInTheDocument();
    expect(screen.queryByText("No recent events.")).not.toBeInTheDocument();
  });

  it("shows section-local unavailable state with Retry", () => {
    resources.timeline = state(null, { error: "request failed" });
    renderPage();
    expect(screen.getByText("Recent events are unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry recent events" })).toBeInTheDocument();
    expect(screen.queryByText("No recent events.")).not.toBeInTheDocument();
  });

  it("shows factual empty copy only for an accepted empty result", () => {
    renderPage();
    expect(screen.getByText("No recent events.")).toBeInTheDocument();
  });

  it("renders accepted timeline events", () => {
    resources.timeline = state([makeTimelineEvent()]);
    renderPage();
    expect(screen.getByText("Device availability changed")).toBeInTheDocument();
    expect(screen.queryByText("No recent events.")).not.toBeInTheDocument();
  });

  it("retains accepted events and adds a refresh warning with Retry", () => {
    resources.timeline = state([makeTimelineEvent()], { error: "refresh failed" });
    renderPage();
    expect(screen.getByText("Device availability changed")).toBeInTheDocument();
    expect(
      screen.getByText("Recent events could not be refreshed. Showing the last loaded timeline."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry recent events" })).toBeInTheDocument();
  });

  it("gives simultaneous incident and timeline retries unique accessible names", () => {
    resources.activeIncidents = state(null, { error: "incident request failed" });
    resources.timeline = state(null, { error: "timeline request failed" });

    renderPage();

    const retryNames = screen.getAllByRole("button", { name: /^Retry / }).map(
      (button) => button.getAttribute("aria-label") ?? button.textContent,
    );
    expect(retryNames).toEqual(["Retry active incidents", "Retry recent events"]);
    expect(new Set(retryNames).size).toBe(retryNames.length);
  });
});
