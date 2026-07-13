import { Link } from "react-router-dom";
import { Card } from "@/components/ui";
import type { SharedAvailabilityEventViewModel } from "@/viewModels/overview/sharedAvailabilityEventViewModel";

export function SharedAvailabilityEventCard({
  event,
}: {
  event: SharedAvailabilityEventViewModel;
}) {
  return (
    <Card
      title={event.title}
      subtitle={`${event.networkLabel} · ${event.timingLabel}`}
      className="border-zl-border bg-zl-surface"
    >
      <p className="mb-3 text-sm leading-relaxed text-zl-text">{event.summary}</p>
      <p className="mb-4 text-xs text-zl-muted">{event.deviceCountLabel}</p>
      <div className="mb-4 rounded-lg border border-zl-border/70 bg-zl-surface-2 p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zl-muted">
          What this does not prove
        </p>
        <p className="mt-2 text-sm text-zl-text">{event.limitation}</p>
      </div>
      <div className="mb-4">
        <p className="text-xs font-medium uppercase tracking-wide text-zl-muted">
          Practical checks
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zl-muted">
          {event.suggestedChecks.map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </div>
      <Link to={event.meshHref} className="text-sm text-zl-accent hover:underline">
        {event.meshLinkLabel}
      </Link>
    </Card>
  );
}
