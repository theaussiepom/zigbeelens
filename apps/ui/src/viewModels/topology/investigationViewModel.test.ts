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
    expect(vm.focusLabel).toBe(vm.actionLead);
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
