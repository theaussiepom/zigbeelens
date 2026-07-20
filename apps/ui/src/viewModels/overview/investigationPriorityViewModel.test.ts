import { describe, expect, it } from "vitest";
import type { InvestigationPrioritySummary } from "@zigbeelens/shared";
import {
  INVESTIGATION_PRIORITY_MESH_LINK_LABEL,
  buildInvestigationPriorityViewModel,
} from "./investigationPriorityViewModel";
import {
  investigationActionGroupLabel,
  investigationActionLead,
  investigationPriorityTone,
} from "@/viewModels/topology/investigationIdentity";

function makePriority(
  overrides: Partial<InvestigationPrioritySummary> = {},
): InvestigationPrioritySummary {
  return {
    id: "priority-1",
    network_id: "home",
    card_type: "shared_availability_event",
    priority: "Review first",
    score: 12,
    action_group: "investigate_shared_event",
    title: "Several devices went offline around the same time",
    summary: "11 devices went offline during a shared availability event lasting about 4 minutes.",
    device_ieees: ["0xd00"],
    latest_supporting_evidence_at: "2026-07-06T08:04:00+00:00",
    ...overrides,
  };
}

describe("investigationPriorityViewModel", () => {
  it("preserves priority label and shared priority tone", () => {
    const vm = buildInvestigationPriorityViewModel(makePriority());
    expect(vm.priorityLabel).toBe("Review first");
    expect(vm.priorityTone).toBe(investigationPriorityTone("Review first"));
    expect(vm.priorityTone).toBe("watch");
  });

  it("uses shared action-group label and lead without exposing the raw code", () => {
    const vm = buildInvestigationPriorityViewModel(makePriority());
    expect(vm.actionLabel).toBe(investigationActionGroupLabel("investigate_shared_event"));
    expect(vm.actionLead).toBe(investigationActionLead("investigate_shared_event"));
    expect(vm.actionLabel).toBe("Investigate shared event");
    expect(vm.actionLead).toMatch(/shared power, placement, or timing pattern/i);
    expect(JSON.stringify(vm)).not.toContain("investigate_shared_event");
  });

  it("maps known network IDs to network names", () => {
    const vm = buildInvestigationPriorityViewModel(makePriority(), "Home");
    expect(vm.networkLabel).toBe("Home");
  });

  it("uses a safe Network fallback for unknown networks", () => {
    const vm = buildInvestigationPriorityViewModel(
      makePriority({ network_id: "missing" }),
      null,
    );
    expect(vm.networkLabel).toBe("Network");
    expect(vm.networkLabel).not.toBe("missing");
  });

  it("links to the Mesh page for the network", () => {
    const vm = buildInvestigationPriorityViewModel(makePriority({ network_id: "office" }));
    expect(vm.meshHref).toBe("/investigate/office");
    expect(vm.meshLinkLabel).toBe(INVESTIGATION_PRIORITY_MESH_LINK_LABEL);
  });

  it("does not expose raw score in user-facing ViewModel labels", () => {
    const vm = buildInvestigationPriorityViewModel(makePriority({ score: 99 }));
    const labels = [
      vm.priorityLabel,
      vm.actionLabel,
      vm.actionLead,
      vm.title,
      vm.summary,
      vm.networkLabel,
      vm.meshLinkLabel,
    ].join(" ");
    expect(labels).not.toMatch(/\b99\b/);
    expect(labels.toLowerCase()).not.toContain("score");
    expect("score" in vm).toBe(false);
  });

  it("fails safely for unknown action groups without showing the raw code", () => {
    const vm = buildInvestigationPriorityViewModel(
      makePriority({ action_group: "future_unknown_group" }),
    );
    expect(vm.actionLabel).toBe("Review investigation");
    expect(vm.actionLead).toMatch(/related Mesh evidence/i);
    expect(JSON.stringify(vm)).not.toContain("future_unknown_group");
  });

  it("hides unknown priority codes as Priority unknown without exposing the raw value", () => {
    const vm = buildInvestigationPriorityViewModel(
      makePriority({ priority: "review_soon_v2" }),
    );
    expect(vm.priorityLabel).toBe("Priority unknown");
    expect(vm.priorityTone).toBe("muted");
    expect(JSON.stringify(vm)).not.toContain("review_soon_v2");
  });
});
