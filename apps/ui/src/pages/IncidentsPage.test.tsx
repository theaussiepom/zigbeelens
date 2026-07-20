import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  networks: [
    { id: "home", name: "Home", base_topic: "zigbee2mqtt" },
    { id: "office", name: "Office", base_topic: "z2m-office" },
    { id: "garage", name: "Garage", base_topic: "z2m-garage" },
  ],
  nextCursor: null as string | null,
  loadMoreImpl: null as null | ((query: Record<string, unknown>) => Promise<unknown>),
}));

vi.mock("@/lib/api", () => ({
  api: {
    networks: vi.fn(() =>
      Promise.resolve({
        items: mockState.networks,
        total: mockState.networks.length,
      }),
    ),
    incidents: vi.fn((query: {
      network_id?: string;
      status?: string | string[];
      cursor?: string;
      scenario?: string;
      limit?: number;
    } = {}) => {
      if (query.cursor && mockState.loadMoreImpl) {
        return mockState.loadMoreImpl(query);
      }
      let items = mockState.incidents;
      if (query.network_id) {
        items = items.filter((inc) => inc.network_ids.includes(query.network_id!));
      }
      if (query.status) {
        const statuses = Array.isArray(query.status) ? query.status : [query.status];
        items = items.filter((inc) => statuses.includes(inc.status));
      }
      return Promise.resolve({
        items,
        total: items.length,
        limit: query.limit ?? 50,
        next_cursor: mockState.nextCursor,
      });
    }),
    incident: vi.fn(async () => mockState.detail),
  },
}));

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: mockState.scenario,
    status: { topology: { enabled: true } },
  }),
}));

vi.mock("@/hooks/useLiveResource", async () => {
  const React = await import("react");
  return {
    useLiveResource: (
      fetcher: () => Promise<unknown> | unknown,
      deps: unknown[] = [],
    ) => {
      const source = fetcher.toString();
      const [data, setData] = React.useState<unknown>(() => {
        if (/\bapi\.incident\s*\(/.test(source) && !/\bapi\.incidents\s*\(/.test(source)) {
          return mockState.detail;
        }
        return null;
      });
      const [loading, setLoading] = React.useState(data == null);
      React.useEffect(() => {
        let active = true;
        setLoading(true);
        void Promise.resolve(fetcher()).then((result) => {
          if (!active) return;
          setData(result);
          setLoading(false);
        });
        return () => {
          active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, deps);
      if (/\bapi\.incident\s*\(/.test(source) && !/\bapi\.incidents\s*\(/.test(source)) {
        return {
          data: mockState.detail,
          loading: false,
          error: null,
          refetch: vi.fn(),
        };
      }
      return {
        data,
        loading,
        error: null,
        refetch: vi.fn(),
      };
    },
  };
});

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
    resolved_at: null,
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
    mockState.nextCursor = null;
    mockState.loadMoreImpl = null;
  });

  it("renders lifecycle groups and current decision summary", async () => {
    renderList();
    expect(await screen.findByText("Open · 1")).toBeInTheDocument();
    expect(screen.getByText("Kitchen Plug unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/Current device decisions:.*Worth reviewing/i),
    ).toBeInTheDocument();
  });

  it("does not render lens/health interpretation or list evidence", async () => {
    renderList();
    expect(await screen.findByText("Kitchen Plug unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Looks offline in lens")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
    expect(screen.queryByText(/Evidence: First stored evidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Limitation: First stored limitation/i)).not.toBeInTheDocument();
    expect(screen.queryByText("worth_reviewing")).not.toBeInTheDocument();
  });

  it("uses record-oriented empty copy", async () => {
    mockState.incidents = [];
    renderList();
    expect(await screen.findByText("No incident records")).toBeInTheDocument();
    expect(screen.getByLabelText("Network")).toBeInTheDocument();
    expect(screen.getByLabelText("Lifecycle")).toBeInTheDocument();
    expect(screen.queryByText(/look stable/i)).not.toBeInTheDocument();
  });

  it("keeps filters and clear action when lifecycle filter returns zero", async () => {
    const user = userEvent.setup();
    mockState.incidents = [makeIncident({ status: "open" })];
    renderList();
    await screen.findByText("Kitchen Plug unavailable");

    await user.selectOptions(screen.getByLabelText("Lifecycle"), "resolved");
    expect(await screen.findByText("No incidents match")).toBeInTheDocument();
    expect(screen.getByLabelText("Lifecycle")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /clear filters/i }).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /clear filters/i })[0]!);
    await waitFor(() => {
      expect(screen.getByText("Kitchen Plug unavailable")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Lifecycle")).toHaveValue("");
  });

  it("keeps filters and clear action when network filter returns zero", async () => {
    const user = userEvent.setup();
    mockState.incidents = [makeIncident({ network_ids: ["home"] })];
    renderList();
    await screen.findByText("Kitchen Plug unavailable");

    await user.selectOptions(screen.getByLabelText("Network"), "garage");
    expect(await screen.findByText("No incidents match")).toBeInTheDocument();
    expect(screen.getByLabelText("Network")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /clear filters/i })[0]!);
    await waitFor(() => {
      expect(screen.getByText("Kitchen Plug unavailable")).toBeInTheDocument();
    });
  });

  it("shows configured networks even when absent from the first page", async () => {
    mockState.incidents = [makeIncident({ network_ids: ["home"] })];
    renderList();
    await screen.findByText("Kitchen Plug unavailable");
    const networkSelect = screen.getByLabelText("Network");
    expect(within(networkSelect).getByRole("option", { name: "garage" })).toBeInTheDocument();
    expect(within(networkSelect).getByRole("option", { name: "office" })).toBeInTheDocument();
  });

  it("keeps Load more when local filters hide all loaded items", async () => {
    const user = userEvent.setup();
    mockState.incidents = [makeIncident()];
    mockState.nextCursor = "cursor-next";
    renderList();
    await screen.findByText("Kitchen Plug unavailable");
    expect(screen.getByRole("button", { name: /load more/i })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/device, friendly name/i), "zzzz-no-match");
    expect(await screen.findByText("No incidents match")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /load more/i })).toBeInTheDocument();
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
            decision: {
              status: "watch",
              priority: "medium",
              headline_code: "stale_last_seen",
              coverage_label_codes: [],
            },
          },
        ],
      }),
    ];
    renderList();
    await waitFor(() => {
      expect(screen.getByText("Kitchen Plug unavailable")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Incident decision/i)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Network"), "office");
    await waitFor(() => {
      expect(screen.queryByText("Kitchen Plug unavailable")).not.toBeInTheDocument();
      expect(screen.getByText("Office motion unavailable")).toBeInTheDocument();
    });
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

  it("uses safe unknown for unknown future status", () => {
    mockState.detail = makeIncident({
      affected_devices: [
        {
          network_id: "home",
          ieee_address: "0xa1",
          friendly_name: "Kitchen Plug",
          decision: {
            status: "future_status_v2",
            priority: "high",
            headline_code: "future_headline_v2",
            coverage_label_codes: [],
          },
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
