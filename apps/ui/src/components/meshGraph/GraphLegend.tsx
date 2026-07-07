import {
  LIVE_EVIDENCE_CLASSES,
  evidenceClassLabel,
  type EvidenceClass,
} from "@/lib/meshEvidence";
import { evidenceEdgeStyle } from "@/components/meshGraph/evidenceStyles";

function LegendLine({ cls }: { cls: EvidenceClass }) {
  const style = evidenceEdgeStyle(cls);
  return (
    <svg width="44" height="10" aria-hidden="true" className="shrink-0">
      <line
        x1="2"
        y1="5"
        x2="42"
        y2="5"
        stroke={style.stroke}
        strokeWidth={style.strokeWidth}
        strokeDasharray={style.strokeDasharray}
        strokeLinecap={style.strokeLinecap}
        opacity={style.opacity}
      />
    </svg>
  );
}

/**
 * Legend for the edge visual grammar. Lists every live evidence class; the
 * passive-derived entry appears only when the current data actually
 * contains passive hints, so the legend never advertises evidence the
 * graph cannot show.
 */
export function GraphLegend({ hasPassiveHints = false }: { hasPassiveHints?: boolean }) {
  const classes = LIVE_EVIDENCE_CLASSES.filter(
    (cls) => cls !== "passive_derived_association" || hasPassiveHints,
  );
  return (
    <div aria-label="Link evidence legend" role="group">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zl-muted">
        Link evidence
      </h3>
      <ul className="space-y-2">
        {classes.map((cls) => (
          <li key={cls} className="flex items-center gap-2 text-xs text-zl-text">
            <LegendLine cls={cls} />
            <span>{evidenceClassLabel(cls)}</span>
            {cls === "passive_derived_association" && (
              <span className="text-[10px] text-zl-muted">
                Passive-derived hint, not topology evidence
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] leading-snug text-zl-muted">
        Arrowheads mark directional route/next-hop evidence only. Adjacency and passive links have
        no direction.
      </p>
    </div>
  );
}
