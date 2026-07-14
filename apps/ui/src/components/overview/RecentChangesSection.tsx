import { Link } from "react-router-dom";
import { Card, EmptyState } from "@/components/ui";
import type { RecentChangesSectionViewModel } from "@/viewModels/overview/recentChangesViewModel";

export function RecentChangesSection({
  section,
}: {
  section: RecentChangesSectionViewModel;
}) {
  return (
    <section className="space-y-3" aria-label={section.title}>
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zl-muted">
          {section.title}
        </h2>
        {section.mode === "changes" && section.subtitle ? (
          <p className="mt-1 text-sm text-zl-muted">{section.subtitle}</p>
        ) : null}
      </div>
      {section.mode === "first_visit" ? (
        <EmptyState title={section.firstVisitCopy ?? ""} />
      ) : section.items.length === 0 ? (
        <EmptyState title="No recorded changes since your previous Overview visit." />
      ) : (
        <div className="grid gap-3">
          {section.items.map((item) => (
            <Card
              key={item.id}
              title={item.title}
              subtitle={item.timingLabel}
              className="border-zl-border bg-zl-surface"
            >
              <p className="mb-3 text-sm leading-relaxed text-zl-muted">{item.summary}</p>
              {item.href && item.linkLabel ? (
                <Link to={item.href} className="text-sm text-zl-accent hover:underline">
                  {item.linkLabel}
                </Link>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
