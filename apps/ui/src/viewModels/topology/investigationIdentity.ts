/**
 * Shared investigation presentation helpers.
 *
 * Priority tone and action-group labels/leads are owned here so Mesh and
 * Overview consume the same interpretation without duplicating copy maps.
 */

import {
  INVESTIGATION_ACTION_GROUP_LABELS,
  INVESTIGATION_ACTION_LEADS,
  type InvestigationActionGroup,
} from "@/lib/meshGraphCopy";
import type { DecisionPillTone } from "@/viewModels/types";

const KNOWN_ACTION_GROUPS = new Set<string>(
  Object.keys(INVESTIGATION_ACTION_GROUP_LABELS),
);

const UNKNOWN_ACTION_GROUP_LABEL = "Review investigation";
const UNKNOWN_ACTION_LEAD =
  "Review the related Mesh evidence before changing the network.";

export function investigationPriorityLabel(priority: string): string {
  switch (priority) {
    case "Review first":
    case "Worth checking":
    case "Lower priority":
      return priority;
    default:
      return "Priority unknown";
  }
}

export function investigationPriorityTone(priority: string): DecisionPillTone {
  switch (priority) {
    case "Review first":
      return "watch";
    case "Worth checking":
      return "action";
    case "Lower priority":
      return "muted";
    default:
      return "muted";
  }
}

function resolveActionGroup(actionGroup: string): InvestigationActionGroup | null {
  if (KNOWN_ACTION_GROUPS.has(actionGroup)) {
    return actionGroup as InvestigationActionGroup;
  }
  return null;
}

export function investigationActionGroupLabel(actionGroup: string): string {
  const resolved = resolveActionGroup(actionGroup);
  if (resolved) {
    return INVESTIGATION_ACTION_GROUP_LABELS[resolved];
  }
  return UNKNOWN_ACTION_GROUP_LABEL;
}

export function investigationActionLead(actionGroup: string): string {
  const resolved = resolveActionGroup(actionGroup);
  if (resolved) {
    return INVESTIGATION_ACTION_LEADS[resolved];
  }
  return UNKNOWN_ACTION_LEAD;
}

export interface InvestigationIdentityViewModel {
  priorityLabel: string;
  priorityTone: DecisionPillTone;
  actionLabel: string;
  actionLead: string;
}

export function buildInvestigationIdentityViewModel(input: {
  priority: string;
  actionGroup: string;
}): InvestigationIdentityViewModel {
  return {
    priorityLabel: investigationPriorityLabel(input.priority),
    priorityTone: investigationPriorityTone(input.priority),
    actionLabel: investigationActionGroupLabel(input.actionGroup),
    actionLead: investigationActionLead(input.actionGroup),
  };
}
