import { useMemo, useState } from "react";
import type { InvestigationCard } from "@/lib/api";
import {
  buildInvestigationCardViewModel,
  buildInvestigationPanelViewModel,
  INVESTIGATION_SECTION_CHECKS,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_SUPPORTING,
} from "@/viewModels/topology/investigationViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

/**
 * "Where to look first" — ranked problem-first investigation cards.
 *
 * Cards come fully formed from the backend (deterministic ranking over
 * existing evidence only). This panel renders action-led ViewModels and
 * drives the visual graph focus: focusing a card highlights involved devices
 * and ensures the involved edges are drawn. Focus is visual only — it never
 * moves nodes, never changes connection-control choices, and never mutates
 * saved layout.
 */

export {
  INVESTIGATION_PANEL_TITLE,
  INVESTIGATION_PANEL_SUBTITLE,
  INVESTIGATION_EMPTY_COPY,
} from "@/lib/meshGraphCopy";

/** How many cards render before "Show more". */
export const INVESTIGATION_CARDS_INITIALLY_VISIBLE = 3;

function priorityBadgeClass(tone: DecisionPillTone): string {
  switch (tone) {
    case "watch":
      return "border-zl-watch/50 bg-zl-watch/10 text-zl-watch";
    case "action":
      return "border-zl-accent/50 bg-zl-accent/10 text-zl-accent";
    case "muted":
      return "border-zl-border bg-zl-surface-2 text-zl-muted";
    default:
      return "border-zl-border bg-zl-surface-2 text-zl-muted";
  }
}

function InvestigationCardView({
  card,
  viewModel,
  active,
  onFocus,
  onClearFocus,
  canOpenPrimaryDevice,
  onOpenPrimaryDevice,
}: {
  card: InvestigationCard;
  viewModel: ReturnType<typeof buildInvestigationCardViewModel>;
  active: boolean;
  onFocus: (card: InvestigationCard) => void;
  onClearFocus: () => void;
  canOpenPrimaryDevice?: (card: InvestigationCard) => boolean;
  onOpenPrimaryDevice?: (card: InvestigationCard) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const showOpenRouter =
    Boolean(viewModel.openRouterDetailsLabel) &&
    Boolean(onOpenPrimaryDevice) &&
    (canOpenPrimaryDevice?.(card) ?? false);

  return (
    <div
      data-testid="investigation-card"
      data-investigation-id={card.id}
      data-investigation-type={card.type}
      className={`rounded-lg border p-2.5 ${
        active ? "border-zl-accent bg-zl-accent/5" : "border-zl-border bg-zl-surface-2"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${priorityBadgeClass(viewModel.priorityTone)}`}
          aria-label={`Investigation priority: ${viewModel.priorityLabel}`}
        >
          {viewModel.priorityLabel}
        </span>
        <span
          className="inline-block rounded-full border border-zl-border bg-zl-surface px-2 py-0.5 text-[10px] font-medium text-zl-text"
          aria-label={`Investigation action: ${viewModel.actionGroupLabel}`}
        >
          {viewModel.actionGroupLabel}
        </span>
      </div>
      <h4 className="mt-1.5 text-sm font-semibold leading-snug text-zl-text">
        {viewModel.actionLead}
      </h4>
      <p className="mt-1 text-[11px] leading-snug text-zl-muted">{viewModel.whyItMatters}</p>
      <p className="mt-1 text-[11px] leading-snug text-zl-text">{viewModel.contextTitle}</p>
      <p className="mt-0.5 text-[11px] leading-snug text-zl-muted">{viewModel.contextSummary}</p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {active ? (
          <button
            type="button"
            onClick={onClearFocus}
            aria-label={viewModel.clearFocusAriaLabel}
            className="rounded-lg border border-zl-accent bg-zl-accent/10 px-2.5 py-1 text-[11px] font-medium text-zl-accent hover:bg-zl-accent/20"
          >
            Clear focus
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onFocus(card)}
            aria-label={viewModel.focusAriaLabel}
            className="rounded-lg border border-zl-border bg-zl-surface px-2.5 py-1 text-[11px] font-medium text-zl-text hover:border-zl-accent/40"
          >
            {viewModel.focusLabel}
          </button>
        )}
        {showOpenRouter && (
          <button
            type="button"
            onClick={() => onOpenPrimaryDevice?.(card)}
            aria-label={viewModel.openPrimaryDeviceAriaLabel!}
            className="rounded-lg border border-zl-border bg-zl-surface px-2.5 py-1 text-[11px] font-medium text-zl-text hover:border-zl-accent/40"
          >
            {viewModel.openRouterDetailsLabel}
          </button>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={
            expanded ? viewModel.hideDetailsAriaLabel : viewModel.detailsAriaLabel
          }
          className="text-[11px] text-zl-accent hover:underline"
        >
          {expanded ? "Hide details" : "View details"}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 text-[11px] leading-snug text-zl-muted">
          <div>
            <p className="font-semibold text-zl-text" aria-label="Supporting evidence">
              {INVESTIGATION_SECTION_SUPPORTING}
            </p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
              {viewModel.supportingEvidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          {viewModel.limitations.length > 0 && (
            <div>
              <p className="font-semibold text-zl-text">{INVESTIGATION_SECTION_DOES_NOT_PROVE}</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {viewModel.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {viewModel.suggestedChecks.length > 0 && (
            <div>
              <p className="font-semibold text-zl-text">{INVESTIGATION_SECTION_CHECKS}</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {viewModel.suggestedChecks.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function InvestigationPanel({
  investigations,
  activeInvestigationId,
  onFocus,
  onClearFocus,
  canOpenPrimaryDevice,
  onOpenPrimaryDevice,
}: {
  investigations: InvestigationCard[];
  activeInvestigationId: string | null;
  onFocus: (card: InvestigationCard) => void;
  onClearFocus: () => void;
  canOpenPrimaryDevice?: (card: InvestigationCard) => boolean;
  onOpenPrimaryDevice?: (card: InvestigationCard) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const panel = useMemo(
    () => buildInvestigationPanelViewModel(investigations),
    [investigations],
  );
  const collapsedCards = useMemo(() => {
    const activeCardIndex = activeInvestigationId
      ? panel.cards.findIndex((card) => card.id === activeInvestigationId)
      : -1;
    return panel.cards.filter(
      (_card, index) =>
        index < INVESTIGATION_CARDS_INITIALLY_VISIBLE || index === activeCardIndex,
    );
  }, [activeInvestigationId, panel.cards]);
  const visibleCards = showAll ? panel.cards : collapsedCards;
  const hiddenCardCount = panel.cards.length - collapsedCards.length;
  const cardById = useMemo(
    () => new Map(investigations.map((card) => [card.id, card])),
    [investigations],
  );
  const clearFocus = () => {
    setShowAll(false);
    onClearFocus();
  };

  return (
    <div role="region" aria-label={panel.title} className="space-y-3">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
          {panel.title}
        </h3>
        <p className="mt-1 text-[11px] leading-snug text-zl-muted">{panel.subtitle}</p>
      </div>

      {panel.cards.length === 0 ? (
        <p className="text-[11px] leading-snug text-zl-muted" data-testid="investigation-empty">
          {panel.emptyCopy}
        </p>
      ) : (
        <>
          <div className="space-y-2">
            {visibleCards.map((viewModel) => {
              const card = cardById.get(viewModel.id);
              if (!card) return null;
              return (
                <InvestigationCardView
                  key={viewModel.id}
                  card={card}
                  viewModel={viewModel}
                  active={viewModel.id === activeInvestigationId}
                  onFocus={onFocus}
                  onClearFocus={clearFocus}
                  canOpenPrimaryDevice={canOpenPrimaryDevice}
                  onOpenPrimaryDevice={onOpenPrimaryDevice}
                />
              );
            })}
          </div>
          {hiddenCardCount > 0 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-[11px] text-zl-accent hover:underline"
            >
              {showAll
                ? "Show fewer"
                : `Show more (${hiddenCardCount})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
