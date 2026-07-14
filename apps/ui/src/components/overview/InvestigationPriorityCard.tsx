import { Link } from "react-router-dom";
import { Card } from "@/components/ui";
import type { InvestigationPriorityViewModel } from "@/viewModels/overview/investigationPriorityViewModel";
import type { DecisionPillTone } from "@/viewModels/types";

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

export function InvestigationPriorityCard({
  priority,
  emphasized = false,
  showMeshLink = true,
}: {
  priority: InvestigationPriorityViewModel;
  emphasized?: boolean;
  showMeshLink?: boolean;
}) {
  return (
    <Card
      title={priority.actionLead}
      subtitle={`${priority.networkLabel} · ${priority.actionLabel}`}
      className={
        emphasized
          ? "border-zl-accent/40 bg-zl-accent/5"
          : "border-zl-border bg-zl-surface"
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span
          className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${priorityBadgeClass(priority.priorityTone)}`}
          aria-label={`Investigation priority: ${priority.priorityLabel}`}
        >
          {priority.priorityLabel}
        </span>
        <span
          className="inline-block rounded-full border border-zl-border bg-zl-surface-2 px-2 py-0.5 text-[10px] font-medium text-zl-text"
          aria-label={`Investigation action: ${priority.actionLabel}`}
        >
          {priority.actionLabel}
        </span>
      </div>
      <p className="mb-1 text-sm font-medium text-zl-text">{priority.title}</p>
      <p className={`text-sm leading-relaxed text-zl-muted ${showMeshLink ? "mb-4" : ""}`}>
        {priority.summary}
      </p>
      {showMeshLink ? (
        <Link to={priority.meshHref} className="text-sm text-zl-accent hover:underline">
          {priority.meshLinkLabel}
        </Link>
      ) : null}
    </Card>
  );
}
