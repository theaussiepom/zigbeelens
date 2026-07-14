import { Link } from "react-router-dom";
import { Card } from "@/components/ui";
import type { DataCoverageWarningViewModel } from "@/viewModels/overview/dataCoverageViewModel";

export function DataCoverageWarningCard({
  warning,
  showMeshLink = true,
}: {
  warning: DataCoverageWarningViewModel;
  showMeshLink?: boolean;
}) {
  return (
    <Card
      title={warning.title}
      subtitle={warning.networkLabel}
      className="border-zl-border bg-zl-surface"
    >
      <p className="mb-3 text-sm leading-relaxed text-zl-text">{warning.summary}</p>
      <div
        className={`rounded-lg border border-zl-border/70 bg-zl-surface-2 p-3 ${showMeshLink ? "mb-4" : ""}`}
      >
        <p className="text-xs font-medium uppercase tracking-wide text-zl-muted">
          Practical check
        </p>
        <p className="mt-2 text-sm text-zl-muted">{warning.check}</p>
      </div>
      {showMeshLink ? (
        <Link to={warning.meshHref} className="text-sm text-zl-accent hover:underline">
          {warning.meshLinkLabel}
        </Link>
      ) : null}
    </Card>
  );
}
