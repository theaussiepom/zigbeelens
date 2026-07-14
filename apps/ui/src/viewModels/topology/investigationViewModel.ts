/**
 * Investigation panel ViewModel — maps investigation card DTOs to action-led
 * display models. InvestigationPanel renders this; it does not decide action
 * grouping or diagnostic copy.
 */

import type { InvestigationCard } from "@/types/topology";
import {
  INVESTIGATION_EMPTY_COPY,
  INVESTIGATION_PANEL_SUBTITLE,
  INVESTIGATION_PANEL_TITLE,
  INVESTIGATION_SECTION_CHECKS,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_SUPPORTING,
  type InvestigationActionGroup,
} from "@/lib/meshGraphCopy";
import type { DecisionPillTone } from "@/viewModels/types";
import { buildInvestigationIdentityViewModel } from "./investigationIdentity";

export interface InvestigationCardViewModel {
  id: string;
  priorityLabel: string;
  priorityTone: DecisionPillTone;
  actionGroupLabel: string;
  actionLead: string;
  contextTitle: string;
  contextSummary: string;
  whyItMatters: string;
  supportingEvidence: string[];
  limitations: string[];
  suggestedChecks: string[];
  focusLabel: string;
}

export interface InvestigationPanelViewModel {
  title: string;
  subtitle: string;
  emptyCopy: string;
  cards: InvestigationCardViewModel[];
}

function actionGroupForCard(card: InvestigationCard): InvestigationActionGroup {
  if (card.action_group) {
    return card.action_group;
  }
  switch (card.type) {
    case "diagnostics_limited_group":
      return "improve_data_coverage";
    case "router_neighbourhood_review":
      return "review_observed_router_area";
    case "model_pattern_review":
      return "review_model_pattern";
    case "recent_missing_cluster":
      return "check_power_reporting";
    case "shared_availability_event":
      return "investigate_shared_event";
    case "issue_cluster":
      return "investigate_shared_event";
    case "passive_instability_group":
      return card.priority === "Lower priority"
        ? "watch_only"
        : "investigate_shared_event";
  }
}

export function buildInvestigationCardViewModel(
  card: InvestigationCard,
): InvestigationCardViewModel {
  const actionGroup = actionGroupForCard(card);
  const identity = buildInvestigationIdentityViewModel({
    priority: card.priority,
    actionGroup,
  });
  return {
    id: card.id,
    priorityLabel: identity.priorityLabel,
    priorityTone: identity.priorityTone,
    actionGroupLabel: identity.actionLabel,
    actionLead: identity.actionLead,
    contextTitle: card.title,
    contextSummary: card.summary,
    whyItMatters: card.why_it_matters,
    supportingEvidence: card.supporting_evidence,
    limitations: card.limitations,
    suggestedChecks: card.suggested_next_steps,
    focusLabel: identity.actionLead,
  };
}

export function buildInvestigationPanelViewModel(
  investigations: InvestigationCard[],
): InvestigationPanelViewModel {
  return {
    title: INVESTIGATION_PANEL_TITLE,
    subtitle: INVESTIGATION_PANEL_SUBTITLE,
    emptyCopy: INVESTIGATION_EMPTY_COPY,
    cards: investigations.map(buildInvestigationCardViewModel),
  };
}

export {
  INVESTIGATION_SECTION_CHECKS,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_SUPPORTING,
};
