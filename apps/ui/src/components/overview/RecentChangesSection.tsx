import { Link } from "react-router-dom";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import type { RecentChangesSectionViewModel } from "@/viewModels/overview/recentChangesViewModel";

export interface RecentIncidentEvidenceState {
  hasAcceptedData: boolean;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function RecentChangesSection({
  section,
  incidentEvidence,
}: {
  section: RecentChangesSectionViewModel;
  incidentEvidence?: RecentIncidentEvidenceState;
}) {
  const incidentEvidencePending =
    section.mode === "changes" && incidentEvidence && !incidentEvidence.hasAcceptedData;
  const hasDashboardItems = section.items.length > 0;

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
      ) : incidentEvidencePending && !hasDashboardItems && incidentEvidence.loading ? (
        <LoadingState label="Loading incident changes…" />
      ) : incidentEvidencePending && !hasDashboardItems ? (
        <ErrorState
          message="Incident changes are unavailable."
          onRetry={incidentEvidence.onRetry}
          retryLabel="Retry incident changes"
        />
      ) : (
        <div className="space-y-3">
          {incidentEvidencePending && hasDashboardItems && (
            <IncidentEvidenceWarning
              message={
                incidentEvidence.error
                  ? "Incident changes are unavailable. Showing changes from the loaded dashboard evidence."
                  : "Incident changes are still loading. Showing changes from the loaded dashboard evidence."
              }
              onRetry={incidentEvidence.error ? incidentEvidence.onRetry : undefined}
              retryLabel="Retry incident changes"
            />
          )}
          {incidentEvidence?.hasAcceptedData && incidentEvidence.error && (
            <IncidentEvidenceWarning
              message="Incident changes could not be refreshed. Showing the last loaded incident evidence."
              onRetry={incidentEvidence.onRetry}
              retryLabel="Retry incident changes"
            />
          )}
          {section.items.length === 0 ? (
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
        </div>
      )}
    </section>
  );
}

function IncidentEvidenceWarning({
  message,
  onRetry,
  retryLabel,
}: {
  message: string;
  onRetry?: () => void;
  retryLabel: string;
}) {
  return (
    <div
      role="status"
      className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 px-3 py-2 text-sm text-zl-watch"
    >
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          aria-label={retryLabel}
          onClick={onRetry}
          className="mt-2 min-h-11 rounded-lg border border-zl-border px-3 py-1.5 text-sm text-zl-text hover:bg-zl-surface-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}
