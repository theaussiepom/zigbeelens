import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Incident } from "@zigbeelens/shared";
import { IncidentDetailPage, IncidentsPage } from "./IncidentsPage";
import {
  decisionStatusLabel,
  headlineText,
} from "@/viewModels/decisionCopy";

const mockState = vi.hoisted(() => ({
  incidents: [] as Incident[],
  detail: null as Incident | null,
  scenario: "",
}));

vi.mock("@/lib/api", () => ({
  api: {
    incidents: vi.fn(async () => ({ items: mockState.incidents })),
    incident: vi.fn(async () => mockState.detail),
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
    void fetcher();
    const source = fetcher.toString();
    if (/\bapi\.incident\s*\(/.test(source) && !/\bapi\.incidents\s*\(/.test(source)) {
      return {
        data: mockState.detail,
        loading: false,
        error: null,
        refetch: vi.fn(),
      };
    }
    return {
      data: mockState.incidents,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
  },
}));

function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    type: "single_device_unavailable",
    status: "open",
    severity: "incident",
    scope: "device",
    confidence: "medium",
    title: "Kitchen Plug unavailable",
    summary: "Kitchen Plug stopped reporting.",
    interpretation: "Legacy interpretation for the record.",
    network_ids: ["home"],
    affected_device_count: 1,
    affected_devices: [
      {
        network_id: "home",
        ieee_address: "0xa1",
        friendly_name: "Kitchen Plug",
        health_primary: "unavailable",
        lens_bucket: "needs_attention",
        lens_bucket_label: "Needs attention",
        lens_bucket_reason: "Looks offline in lens",
        decision: {
          status: "worth_reviewing",
          priority: "high",
          headline_code: "current_issue_present",
          coverage_label_codes: [],
        },
      },
    ],
    opened_at: "2026-07-13T00:00:00Z",
    updated_at: "2026-07-13T01:00:00Z",
    evidence: [{ id: "e1", kind: "stored", summary: "First stored evidence" }],
    counter_evidence: [{ id: "c1", kind: "stored", summary: "Counter evidence" }],
    limitations: [{ id: "l1", summary: "First stored limitation" }],
    timeline: [
      {
        id: "t1",
        timestamp: "2026-07-13T00:00:00Z",
        kind: "incident_opened",
        severity: "incident",
        title: "Opened",
        summary: "Incident opened",
        incident_id: "inc-1",
      },
    ],
    conclusion: {
      classification: "single_device_unavailable",
      severity: "incident",
      scope: "device",
      confidence: "medium",
      summary: "Kitchen Plug stopped reporting.",
      evidence: [],
      counter_evidence: [],
      limitations: [],
    },
    ...overrides,
  };
}

function renderList() {
  return render(
    <MemoryRouter initialEntries={["/incidents"]}>
      <Routes>
        <Route path="/incidents" element={<IncidentsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/incidents/inc-1"]}>
      <Routes>
        <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("IncidentsPage list", () => {
  beforeEach(() => {
    mockState.scenario = "";
    mockState.incidents = [makeIncident()];
    mockState.detail = null;
  });

  it("renders lifecycle groups and current decision summary", () => {
    renderList();
    expect(screen.getByText("Open · 1")).toBeInTheDocument();
    expect(screen.getByText("Kitchen Plug unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/Current device decisions:.*Worth reviewing/i),
    ).toBeInTheDocument();
  });

  it("does not render lens/health interpretation or list evidence", () => {
    renderList();
    expect(screen.queryByText("Looks offline in lens")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
    expect(screen.queryByText(/Evidence: First stored evidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Limitation: First stored limitation/i)).not.toBeInTheDocument();
    expect(screen.queryByText("worth_reviewing")).not.toBeInTheDocument();
  });

  it("uses record-oriented empty copy", () => {
    mockState.incidents = [];
    renderList();
    expect(screen.getByText("No incident records")).toBeInTheDocument();
    expect(screen.queryByText(/look stable/i)).not.toBeInTheDocument();
  });

  it("filters by network/lifecycle/type/scope/search without severity filter", async () => {
    const user = userEvent.setup();
    mockState.incidents = [
      makeIncident(),
      makeIncident({
        id: "inc-2",
        title: "Office motion unavailable",
        status: "watching",
        network_ids: ["office"],
        type: "possible_mesh_segment_issue",
        scope: "mesh_segment",
        affected_devices: [
          {
            network_id: "office",
            ieee_address: "0xb1",
            friendly_name: "Office motion",
            health_primary: "unavailable",
            lens_bucket: "needs_attention",
            lens_bucket_label: "Needs attention",
            lens_bucket_reason: "",
            decision: null,
          },
        ],
      }),
    ];
    renderList();
    expect(screen.queryByLabelText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Incident decision/i)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Network"), "office");
    expect(screen.queryByText("Kitchen Plug unavailable")).not.toBeInTheDocument();
    expect(screen.getByText("Office motion unavailable")).toBeInTheDocument();
  });

  it("list source does not hard-code decision status switches", () => {
    const pagePath = join(dirname(fileURLToPath(import.meta.url)), "IncidentsPage.tsx");
    const source = readFileSync(pagePath, "utf8");
    expect(source).not.toMatch(/health_primary/);
    expect(source).not.toMatch(/lens_bucket/);
    expect(source).not.toMatch(/LensBucketBadge/);
    expect(source).not.toMatch(/routerCandidates/);
    expect(source).not.toMatch(/What ZigbeeLens thinks/);
    expect(source).not.toMatch(/review_first/);
    expect(source).not.toMatch(/worth_reviewing/);
    expect(source).not.toMatch(/improve_data_coverage/);
    expect(source).not.toMatch(/no_notable_change/);
  });
});

describe("IncidentDetailPage", () => {
  beforeEach(() => {
    mockState.scenario = "";
    mockState.detail = makeIncident();
    mockState.incidents = [];
  });

  it("leads with lifecycle and incident record summary", () => {
    renderDetail();
    expect(screen.getByRole("heading", { name: "Kitchen Plug unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Incident record")).toBeInTheDocument();
    expect(screen.getByText("Kitchen Plug stopped reporting.")).toBeInTheDocument();
    expect(screen.queryByText("What ZigbeeLens thinks")).not.toBeInTheDocument();
  });

  it("shows historical recorded interpretation when distinct", () => {
    renderDetail();
    expect(screen.getByText("Recorded interpretation")).toBeInTheDocument();
    expect(screen.getByText("Legacy interpretation for the record.")).toBeInTheDocument();
  });

  it("renders current device decision badge and headline", () => {
    renderDetail();
    expect(screen.getByText("Current device decisions")).toBeInTheDocument();
    expect(screen.getByText(decisionStatusLabel("worth_reviewing"))).toBeInTheDocument();
    expect(screen.getByText(headlineText("current_issue_present"))).toBeInTheDocument();
    expect(screen.getByText("View device →")).toBeInTheDocument();
    expect(screen.queryByText("Looks offline in lens")).not.toBeInTheDocument();
    expect(screen.queryByText("Related router candidates")).not.toBeInTheDocument();
  });

  it("uses safe unknown for null decision", () => {
    mockState.detail = makeIncident({
      affected_devices: [
        {
          network_id: "home",
          ieee_address: "0xa1",
          friendly_name: "Kitchen Plug",
          health_primary: "healthy",
          lens_bucket: "healthy",
          lens_bucket_label: "Healthy",
          lens_bucket_reason: "Looks fine",
          decision: null,
        },
      ],
    });
    renderDetail();
    expect(screen.getByText("Status unknown")).toBeInTheDocument();
    expect(screen.getByText("Device story summary unavailable.")).toBeInTheDocument();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
  });

  it("keeps stored evidence, limitations and timeline", () => {
    renderDetail();
    expect(screen.getByText("Stored incident evidence")).toBeInTheDocument();
    expect(screen.getByText("First stored evidence")).toBeInTheDocument();
    expect(screen.getByText("Counter evidence")).toBeInTheDocument();
    expect(screen.getByText("First stored limitation")).toBeInTheDocument();
    expect(screen.getByText("Timeline")).toBeInTheDocument();
  });

  it("shows a record-oriented snippet with mapped decisions", () => {
    renderDetail();
    expect(screen.getByText("Incident record snippet")).toBeInTheDocument();
    const snippet = screen.getByText(/# Kitchen Plug unavailable/).closest("pre");
    expect(snippet).toBeTruthy();
    expect(snippet?.textContent).toContain("## Recorded summary");
    expect(snippet?.textContent).toContain("## Current device decisions");
    expect(snippet?.textContent).toContain(decisionStatusLabel("worth_reviewing"));
    expect(snippet?.textContent).not.toContain("worth_reviewing");
    expect(snippet?.textContent).not.toContain("What ZigbeeLens thinks");
  });

  it("uses scenario DTO decisions without inventing live overrides", () => {
    mockState.scenario = "offline_cluster";
    mockState.detail = makeIncident({
      affected_devices: [
        {
          network_id: "home",
          ieee_address: "0xa1",
          friendly_name: "Kitchen Plug",
          health_primary: "healthy",
          lens_bucket: "healthy",
          lens_bucket_label: "Healthy",
          lens_bucket_reason: "Live-looking lens",
          decision: {
            status: "review_first",
            priority: "high",
            headline_code: "current_issue_present",
            coverage_label_codes: [],
          },
        },
      ],
    });
    renderDetail();
    expect(screen.getByText(decisionStatusLabel("review_first"))).toBeInTheDocument();
    expect(screen.queryByText("Live-looking lens")).not.toBeInTheDocument();
    expect(screen.queryByText(decisionStatusLabel("watch"))).not.toBeInTheDocument();
  });
});
