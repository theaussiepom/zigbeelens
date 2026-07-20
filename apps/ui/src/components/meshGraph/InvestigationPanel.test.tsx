import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { InvestigationCard } from "@/types/topology";
import { InvestigationPanel } from "./InvestigationPanel";

function makeCard(overrides: Partial<InvestigationCard> = {}): InvestigationCard {
  return {
    id: "card-default",
    type: "recent_missing_cluster",
    priority: "Worth checking",
    score: 8,
    title: "Several recent missing links involve Live Lamp",
    summary: "Live Lamp has 3 recent missing links.",
    why_it_matters: "Worth checking power and reporting.",
    supporting_evidence: ["3 recent missing links involve Live Lamp."],
    limitations: ["Generic limitation."],
    suggested_next_steps: ["Check device power."],
    device_ieees: ["0xe1"],
    edge_ids: ["hist-neighbor-0xe1|0xe2"],
    primary_device_ieee: "0xe1",
    primary_neighbourhood_ieee: null,
    created_from_evidence_classes: ["historical_neighbor"],
    latest_supporting_evidence_at: "2026-07-04T10:00:00+00:00",
    action_group: "check_power_reporting",
    ...overrides,
  };
}

function renderPanel(
  investigations: InvestigationCard[],
  options: {
    activeInvestigationId?: string | null;
    canOpenPrimaryDevice?: boolean;
  } = {},
) {
  const onFocus = vi.fn();
  const onClearFocus = vi.fn();
  const onOpenPrimaryDevice = vi.fn();
  render(
    <InvestigationPanel
      investigations={investigations}
      activeInvestigationId={options.activeInvestigationId ?? null}
      onFocus={onFocus}
      onClearFocus={onClearFocus}
      canOpenPrimaryDevice={() => options.canOpenPrimaryDevice ?? true}
      onOpenPrimaryDevice={onOpenPrimaryDevice}
    />,
  );
  return { onFocus, onClearFocus, onOpenPrimaryDevice };
}

describe("InvestigationPanel accessible action names", () => {
  it("renders unique Focus/View names for repeated shared_availability_event titles", () => {
    const cards = [
      makeCard({
        id: "shared-a",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "11 devices went offline during a shared availability event lasting about 4 minutes.",
        latest_supporting_evidence_at: "2026-07-20T10:32:00Z",
      }),
      makeCard({
        id: "shared-b",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "6 devices went offline during a shared availability event lasting about 2 minutes.",
        latest_supporting_evidence_at: "2026-07-19T08:00:00Z",
      }),
    ];
    renderPanel(cards);

    const focusA = screen.getByRole("button", {
      name: /^Focus graph: Several devices went offline around the same time — 11 devices/i,
    });
    const focusB = screen.getByRole("button", {
      name: /^Focus graph: Several devices went offline around the same time — 6 devices/i,
    });
    expect(focusA).not.toBe(focusB);
    expect(focusA).toHaveTextContent("Focus graph");

    expect(
      screen.getByRole("button", {
        name: /^View details: Several devices went offline around the same time — 11 devices/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /^View details: Several devices went offline around the same time — 6 devices/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders unique action names for repeated issue_cluster neighbourhood summaries", () => {
    renderPanel([
      makeCard({
        id: "issue-a",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "4 devices needing attention have recent evidence near the same observed router neighbourhood (Hall Router).",
      }),
      makeCard({
        id: "issue-b",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "3 devices needing attention have recent evidence near the same observed router neighbourhood (Garage Router).",
      }),
    ]);

    expect(
      screen.getByRole("button", {
        name: /Focus graph: .*Hall Router/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Focus graph: .*Garage Router/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /View details: .*Hall Router/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /View details: .*Garage Router/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders unique action names for repeated passive groups distinguished by evidence time", () => {
    renderPanel([
      makeCard({
        id: "passive-a",
        type: "passive_instability_group",
        action_group: "watch_only",
        priority: "Lower priority",
        title: "Devices repeatedly went offline around the same time",
        summary: "5 devices showed repeated related offline timing in passive observations.",
        latest_supporting_evidence_at: "2026-07-20T12:00:00Z",
      }),
      makeCard({
        id: "passive-b",
        type: "passive_instability_group",
        action_group: "watch_only",
        priority: "Lower priority",
        title: "Devices repeatedly went offline around the same time",
        summary: "5 devices showed repeated related offline timing in passive observations.",
        latest_supporting_evidence_at: "2026-07-19T12:00:00Z",
      }),
    ]);

    expect(
      screen.getByRole("button", {
        name: /Focus graph: .*latest evidence 2026-07-20T12:00:00Z/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Focus graph: .*latest evidence 2026-07-19T12:00:00Z/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /View details: .*latest evidence 2026-07-20T12:00:00Z/i,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Clear focus:/i })).not.toBeInTheDocument();
  });

  it("renders distinct router-area Focus/Open/View names without duplicated action-group wording", () => {
    renderPanel(
      [
        makeCard({
          id: "router-a",
          type: "router_neighbourhood_review",
          action_group: "review_observed_router_area",
          primary_neighbourhood_ieee: "0xr1",
          title: "Review observed router area: Hall Router",
          summary: "Evidence concentrates around Hall Router.",
        }),
        makeCard({
          id: "router-b",
          type: "router_neighbourhood_review",
          action_group: "review_observed_router_area",
          primary_neighbourhood_ieee: "0xr2",
          title: "Review observed router area: Garage Router",
          summary: "Evidence concentrates around Garage Router.",
        }),
      ],
      { canOpenPrimaryDevice: true },
    );

    const hallFocus = screen.getByRole("button", {
      name: "Focus router area: Review observed router area: Hall Router",
    });
    const garageFocus = screen.getByRole("button", {
      name: "Focus router area: Review observed router area: Garage Router",
    });
    expect(hallFocus).toHaveTextContent("Focus router area");
    expect(garageFocus).toHaveTextContent("Focus router area");

    expect(
      screen.getByRole("button", {
        name: "Open router details: Review observed router area: Hall Router",
      }),
    ).toHaveTextContent("Open router details");
    expect(
      screen.getByRole("button", {
        name: "Open router details: Review observed router area: Garage Router",
      }),
    ).toHaveTextContent("Open router details");

    expect(
      screen.getByRole("button", {
        name: "View details: Review observed router area: Hall Router",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "View details: Review observed router area: Garage Router",
      }),
    ).toBeInTheDocument();

    expect(document.body.textContent).not.toMatch(
      /Review observed router area — Review observed router area/i,
    );

    const panel = screen.getByRole("region", { name: /where to look first/i });
    const cards = within(panel).getAllByTestId("investigation-card");
    expect(cards).toHaveLength(2);
  });

  it("exposes unique Clear focus names when a repeated-title card is active", () => {
    renderPanel(
      [
        makeCard({
          id: "shared-a",
          type: "shared_availability_event",
          action_group: "investigate_shared_event",
          title: "Several devices went offline around the same time",
          summary:
            "11 devices went offline during a shared availability event lasting about 4 minutes.",
          latest_supporting_evidence_at: "2026-07-20T10:32:00Z",
        }),
        makeCard({
          id: "shared-b",
          type: "shared_availability_event",
          action_group: "investigate_shared_event",
          title: "Several devices went offline around the same time",
          summary:
            "6 devices went offline during a shared availability event lasting about 2 minutes.",
          latest_supporting_evidence_at: "2026-07-19T08:00:00Z",
        }),
      ],
      { activeInvestigationId: "shared-b" },
    );

    expect(
      screen.getByRole("button", {
        name: /^Clear focus: Several devices went offline around the same time — 6 devices/i,
      }),
    ).toHaveTextContent("Clear focus");
    expect(
      screen.getByRole("button", {
        name: /^Focus graph: Several devices went offline around the same time — 11 devices/i,
      }),
    ).toBeInTheDocument();
  });
});
