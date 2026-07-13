/**
 * Overview ViewModel for investigation priorities (Phase 5A-2).
 */

import type { InvestigationPrioritySummary } from "@zigbeelens/shared";
import { buildInvestigationIdentityViewModel } from "@/viewModels/topology/investigationIdentity";
import type { DecisionPillTone } from "@/viewModels/types";

export const INVESTIGATION_PRIORITY_SECTION_TITLE = "What needs attention now";

export const INVESTIGATION_PRIORITY_EMPTY_COPY =
  "No current investigation priorities from stored evidence.";

export const INVESTIGATION_PRIORITY_MESH_LINK_LABEL = "Investigate in Mesh →";

export interface InvestigationPriorityViewModel {
  id: string;
  priorityLabel: string;
  priorityTone: DecisionPillTone;
  actionLabel: string;
  actionLead: string;
  title: string;
  summary: string;
  networkLabel: string;
  meshHref: string;
  meshLinkLabel: string;
}

export function buildInvestigationPriorityViewModel(
  priority: InvestigationPrioritySummary,
  networkName?: string | null,
): InvestigationPriorityViewModel {
  const identity = buildInvestigationIdentityViewModel({
    priority: priority.priority,
    actionGroup: priority.action_group,
  });
  const networkLabel = networkName?.trim() || "Network";

  return {
    id: priority.id,
    priorityLabel: identity.priorityLabel,
    priorityTone: identity.priorityTone,
    actionLabel: identity.actionLabel,
    actionLead: identity.actionLead,
    title: priority.title,
    summary: priority.summary,
    networkLabel,
    meshHref: `/topology/${priority.network_id}`,
    meshLinkLabel: INVESTIGATION_PRIORITY_MESH_LINK_LABEL,
  };
}
