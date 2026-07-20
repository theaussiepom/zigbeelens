import { describe, expect, it } from "vitest";
import type { InvestigationCard } from "@/types/topology";
import {
  assignAccessibleContextKeys,
  buildAccessibleContextKey,
  buildInvestigationCardViewModel,
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
    expect(vm.whyItMatters).toMatch(/does not prove a failure/i);
    expect(vm.focusLabel).toBe("Focus graph");
    expect(vm.openRouterDetailsLabel).toBeNull();
  });

  it("uses router-area focus labels from the card title without duplicating action group wording", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr1",
        title: "Review observed router area: Hall Router",
        summary: "Several issue devices are represented around Hall Router in stored evidence.",
      }),
    );
    expect(vm.isRouterArea).toBe(true);
    expect(vm.focusLabel).toBe("Focus router area");
    expect(vm.openRouterDetailsLabel).toBe("Open router details");
    expect(vm.primaryNeighbourhoodIeee).toBe("0xr1");
    expect(vm.focusAriaLabel).toBe(
      "Focus router area: Review observed router area: Hall Router",
    );
    expect(vm.openPrimaryDeviceAriaLabel).toBe(
      "Open router details: Review observed router area: Hall Router",
    );
    expect(vm.clearFocusAriaLabel).toBe(
      "Clear focus: Review observed router area: Hall Router",
    );
    expect(vm.focusAriaLabel).not.toMatch(
      /Review observed router area — Review observed router area/i,
    );
  });

  it("gives each investigation action a distinguishable accessible name", () => {
    const cards = [
      makeCard({
        id: "ordinary-a",
        title: "Several recent missing links involve Kitchen Sensor",
        primary_device_ieee: "0xe1",
      }),
      makeCard({
        id: "ordinary-b",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        primary_device_ieee: "0xe2",
      }),
      makeCard({
        id: "router-a",
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr1",
        title: "Review observed router area: Hall Router",
      }),
      makeCard({
        id: "router-b",
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr2",
        title: "Review observed router area: Garage Router",
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    const names = vms.flatMap(actionNames);

    expect(vms.filter((vm) => !vm.isRouterArea)).toHaveLength(2);
    expect(vms.filter((vm) => vm.isRouterArea)).toHaveLength(2);
    expect(new Set(names).size).toBe(names.length);
    for (const vm of vms) {
      expect(vm.focusAriaLabel).toContain(vm.contextTitle);
      expect(vm.focusAriaLabel).not.toMatch(/\b0x[0-9a-f]+\b/i);
      expect(vm.clearFocusAriaLabel).toMatch(/^Clear focus:/);
      expect(vm.clearFocusAriaLabel).not.toMatch(/Clear focus for Focus/i);
      expect(vm.detailsAriaLabel).toMatch(/^View details:/);
    }
    expect(vms[0]?.focusAriaLabel).toBe(
      "Focus graph: Several recent missing links involve Kitchen Sensor",
    );
    expect(vms[2]?.focusAriaLabel).toBe(
      "Focus router area: Review observed router area: Hall Router",
    );
  });

  it("distinguishes repeated shared_availability_event titles with summary and evidence time", () => {
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
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toBe(
      "Focus graph: Several devices went offline around the same time — " +
        "11 devices went offline during a shared availability event lasting about 4 minutes.",
    );
    expect(vms[1]?.focusAriaLabel).toContain("6 devices went offline");
    expect(vms[0]?.focusAriaLabel).not.toBe(vms[1]?.focusAriaLabel);
    expect(vms[0]?.detailsAriaLabel).not.toBe(vms[1]?.detailsAriaLabel);
    expect(vms[0]?.clearFocusAriaLabel).not.toBe(vms[1]?.clearFocusAriaLabel);
    expect(vms[0]?.focusAriaLabel).not.toMatch(/\b0x[0-9a-f]+\b/i);
  });

  it("includes latest evidence when shared-event summaries alone are not enough", () => {
    const cards = [
      makeCard({
        id: "shared-same-summary-a",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "11 devices went offline during a shared availability event lasting about 4 minutes.",
        latest_supporting_evidence_at: "2026-07-20T10:32:00Z",
      }),
      makeCard({
        id: "shared-same-summary-b",
        type: "shared_availability_event",
        action_group: "investigate_shared_event",
        title: "Several devices went offline around the same time",
        summary:
          "11 devices went offline during a shared availability event lasting about 4 minutes.",
        latest_supporting_evidence_at: "2026-07-18T09:00:00Z",
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toBe(
      "Focus graph: Several devices went offline around the same time — " +
        "11 devices went offline during a shared availability event lasting about 4 minutes. — " +
        "latest evidence 2026-07-20T10:32:00Z",
    );
    expect(vms[1]?.focusAriaLabel).toContain("latest evidence 2026-07-18T09:00:00Z");
    expect(vms[0]?.focusAriaLabel).not.toBe(vms[1]?.focusAriaLabel);
  });

  it("distinguishes repeated issue_cluster titles via neighbourhood summaries", () => {
    const cards = [
      makeCard({
        id: "issue-a",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "4 devices needing attention have recent evidence near the same observed router neighbourhood (Hall Router).",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
      }),
      makeCard({
        id: "issue-b",
        type: "issue_cluster",
        action_group: "investigate_shared_event",
        title: "Devices needing attention share an observed neighbourhood",
        summary:
          "3 devices needing attention have recent evidence near the same observed router neighbourhood (Garage Router).",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
      }),
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("Hall Router");
    expect(vms[1]?.focusAriaLabel).toContain("Garage Router");
    expect(vms[0]?.focusAriaLabel).not.toBe(vms[1]?.focusAriaLabel);
    expect(vms[0]?.detailsAriaLabel).not.toBe(vms[1]?.detailsAriaLabel);
  });

  it("distinguishes repeated passive_instability_group titles via latest evidence time", () => {
    const cards = [
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
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toContain("latest evidence 2026-07-20T12:00:00Z");
    expect(vms[1]?.focusAriaLabel).toContain("latest evidence 2026-07-19T12:00:00Z");
    expect(vms[0]?.focusAriaLabel).not.toBe(vms[1]?.focusAriaLabel);
    expect(vms[0]?.clearFocusAriaLabel).not.toBe(vms[1]?.clearFocusAriaLabel);
  });

  it("keeps router-area action names distinct without duplicated action-group wording", () => {
    const cards = [
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
    ];
    const vms = buildInvestigationPanelViewModel(cards).cards;
    expect(vms[0]?.focusAriaLabel).toBe(
      "Focus router area: Review observed router area: Hall Router",
    );
    expect(vms[1]?.focusAriaLabel).toBe(
      "Focus router area: Review observed router area: Garage Router",
    );
    expect(vms[0]?.openPrimaryDeviceAriaLabel).toBe(
      "Open router details: Review observed router area: Hall Router",
    );
    expect(vms[1]?.openPrimaryDeviceAriaLabel).toBe(
      "Open router details: Review observed router area: Garage Router",
    );
    for (const vm of vms) {
      expect(vm.focusAriaLabel).not.toMatch(
        /Review observed router area — Review observed router area/i,
      );
      expect(vm.clearFocusAriaLabel).not.toMatch(
        /Review observed router area — Review observed router area/i,
      );
      expect(vm.detailsAriaLabel).not.toMatch(
        /Review observed router area — Review observed router area/i,
      );
    }
    expect(new Set(vms.flatMap(actionNames)).size).toBe(vms.flatMap(actionNames).length);
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

  it("refuses opaque id / IEEE disambiguation when human facts still collide", () => {
    const cards = [
      makeCard({
        id: "opaque-a",
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["0xaaaa"],
      }),
      makeCard({
        id: "opaque-b",
        title: "Identical title",
        summary: "Identical summary",
        latest_supporting_evidence_at: "2026-07-20T10:00:00Z",
        supporting_evidence: ["0xbbbb"],
      }),
    ];
    expect(() => assignAccessibleContextKeys(cards)).toThrow(/refusing to expose/i);
    expect(buildAccessibleContextKey(cards[0]!, 3)).toBe(
      "Identical title — Identical summary — latest evidence 2026-07-20T10:00:00Z",
    );
  });
});
