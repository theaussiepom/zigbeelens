import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { InvestigationCard } from "@/types/topology";
import {
  INVESTIGATION_CARDS_INITIALLY_VISIBLE,
  InvestigationPanel,
} from "./InvestigationPanel";

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
    onFocus?: (card: InvestigationCard) => void;
  } = {},
) {
  const onFocus = options.onFocus ?? vi.fn();
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

function StatefulInvestigationPanel({
  investigations,
  initialActiveInvestigationId = null,
}: {
  investigations: InvestigationCard[];
  initialActiveInvestigationId?: string | null;
}) {
  const [activeInvestigationId, setActiveInvestigationId] = useState<string | null>(
    initialActiveInvestigationId,
  );
  return (
    <InvestigationPanel
      investigations={investigations}
      activeInvestigationId={activeInvestigationId}
      onFocus={(card) => setActiveInvestigationId(card.id)}
      onClearFocus={() => setActiveInvestigationId(null)}
    />
  );
}

function makeRankedCards(count: number): InvestigationCard[] {
  return Array.from({ length: count }, (_, index) => {
    const rank = index + 1;
    return makeCard({
      id: `ranked-${rank}`,
      title: `Ranked investigation ${rank}`,
      summary: `Current summary ${rank}`,
      supporting_evidence: [`Current evidence ${rank}`],
    });
  });
}

function visibleCardIds(panel: HTMLElement): string[] {
  return within(panel)
    .getAllByTestId("investigation-card")
    .map((card) => card.dataset.investigationId ?? "");
}

function cardWithId(panel: HTMLElement, id: string): HTMLElement {
  const card = within(panel)
    .getAllByTestId("investigation-card")
    .find((candidate) => candidate.dataset.investigationId === id);
  expect(card).toBeDefined();
  return card!;
}

describe("InvestigationPanel accessible action names", () => {
  it("renders unique Focus/View names for repeated shared_availability_event titles", () => {
    renderPanel([
      makeCard({
        id: "shared-a",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "11 devices went offline during a shared availability event lasting about 4 minutes.",
        latest_supporting_evidence_at: "2026-07-20T10:32:00Z",
        supporting_evidence: ["Window A"],
      }),
      makeCard({
        id: "shared-b",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "6 devices went offline during a shared availability event lasting about 2 minutes.",
        latest_supporting_evidence_at: "2026-07-19T08:00:00Z",
        supporting_evidence: ["Window B"],
      }),
    ]);

    expect(
      screen.getByRole("button", {
        name: /^Focus graph: Several devices went offline around the same time — 11 devices/i,
      }),
    ).toHaveTextContent("Focus graph");
    expect(
      screen.getByRole("button", {
        name: /^Focus graph: Several devices went offline around the same time — 6 devices/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /^View details: Several devices went offline around the same time — 11 devices/i,
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
        supporting_evidence: ["Hall support"],
      }),
      makeCard({
        id: "issue-b",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "3 devices needing attention have recent evidence near the same observed router neighbourhood (Garage Router).",
        supporting_evidence: ["Garage support"],
      }),
    ]);

    expect(screen.getByRole("button", { name: /Focus graph: .*Hall Router/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Focus graph: .*Garage Router/i }),
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
        supporting_evidence: ["Passive support"],
      }),
      makeCard({
        id: "passive-b",
        type: "passive_instability_group",
        action_group: "watch_only",
        priority: "Lower priority",
        title: "Devices repeatedly went offline around the same time",
        summary: "5 devices showed repeated related offline timing in passive observations.",
        latest_supporting_evidence_at: "2026-07-19T12:00:00Z",
        supporting_evidence: ["Passive support"],
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
          latest_supporting_evidence_at: null,
          supporting_evidence: ["Hall area"],
        }),
        makeCard({
          id: "router-b",
          type: "router_neighbourhood_review",
          action_group: "review_observed_router_area",
          primary_neighbourhood_ieee: "0xr2",
          title: "Review observed router area: Garage Router",
          summary: "Evidence concentrates around Garage Router.",
          latest_supporting_evidence_at: null,
          supporting_evidence: ["Garage area"],
        }),
      ],
      { canOpenPrimaryDevice: true },
    );

    expect(
      screen.getByRole("button", {
        name: /Focus router area: Review observed router area: Hall Router/i,
      }),
    ).toHaveTextContent("Focus router area");
    expect(
      screen.getByRole("button", {
        name: /Open router details: Review observed router area: Hall Router/i,
      }),
    ).toHaveTextContent("Open router details");
    expect(
      screen.getByRole("button", {
        name: /Focus router area: Review observed router area: Garage Router/i,
      }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /Review observed router area — Review observed router area/i,
    );
  });

  it("keeps completely identical cards operable with ordinal accessible names", async () => {
    const user = userEvent.setup();
    const onFocus = vi.fn();
    const cards = [
      makeCard({
        id: "identical-a",
        title: "Identical investigation",
        summary: "Same summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
      makeCard({
        id: "identical-b",
        title: "Identical investigation",
        summary: "Same summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
    ];
    renderPanel(cards, { onFocus });

    const focus1 = screen.getByRole("button", {
      name: /Focus graph: Identical investigation .* — item 1 of 2$/i,
    });
    const focus2 = screen.getByRole("button", {
      name: /Focus graph: Identical investigation .* — item 2 of 2$/i,
    });
    expect(focus1).toHaveTextContent("Focus graph");
    expect(focus2).toHaveTextContent("Focus graph");
    expect(screen.getAllByText("Identical investigation")).toHaveLength(2);

    await user.click(focus2);
    expect(onFocus).toHaveBeenCalledTimes(1);
    expect(onFocus.mock.calls[0]?.[0]).toMatchObject({ id: "identical-b" });

    const details1 = screen.getByRole("button", {
      name: /View details: Identical investigation .* — item 1 of 2$/i,
    });
    const details2 = screen.getByRole("button", {
      name: /View details: Identical investigation .* — item 2 of 2$/i,
    });
    await user.click(details1);
    expect(details1).toHaveAttribute("aria-expanded", "true");
    expect(details2).toHaveAttribute("aria-expanded", "false");

    expect(focus1.getAttribute("aria-label")).not.toMatch(/\b0x[0-9a-f]+\b/i);
    expect(focus1.getAttribute("aria-label")).not.toMatch(/identical-[ab]/i);
  });

  it("keeps full-list ordinals stable across Show more", async () => {
    const user = userEvent.setup();
    expect(INVESTIGATION_CARDS_INITIALLY_VISIBLE).toBe(3);

    const cards = [
      makeCard({
        id: "unique-1",
        title: "Unique one",
        summary: "A",
        latest_supporting_evidence_at: null,
        supporting_evidence: [],
      }),
      makeCard({
        id: "unique-2",
        title: "Unique two",
        summary: "B",
        latest_supporting_evidence_at: null,
        supporting_evidence: [],
      }),
      makeCard({
        id: "dup-1",
        title: "Duplicate investigation",
        summary: "Same",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
      makeCard({
        id: "dup-2",
        title: "Duplicate investigation",
        summary: "Same",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
    ];
    renderPanel(cards);

    const panel = screen.getByRole("region", { name: /where to look first/i });
    expect(within(panel).getAllByTestId("investigation-card")).toHaveLength(3);

    const beforeShowMore = screen.getByRole("button", {
      name: /Focus graph: Duplicate investigation .* — item 1 of 2$/i,
    });
    const beforeLabel = beforeShowMore.getAttribute("aria-label");

    await user.click(within(panel).getByRole("button", { name: /show more/i }));
    expect(within(panel).getAllByTestId("investigation-card")).toHaveLength(4);

    const afterShowMore = screen.getByRole("button", {
      name: /Focus graph: Duplicate investigation .* — item 1 of 2$/i,
    });
    expect(afterShowMore.getAttribute("aria-label")).toBe(beforeLabel);
    expect(
      screen.getByRole("button", {
        name: /Focus graph: Duplicate investigation .* — item 2 of 2$/i,
      }),
    ).toBeInTheDocument();
  });

  it("keeps a focused fourth card visible after Show fewer and restores the initial slice on clear", async () => {
    const user = userEvent.setup();
    render(<StatefulInvestigationPanel investigations={makeRankedCards(5)} />);
    const panel = screen.getByRole("region", { name: /where to look first/i });

    expect(visibleCardIds(panel)).toEqual(["ranked-1", "ranked-2", "ranked-3"]);
    expect(within(panel).getByRole("button", { name: "Show more (2)" })).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Show more (2)" }));
    const fourthCard = cardWithId(panel, "ranked-4");
    await user.click(within(fourthCard).getByRole("button", { name: /^Focus graph:/i }));
    await user.click(within(panel).getByRole("button", { name: "Show fewer" }));

    expect(visibleCardIds(panel)).toEqual([
      "ranked-1",
      "ranked-2",
      "ranked-3",
      "ranked-4",
    ]);
    expect(
      within(panel)
        .getAllByTestId("investigation-card")
        .filter((card) => card.dataset.investigationId === "ranked-4"),
    ).toHaveLength(1);
    const collapsedActiveCard = cardWithId(panel, "ranked-4");
    expect(collapsedActiveCard).toHaveClass("border-zl-accent");
    expect(
      within(collapsedActiveCard).getByRole("button", { name: /^Clear focus:/i }),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Show more (1)" })).toBeInTheDocument();

    await user.click(
      within(collapsedActiveCard).getByRole("button", { name: /^Clear focus:/i }),
    );
    expect(visibleCardIds(panel)).toEqual(["ranked-1", "ranked-2", "ranked-3"]);
    expect(within(panel).queryByText("Ranked investigation 4")).not.toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Show more (2)" })).toBeInTheDocument();
  });

  it("does not offer a misleading toggle when the active fourth card leaves nothing hidden", () => {
    render(
      <StatefulInvestigationPanel
        investigations={makeRankedCards(4)}
        initialActiveInvestigationId="ranked-4"
      />,
    );
    const panel = screen.getByRole("region", { name: /where to look first/i });

    expect(visibleCardIds(panel)).toEqual([
      "ranked-1",
      "ranked-2",
      "ranked-3",
      "ranked-4",
    ]);
    expect(
      within(panel)
        .getAllByTestId("investigation-card")
        .filter((card) => card.dataset.investigationId === "ranked-4"),
    ).toHaveLength(1);
    expect(
      within(cardWithId(panel, "ranked-4")).getByRole("button", {
        name: /^Clear focus:/i,
      }),
    ).toBeInTheDocument();
    expect(
      within(panel).queryByRole("button", { name: /show (more|fewer)/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps refreshed active content visible when backend order moves it below the first three", async () => {
    const user = userEvent.setup();
    const initialCards = makeRankedCards(5);
    const view = render(<StatefulInvestigationPanel investigations={initialCards} />);
    const panel = screen.getByRole("region", { name: /where to look first/i });

    await user.click(
      within(cardWithId(panel, "ranked-1")).getByRole("button", { name: /^Focus graph:/i }),
    );

    const refreshedActive = makeCard({
      id: "ranked-1",
      title: "Refreshed active investigation",
      summary: "Current refreshed summary",
      supporting_evidence: ["Current refreshed evidence"],
    });
    view.rerender(
      <StatefulInvestigationPanel
        investigations={[
          initialCards[1]!,
          initialCards[2]!,
          initialCards[3]!,
          initialCards[4]!,
          refreshedActive,
        ]}
      />,
    );

    expect(visibleCardIds(panel)).toEqual([
      "ranked-2",
      "ranked-3",
      "ranked-4",
      "ranked-1",
    ]);
    expect(within(panel).queryByText("Ranked investigation 1")).not.toBeInTheDocument();
    expect(within(panel).getByText("Refreshed active investigation")).toBeInTheDocument();
    expect(within(panel).getByText("Current refreshed summary")).toBeInTheDocument();
    const activeCard = cardWithId(panel, "ranked-1");
    expect(activeCard).toHaveClass("border-zl-accent");
    expect(
      within(activeCard).getByRole("button", { name: /^Clear focus:/i }),
    ).toBeInTheDocument();
    expect(
      within(panel)
        .getAllByTestId("investigation-card")
        .filter((card) => card.dataset.investigationId === "ranked-1"),
    ).toHaveLength(1);
    expect(within(panel).getByRole("button", { name: "Show more (1)" })).toBeInTheDocument();
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
          supporting_evidence: ["Window A"],
        }),
        makeCard({
          id: "shared-b",
          type: "shared_availability_event",
          action_group: "investigate_shared_event",
          title: "Several devices went offline around the same time",
          summary:
            "6 devices went offline during a shared availability event lasting about 2 minutes.",
          latest_supporting_evidence_at: "2026-07-19T08:00:00Z",
          supporting_evidence: ["Window B"],
        }),
      ],
      { activeInvestigationId: "shared-b" },
    );

    expect(
      screen.getByRole("button", {
        name: /^Clear focus: Several devices went offline around the same time — 6 devices/i,
      }),
    ).toHaveTextContent("Clear focus");
  });
});
