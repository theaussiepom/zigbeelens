import { useState } from "react";
import type { InvestigationCard } from "@/lib/api";
import {
  INVESTIGATION_EMPTY_COPY,
  INVESTIGATION_PANEL_SUBTITLE,
  INVESTIGATION_PANEL_TITLE,
  INVESTIGATION_SECTION_CHECKS,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_SUPPORTING,
  INVESTIGATION_SECTION_WHY,
} from "@/lib/meshGraphCopy";

/**
 * "Where to look first" — ranked problem-first investigation cards.
 *
 * Cards come fully formed from the backend (deterministic ranking over
 * existing evidence only). This panel renders them and drives the visual
 * graph focus: focusing a card highlights involved devices and ensures the
 * involved edges are drawn. Focus is visual only — it never moves nodes,
 * never changes connection-control choices, and never mutates saved layout.
 */

export {
  INVESTIGATION_PANEL_TITLE,
  INVESTIGATION_PANEL_SUBTITLE,
  INVESTIGATION_EMPTY_COPY,
} from "@/lib/meshGraphCopy";

/** How many cards render before "Show more". */
export const INVESTIGATION_CARDS_INITIALLY_VISIBLE = 3;

function priorityBadgeClass(priority: InvestigationCard["priority"]): string {
  switch (priority) {
    case "Review first":
      return "border-zl-watch/50 bg-zl-watch/10 text-zl-watch";
    case "Worth checking":
      return "border-zl-accent/50 bg-zl-accent/10 text-zl-accent";
    case "Lower priority":
      return "border-zl-border bg-zl-surface-2 text-zl-muted";
  }
}

function InvestigationCardView({
  card,
  active,
  onFocus,
  onClearFocus,
}: {
  card: InvestigationCard;
  active: boolean;
  onFocus: (card: InvestigationCard) => void;
  onClearFocus: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      data-testid="investigation-card"
      data-investigation-id={card.id}
      className={`rounded-lg border p-2.5 ${
        active ? "border-zl-accent bg-zl-accent/5" : "border-zl-border bg-zl-surface-2"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${priorityBadgeClass(card.priority)}`}
          aria-label={`Investigation priority: ${card.priority}`}
        >
          {card.priority}
        </span>
      </div>
      <h4 className="mt-1.5 text-sm font-semibold leading-snug text-zl-text">{card.title}</h4>
      <p className="mt-1 text-[11px] leading-snug text-zl-muted">{card.summary}</p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {active ? (
          <button
            type="button"
            onClick={onClearFocus}
            aria-label={`Clear focus for ${card.title}`}
            className="rounded-lg border border-zl-accent bg-zl-accent/10 px-2.5 py-1 text-[11px] font-medium text-zl-accent hover:bg-zl-accent/20"
          >
            Clear focus
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onFocus(card)}
            aria-label={`Focus graph on ${card.title}`}
            className="rounded-lg border border-zl-border bg-zl-surface px-2.5 py-1 text-[11px] font-medium text-zl-text hover:border-zl-accent/40"
          >
            Focus graph
          </button>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="text-[11px] text-zl-accent hover:underline"
        >
          {expanded ? "Hide details" : "View details"}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 text-[11px] leading-snug text-zl-muted">
          <div>
            <p className="font-semibold text-zl-text">{INVESTIGATION_SECTION_WHY}</p>
            <p className="mt-0.5">{card.why_it_matters}</p>
          </div>
          <div>
            <p className="font-semibold text-zl-text" aria-label="Supporting evidence">
              {INVESTIGATION_SECTION_SUPPORTING}
            </p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
              {card.supporting_evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          {card.limitations.length > 0 && (
            <div>
              <p className="font-semibold text-zl-text">{INVESTIGATION_SECTION_DOES_NOT_PROVE}</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {card.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {card.suggested_next_steps.length > 0 && (
            <div>
              <p className="font-semibold text-zl-text">{INVESTIGATION_SECTION_CHECKS}</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {card.suggested_next_steps.map((item) => (
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
}: {
  investigations: InvestigationCard[];
  activeInvestigationId: string | null;
  onFocus: (card: InvestigationCard) => void;
  onClearFocus: () => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll
    ? investigations
    : investigations.slice(0, INVESTIGATION_CARDS_INITIALLY_VISIBLE);

  return (
    <div role="region" aria-label={INVESTIGATION_PANEL_TITLE} className="space-y-3">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zl-muted">
          {INVESTIGATION_PANEL_TITLE}
        </h3>
        <p className="mt-1 text-[11px] leading-snug text-zl-muted">
          {INVESTIGATION_PANEL_SUBTITLE}
        </p>
      </div>

      {investigations.length === 0 ? (
        <p className="text-[11px] leading-snug text-zl-muted" data-testid="investigation-empty">
          {INVESTIGATION_EMPTY_COPY}
        </p>
      ) : (
        <>
          <div className="space-y-2">
            {visible.map((card) => (
              <InvestigationCardView
                key={card.id}
                card={card}
                active={card.id === activeInvestigationId}
                onFocus={onFocus}
                onClearFocus={onClearFocus}
              />
            ))}
          </div>
          {investigations.length > INVESTIGATION_CARDS_INITIALLY_VISIBLE && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-[11px] text-zl-accent hover:underline"
            >
              {showAll
                ? "Show fewer"
                : `Show more (${investigations.length - INVESTIGATION_CARDS_INITIALLY_VISIBLE})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
