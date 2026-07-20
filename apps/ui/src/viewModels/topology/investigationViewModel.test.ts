import { describe, expect, it } from "vitest";
import type { InvestigationCard } from "@/types/topology";
import { buildInvestigationCardViewModel, buildInvestigationPanelViewModel } from "./investigationViewModel";

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

  it("uses router-area focus and open-details labels for observed router areas", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr1",
        title: "Observed router area around Hall Router",
      }),
    );
    expect(vm.isRouterArea).toBe(true);
    expect(vm.focusLabel).toBe("Focus router area");
    expect(vm.openRouterDetailsLabel).toBe("Open router details");
    expect(vm.primaryNeighbourhoodIeee).toBe("0xr1");
    expect(vm.focusAriaLabel).toBe(
      "Focus router area: Review observed router area — Observed router area around Hall Router",
    );
    expect(vm.openPrimaryDeviceAriaLabel).toBe(
      "Open router details: Review observed router area — Observed router area around Hall Router",
    );
    expect(vm.clearFocusAriaLabel).toBe(
      "Clear focus: Review observed router area — Observed router area around Hall Router",
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
        title: "Observed router area around Hall Router",
      }),
      makeCard({
        id: "router-b",
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: "0xr2",
        title: "Observed router area around Garage Router",
      }),
    ];
    const vms = cards.map(buildInvestigationCardViewModel);
    const actionNames = vms.flatMap((vm) =>
      [
        vm.focusAriaLabel,
        vm.clearFocusAriaLabel,
        vm.detailsAriaLabel,
        vm.hideDetailsAriaLabel,
        vm.openPrimaryDeviceAriaLabel,
      ].filter((name): name is string => Boolean(name)),
    );

    expect(vms.filter((vm) => !vm.isRouterArea)).toHaveLength(2);
    expect(vms.filter((vm) => vm.isRouterArea)).toHaveLength(2);
    expect(new Set(actionNames).size).toBe(actionNames.length);
    for (const vm of vms) {
      expect(vm.focusAriaLabel).toContain(vm.contextTitle);
      expect(vm.focusAriaLabel).not.toMatch(/0x[0-9a-f]+/i);
      expect(vm.clearFocusAriaLabel).toMatch(/^Clear focus:/);
      expect(vm.clearFocusAriaLabel).not.toMatch(/Clear focus for Focus/i);
      expect(vm.detailsAriaLabel).toMatch(/^View details:/);
    }
    expect(vms[0]?.focusAriaLabel).toBe(
      "Focus graph: Several recent missing links involve Kitchen Sensor",
    );
    expect(vms[2]?.focusAriaLabel).toBe(
      "Focus router area: Review observed router area — Observed router area around Hall Router",
    );
    expect(vms[2]?.openPrimaryDeviceAriaLabel).toBe(
      "Open router details: Review observed router area — Observed router area around Hall Router",
    );
  });

  it("omits open-router-details when the card has no neighbourhood IEEE", () => {
    const vm = buildInvestigationCardViewModel(
      makeCard({
        type: "router_neighbourhood_review",
        action_group: "review_observed_router_area",
        primary_neighbourhood_ieee: null,
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
