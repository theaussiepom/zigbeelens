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

type ContextRichness = 0 | 1 | 2 | 3;

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

function usableSummary(card: InvestigationCard): string | null {
  const summary = card.summary.trim();
  if (!summary || summary === card.title.trim()) return null;
  return summary;
}

function usableEvidenceAt(card: InvestigationCard): string | null {
  const evidenceAt = card.latest_supporting_evidence_at?.trim() ?? "";
  return evidenceAt || null;
}

/** First human supporting line that is not a bare IEEE / opaque id. */
function usableSupportingFallback(card: InvestigationCard): string | null {
  for (const item of card.supporting_evidence) {
    const line = item.trim();
    if (!line || isBareIeee(line)) continue;
    return line;
  }
  return null;
}

/**
 * Progressive human context for action aria-labels.
 * Richness: title → +summary → +latest evidence → +supporting evidence fallback.
 */
export function buildAccessibleContextKey(
  card: InvestigationCard,
  richness: ContextRichness = 0,
): string {
  const title = card.title.trim();
  const parts = [title];
  if (richness >= 1) {
    const summary = usableSummary(card);
    if (summary) parts.push(summary);
  }
  if (richness >= 2) {
    const evidenceAt = usableEvidenceAt(card);
    if (evidenceAt) parts.push(`latest evidence ${evidenceAt}`);
  }
  if (richness >= 3) {
    const fallback = usableSupportingFallback(card);
    if (fallback) parts.push(fallback);
  }
  return parts.join(" — ");
}

/**
 * Assign distinguishable human context keys across a card set.
 * Escalates title → summary → latest evidence → supporting evidence.
 * Never uses array index, bare IEEE, or opaque card ids.
 */
export function assignAccessibleContextKeys(
  cards: InvestigationCard[],
): Map<string, string> {
  const levels = new Map<string, ContextRichness>(
    cards.map((card) => [card.id, 0]),
  );

  const keyFor = (card: InvestigationCard): string =>
    buildAccessibleContextKey(card, levels.get(card.id) ?? 0);

  let changed = true;
  while (changed) {
    changed = false;
    const keys = cards.map((card) => ({ card, key: keyFor(card) }));
    const counts = new Map<string, number>();
    for (const { key } of keys) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    for (const { card, key } of keys) {
      if ((counts.get(key) ?? 0) < 2) continue;
      const level = levels.get(card.id) ?? 0;
      if (level >= 3) continue;
      const next = (level + 1) as ContextRichness;
      const nextKey = buildAccessibleContextKey(card, next);
      if (nextKey !== key || next > level) {
        levels.set(card.id, next);
        changed = true;
      }
    }
  }

  const assigned = new Map<string, string>();
  const finalCounts = new Map<string, number>();
  for (const card of cards) {
    const key = keyFor(card);
    assigned.set(card.id, key);
    finalCounts.set(key, (finalCounts.get(key) ?? 0) + 1);
  }

  const duplicates = [...finalCounts.entries()].filter(([, n]) => n > 1);
  if (duplicates.length > 0) {
    throw new Error(
      "Investigation action accessible names collide after title, summary, " +
        "latest evidence, and supporting-evidence fallback; refusing to expose " +
        "IEEE addresses or opaque card ids as disambiguators.",
    );
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
  // Single-card calls use title-only context; panel assignment escalates when needed.
  const contextKey = accessibleContextKey ?? buildAccessibleContextKey(card, 0);
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
