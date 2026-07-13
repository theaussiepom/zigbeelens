import { Link } from "react-router-dom";
import { Card } from "@/components/ui";
import type { ModelPatternViewModel } from "@/viewModels/overview/modelPatternViewModel";

export function ModelPatternCard({ pattern }: { pattern: ModelPatternViewModel }) {
  return (
    <Card
      title={pattern.title}
      subtitle={`${pattern.networkLabel} · ${pattern.identityLabel}`}
      className="border-zl-border bg-zl-surface"
    >
      <p className="mb-3 text-sm leading-relaxed text-zl-text">{pattern.summary}</p>
      <p className="mb-4 text-xs text-zl-muted">{pattern.timingLabel}</p>
      <div className="mb-4 rounded-lg border border-zl-border/70 bg-zl-surface-2 p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zl-muted">
          What this does not prove
        </p>
        <p className="mt-2 text-sm text-zl-text">{pattern.limitation}</p>
      </div>
      <div className="mb-4">
        <p className="text-xs font-medium uppercase tracking-wide text-zl-muted">
          Practical checks
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zl-muted">
          {pattern.suggestedChecks.map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </div>
      <Link to={pattern.meshHref} className="text-sm text-zl-accent hover:underline">
        {pattern.meshLinkLabel}
      </Link>
    </Card>
  );
}
