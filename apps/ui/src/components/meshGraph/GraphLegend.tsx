import {
  LIVE_EVIDENCE_CLASSES,
  evidenceClassLabel,
  type EvidenceClass,
} from "@/lib/meshEvidence";
import { evidenceClassTooltip } from "@/lib/meshGraphCopy";
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
 * Legend for the link visual grammar. Lists every live evidence class; the
 * passive-derived and last-known entries appear only when the current data
 * actually contains them, so the legend never advertises evidence the
 * graph cannot show.
 */
export function GraphLegend({
  hasPassiveHints = false,
  hasLastKnownLinks = false,
}: {
  hasPassiveHints?: boolean;
  hasLastKnownLinks?: boolean;
}) {
  const classes = LIVE_EVIDENCE_CLASSES.filter((cls) => {
    if (cls === "passive_derived_association") return hasPassiveHints;
    if (cls === "last_known_link") return hasLastKnownLinks;
    return true;
  });
  return (
    <div aria-label="Link evidence legend" role="group">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zl-muted">
        Link evidence
      </h3>
      <ul className="space-y-2">
        {classes.map((cls) => (
          <li
            key={cls}
            className="flex items-center gap-2 text-xs text-zl-text"
            title={evidenceClassTooltip(cls)}
          >
            <LegendLine cls={cls} />
            <span>{evidenceClassLabel(cls)}</span>
            {cls === "passive_derived_association" && (
              <span className="text-[10px] text-zl-muted">Not topology evidence</span>
            )}
            {cls === "last_known_link" && (
              <span className="text-[10px] text-zl-muted">Not currently reported</span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] leading-snug text-zl-muted">
        Arrowheads mark directional route hints only. Neighbour and investigation links have no
        direction.
      </p>
    </div>
  );
}
