/**
 * Investigation panel ViewModel — maps investigation card DTOs to action-led
 * display models. InvestigationPanel renders this; it does not decide action
 * grouping or diagnostic copy.
 */

import type { InvestigationCard } from "@/types/topology";
import {
  INVESTIGATION_EMPTY_COPY,
  INVESTIGATION_FOCUS_LABEL_DEFAULT,
  INVESTIGATION_FOCUS_LABEL_ROUTER_AREA,
  INVESTIGATION_OPEN_ROUTER_DETAILS_LABEL,
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
  /** IEEE for open-router-details; null when the card does not expose one. */
  primaryNeighbourhoodIeee: string | null;
  openRouterDetailsLabel: string | null;
  isRouterArea: boolean;
  /** Accessible name for Focus graph / Focus router area. */
  focusAriaLabel: string;
  /** Accessible name for Clear focus. */
  clearFocusAriaLabel: string;
  /** Accessible name for Open router details; null when the action is absent. */
  openPrimaryDeviceAriaLabel: string | null;
  /** Accessible name for View details. */
  detailsAriaLabel: string;
  /** Accessible name for Hide details. */
  hideDetailsAriaLabel: string;
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

function isBareIeee(value: string): boolean {
  return /^0x[0-9a-f]+$/i.test(value.trim());
}

/**
 * Base human context for accessible action names.
 * Includes title, then summary / latest evidence / supporting line when usable.
 * Does not resolve sibling collisions and never throws.
 */
export function buildInvestigationHumanContext(card: InvestigationCard): string {
  const title = card.title.trim();
  const parts = [title];

  const summary = card.summary.trim();
  if (summary && summary !== title) {
    parts.push(summary);
  }

  const evidenceAt = card.latest_supporting_evidence_at?.trim() ?? "";
  if (evidenceAt) {
    parts.push(`latest evidence ${evidenceAt}`);
  }

  for (const item of card.supporting_evidence) {
    const line = item.trim();
    if (!line || isBareIeee(line)) continue;
    if (line === title || line === summary) continue;
    parts.push(line);
    break;
  }

  return parts.join(" — ");
}

/**
 * List-level accessible contexts: human facts first, then duplicate-group
 * ordinals (`item N of M`) only when the full human context still collides.
 * Uses rendered/server order. Never throws; never exposes card IDs or IEEE.
 */
export function assignAccessibleContextKeys(
  cards: InvestigationCard[],
): Map<string, string> {
  const baseById = new Map(
    cards.map((card) => [card.id, buildInvestigationHumanContext(card)]),
  );

  const groups = new Map<string, string[]>();
  for (const card of cards) {
    const base = baseById.get(card.id) ?? card.title;
    const group = groups.get(base);
    if (group) group.push(card.id);
    else groups.set(base, [card.id]);
  }

  const assigned = new Map<string, string>();
  for (const card of cards) {
    const base = baseById.get(card.id) ?? card.title;
    const group = groups.get(base) ?? [card.id];
    if (group.length === 1) {
      assigned.set(card.id, base);
      continue;
    }
    const index = group.indexOf(card.id) + 1;
    assigned.set(card.id, `${base} — item ${index} of ${group.length}`);
  }
  return assigned;
}

function ariaLabelsForContext(
  focusLabel: string,
  openRouterDetailsLabel: string | null,
  contextKey: string,
): Pick<
  InvestigationCardViewModel,
  | "focusAriaLabel"
  | "clearFocusAriaLabel"
  | "openPrimaryDeviceAriaLabel"
  | "detailsAriaLabel"
  | "hideDetailsAriaLabel"
> {
  return {
    focusAriaLabel: `${focusLabel}: ${contextKey}`,
    clearFocusAriaLabel: `Clear focus: ${contextKey}`,
    openPrimaryDeviceAriaLabel: openRouterDetailsLabel
      ? `${openRouterDetailsLabel}: ${contextKey}`
      : null,
    detailsAriaLabel: `View details: ${contextKey}`,
    hideDetailsAriaLabel: `Hide details: ${contextKey}`,
  };
}

export function buildInvestigationCardViewModel(
  card: InvestigationCard,
  accessibleContextKey?: string,
): InvestigationCardViewModel {
  const actionGroup = actionGroupForCard(card);
  const identity = buildInvestigationIdentityViewModel({
    priority: card.priority,
    actionGroup,
  });
  const isRouterArea =
    card.type === "router_neighbourhood_review" ||
    actionGroup === "review_observed_router_area";
  const primaryNeighbourhoodIeee = card.primary_neighbourhood_ieee ?? null;
  const focusLabel = isRouterArea
    ? INVESTIGATION_FOCUS_LABEL_ROUTER_AREA
    : INVESTIGATION_FOCUS_LABEL_DEFAULT;
  const openRouterDetailsLabel =
    isRouterArea && primaryNeighbourhoodIeee
      ? INVESTIGATION_OPEN_ROUTER_DETAILS_LABEL
      : null;
  // Standalone calls use unsuffixed human context; panel assignment adds ordinals.
  const contextKey =
    accessibleContextKey ?? buildInvestigationHumanContext(card);
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
    focusLabel,
    primaryNeighbourhoodIeee,
    openRouterDetailsLabel,
    isRouterArea,
    ...ariaLabelsForContext(focusLabel, openRouterDetailsLabel, contextKey),
  };
}

export function buildInvestigationPanelViewModel(
  investigations: InvestigationCard[],
): InvestigationPanelViewModel {
  const contextKeys = assignAccessibleContextKeys(investigations);
  return {
    title: INVESTIGATION_PANEL_TITLE,
    subtitle: INVESTIGATION_PANEL_SUBTITLE,
    emptyCopy: INVESTIGATION_EMPTY_COPY,
    cards: investigations.map((card) =>
      buildInvestigationCardViewModel(card, contextKeys.get(card.id)),
    ),
  };
}

export {
  INVESTIGATION_SECTION_CHECKS,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_SUPPORTING,
};
