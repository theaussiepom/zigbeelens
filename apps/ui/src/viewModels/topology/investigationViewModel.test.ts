import { describe, expect, it } from "vitest";
import type { InvestigationCard } from "@/types/topology";
import {
  assignAccessibleContextKeys,
  buildInvestigationCardViewModel,
  buildInvestigationHumanContext,
  buildInvestigationPanelViewModel,
} from "./investigationViewModel";

function makeCard(overrides: Partial<InvestigationCard> = {}): InvestigationCard {
  return {
    id: "recent-missing-0xe1",
    type: "recent_missing_cluster",
    priority: "Worth checking",
    score: 8,
    title: "Several recent missing links involve Live Lamp",
    summary:
      "Live Lamp has 3 links that were seen recently but are not present in the latest usable snapshot.",
    why_it_matters:
      "This does not prove a failure, but it may be worth checking if the device has moved, lost power, or has weak mesh conditions.",
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

function actionNames(vm: ReturnType<typeof buildInvestigationCardViewModel>): string[] {
  return [
    vm.focusAriaLabel,
    vm.clearFocusAriaLabel,
    vm.detailsAriaLabel,
    vm.hideDetailsAriaLabel,
    vm.openPrimaryDeviceAriaLabel,
  ].filter((name): name is string => Boolean(name));
}

describe("investigationViewModel", () => {
  it("leads with action group copy for check power/reporting", () => {
    const vm = buildInvestigationCardViewModel(makeCard());
    expect(vm.actionGroupLabel).toBe("Check power/reporting");
    expect(vm.actionLead).toMatch(/power and are reporting/i);
    expect(vm.contextTitle).toBe("Several recent missing links involve Live Lamp");
    expect(vm.focusLabel).toBe("Focus graph");
    expect(vm.openRouterDetailsLabel).toBeNull();
  });

  it("builds human context from title, summary, evidence time, and supporting line", () => {
    const context = buildInvestigationHumanContext(
      makeCard({
        title: "Several devices went offline around the same time",
        summary:
          "11 devices went offline during a shared availability event lasting about 4 minutes.",
        latest_supporting_evidence_at: "2026-07-20T10:32:00Z",
        supporting_evidence: ["Shared offline window lasted about 4 minutes."],
      }),
    );
    expect(context).toBe(
      "Several devices went offline around the same time — " +
        "11 devices went offline during a shared availability event lasting about 4 minutes. — " +
        "latest evidence 2026-07-20T10:32:00Z — " +
        "Shared offline window lasted about 4 minutes.",
    );
  });

  it("uses router-area titles without duplicating action-group wording", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr1",
        title: "Review observed router area: Hall Router",
        summary: "Several issue devices are represented around Hall Router in stored evidence.",
        latest_supporting_evidence_at: null,
        supporting_evidence: ["Evidence concentrates around Hall Router."],
      }),
    );
    expect(vm.focusAriaLabel).toContain(
      "Focus router area: Review observed router area: Hall Router",
    );
    expect(vm.focusAriaLabel).not.toMatch(
      /Review observed router area — Review observed router area/i,
    );
    expect(vm.openPrimaryDeviceAriaLabel).toContain(
      "Open router details: Review observed router area: Hall Router",
    );
  });

  it("keeps standalone card ViewModel construction total and unsuffixed", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Identical support"],
      }),
    );
    expect(vm.focusAriaLabel).toBe(
      "Focus graph: Identical title — Identical summary — " +
        "latest evidence 2026-07-20T10:00:00Z — Identical support",
    );
    expect(vm.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("suffixes completely identical sibling cards with item N of M", () => {
    const cards = [
      makeCard({
        id: "dup-a",
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Identical support"],
      }),
      makeCard({
        id: "dup-b",
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Identical support"],
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms).toHaveLength(2);
    expect(vms[0]?.focusAriaLabel).toMatch(/ — item 1 of 2$/);
    expect(vms[1]?.focusAriaLabel).toMatch(/ — item 2 of 2$/);
    expect(vms[0]?.clearFocusAriaLabel).toMatch(/ — item 1 of 2$/);
    expect(vms[1]?.detailsAriaLabel).toMatch(/ — item 2 of 2$/);
    expect(vms[0]?.contextTitle).toBe("Identical title");
    expect(vms[1]?.contextTitle).toBe("Identical title");
    expect(new Set(vms.flatMap(actionNames)).size).toBe(vms.flatMap(actionNames).length);
  });

  it("suffixes three identical cards as item 1/2/3 of 3", () => {
    const cards = [1, 2, 3].map((n) =>
      makeCard({
        id: `trip-${n}`,
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Identical support"],
      }),
    );
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms.map((vm) => vm.focusAriaLabel)).toEqual([
      expect.stringMatching(/ — item 1 of 3$/),
      expect.stringMatching(/ — item 2 of 3$/),
      expect.stringMatching(/ — item 3 of 3$/),
    ]);
  });

  it("does not add item 1 of 1 for a single card", () => {
    const vm = buildInvestigationPanelViewModel([makeCard()]).cards[0];
    expect(vm?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("distinguishes same title with different summaries without ordinals", () => {
    const cards = [
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
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("11 devices went offline");
    expect(vms[1]?.focusAriaLabel).toContain("6 devices went offline");
    expect(vms[0]?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
    expect(vms[1]?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("distinguishes same title/summary with different evidence times without ordinals", () => {
    const cards = [
      makeCard({
        id: "passive-a",
        type: "passive_instability_group",
        action_group: "watch_only",
        priority: "Lower priority",
        title: "Devices repeatedly went offline around the same time",
        summary: "5 devices showed repeated related offline timing in passive observations.",
        latest_supporting_evidence_at: "2026-07-20T12:00:00Z",
        supporting_evidence: ["Passive group support"],
      }),
      makeCard({
        id: "passive-b",
        type: "passive_instability_group",
        action_group: "watch_only",
        priority: "Lower priority",
        title: "Devices repeatedly went offline around the same time",
        summary: "5 devices showed repeated related offline timing in passive observations.",
        latest_supporting_evidence_at: "2026-07-19T12:00:00Z",
        supporting_evidence: ["Passive group support"],
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("latest evidence 2026-07-20T12:00:00Z");
    expect(vms[1]?.focusAriaLabel).toContain("latest evidence 2026-07-19T12:00:00Z");
    expect(vms[0]?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("distinguishes same title/summary/time with different supporting lines without ordinals", () => {
    const cards = [
      makeCard({
        id: "support-a",
        title: "Shared title",
        summary: "Shared summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Support line for kitchen"],
      }),
      makeCard({
        id: "support-b",
        title: "Shared title",
        summary: "Shared summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Support line for garage"],
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("Support line for kitchen");
    expect(vms[1]?.focusAriaLabel).toContain("Support line for garage");
    expect(vms[0]?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("keeps issue_cluster neighbourhood summaries distinguishable", () => {
    const cards = [
      makeCard({
        id: "issue-a",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "4 devices needing attention have recent evidence near the same observed router neighbourhood (Hall Router).",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Hall neighbourhood evidence"],
      }),
      makeCard({
        id: "issue-b",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "3 devices needing attention have recent evidence near the same observed router neighbourhood (Garage Router).",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Garage neighbourhood evidence"],
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("Hall Router");
    expect(vms[1]?.focusAriaLabel).toContain("Garage Router");
    expect(vms[0]?.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
  });

  it("keeps router-area action names distinct without ordinals when titles differ", () => {
    const cards = [
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
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("Hall Router");
    expect(vms[1]?.focusAriaLabel).toContain("Garage Router");
    expect(vms[0]?.openPrimaryDeviceAriaLabel).toContain("Hall Router");
    expect(vms[1]?.openPrimaryDeviceAriaLabel).toContain("Garage Router");
    for (const vm of vms) {
      expect(vm.focusAriaLabel).not.toMatch(
        /Review observed router area — Review observed router area/i,
      );
      expect(vm.focusAriaLabel).not.toMatch(/item \d+ of \d+/);
      expect(vm.focusAriaLabel).not.toMatch(/\b0x[0-9a-f]+\b/i);
    }
  });

  it("computes ordinals from the full list order before any visible slice", () => {
    const cards = [
      makeCard({
        id: "unique",
        title: "Unique card",
        summary: "Only one",
        latest_supporting_evidence_at: null,
        supporting_evidence: [],
      }),
      makeCard({
        id: "dup-1",
        title: "Duplicate card",
        summary: "Same",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
      makeCard({
        id: "dup-2",
        title: "Duplicate card",
        summary: "Same",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
      makeCard({
        id: "dup-3",
        title: "Duplicate card",
        summary: "Same",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["Same support"],
      }),
    ];
    const keys = assignAccessibleContextKeys(cards);
    expect(keys.get("unique")).not.toMatch(/item \d+ of \d+/);
    expect(keys.get("dup-1")).toMatch(/ — item 1 of 3$/);
    expect(keys.get("dup-2")).toMatch(/ — item 2 of 3$/);
    expect(keys.get("dup-3")).toMatch(/ — item 3 of 3$/);

    // Visible slice of first 3 still keeps full-list ordinals (item 1/2 of 3).
    const panel = buildInvestigationPanelViewModel(cards);
    const visible = panel.cards.slice(0, 3);
    expect(visible[1]?.focusAriaLabel).toMatch(/ — item 1 of 3$/);
    expect(visible[2]?.focusAriaLabel).toMatch(/ — item 2 of 3$/);
  });

  it("never throws for identical cards that only differ by id", () => {
    expect(() =>
      buildInvestigationPanelViewModel([
        makeCard({
          id: "a",
          title: "Same",
          summary: "Same",
          latest_supporting_evidence_at: "t",
          supporting_evidence: ["Same"],
        }),
        makeCard({
          id: "b",
          title: "Same",
          summary: "Same",
          latest_supporting_evidence_at: "t",
          supporting_evidence: ["Same"],
        }),
      ]),
    ).not.toThrow();
  });

  it("omits open-router-details when the card has no neighbourhood IEEE", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: null,
        title: "Review observed router area: Hall Router",
      }),
    );
    expect(vm.focusLabel).toBe("Focus router area");
    expect(vm.openRouterDetailsLabel).toBeNull();
  });

  it("maps each action group label", () => {
    const groups = [
      ["check_power_reporting", "Check power/reporting"],
      ["review_observed_router_area", "Review observed router area"],
      ["investigate_shared_event", "Investigate shared event"],
      ["improve_data_coverage", "Improve data coverage"],
      ["watch_only", "Watch only"],
    ] as const;

    for (const [action_group, label] of groups) {
      const vm = buildInvestigationCardViewModel(makeCard({ action_group }));
      expect(vm.actionGroupLabel).toBe(label);
      expect(vm.actionLead.length).toBeGreaterThan(10);
    }
  });

  it("falls back to investigate shared event for shared availability cards without action_group", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "shared_availability_event",
        title: "Several devices went offline around the same time",
        summary: "11 devices went offline during a shared availability event lasting about 4 minutes.",
        action_group: undefined as unknown as InvestigationCard["action_group"],
      }),
    );
    expect(vm.actionGroupLabel).toBe("Investigate shared event");
  });

  it("falls back to watch only for low-priority passive cards without action_group", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "passive_instability_group",
        priority: "Lower priority",
        action_group: undefined as unknown as InvestigationCard["action_group"],
      }),
    );
    expect(vm.actionGroupLabel).toBe("Watch only");
  });

  it("builds panel view model with stable shell copy", () => {
    const vm = buildInvestigationPanelViewModel([makeCard()]);
    expect(vm.title).toBe("Where to look first");
    expect(vm.cards).toHaveLength(1);
    expect(vm.emptyCopy).toMatch(/no investigation priorities/i);
  });
});
