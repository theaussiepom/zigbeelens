import type { EvidenceCoverageItemViewModel } from "@/viewModels/coverage/coverageStripViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

function pillClassName(tone: DecisionPillTone): string {
  if (tone === "coverage") {
    return "inline-flex items-center rounded-full border border-zl-unavailable/40 bg-zl-unavailable/10 px-2 py-0.5 text-[11px] font-medium text-zl-unavailable";
  }
  if (tone === "watch") {
    return "inline-flex items-center rounded-full border border-zl-watch/40 bg-zl-watch/10 px-2 py-0.5 text-[11px] font-medium text-zl-watch";
  }
  if (tone === "action") {
    return "inline-flex items-center rounded-full border border-zl-accent/40 bg-zl-accent/10 px-2 py-0.5 text-[11px] font-medium text-zl-accent";
  }
  return "inline-flex items-center rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[11px] font-medium text-zl-muted";
}

function CoveragePill({ item }: { item: EvidenceCoverageItemViewModel }) {
  return (
    <span className={pillClassName(item.tone)} title={item.helper}>
      {item.label}
    </span>
  );
}

export function EvidenceCoverageStrip({
  title,
  items,
}: {
  title: string;
  items: EvidenceCoverageItemViewModel[];
}) {
  if (items.length === 0) return null;

  return (
    <div data-testid="evidence-coverage-strip" className="space-y-1.5">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-zl-muted">
        {title}
      </h3>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <CoveragePill key={item.label} item={item} />
        ))}
      </div>
    </div>
  );
}
