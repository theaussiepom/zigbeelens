/**
 * Presentation-only incident list card for record-oriented Incidents page.
 * Receives a ViewModel; does not interpret health, lens, or decision codes.
 */

import { Link } from "react-router-dom";
import { Badge, LifecycleBadge, NetworkBadge } from "@/components/ui";
import type { IncidentRecordViewModel } from "@/viewModels/incidents/incidentViewModel";

export function IncidentRecordCard({ record }: { record: IncidentRecordViewModel }) {
  return (
    <Link
      to={record.href}
      className="block rounded-xl border border-zl-border bg-zl-surface p-5 transition-colors hover:border-zl-accent/40"
      data-testid="incident-record-card"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <LifecycleBadge status={record.lifecycle} />
        <Badge>{record.typeLabel}</Badge>
        <span className="text-xs text-zl-muted">
          {record.scopeLabel} · Recorded severity: {record.recordedSeverityLabel} ·
          Recorded confidence: {record.recordedConfidenceLabel}
        </span>
      </div>
      <h3 className="text-lg font-semibold text-zl-text">{record.title}</h3>
      <p className="mt-1 text-sm text-zl-muted">{record.recordSummary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {record.networks.map((n) => (
          <NetworkBadge key={n} network={n} />
        ))}
        <span className="text-xs text-zl-muted">
          {record.affectedDeviceCount} affected device
          {record.affectedDeviceCount === 1 ? "" : "s"}
        </span>
      </div>
      {record.currentDecisionSummary ? (
        <p className="mt-3 text-xs text-zl-text">{record.currentDecisionSummary}</p>
      ) : null}
      <p
        className="mt-3 text-xs text-zl-muted"
        title={`Opened ${record.openedExact} · Updated ${record.updatedExact}${
          record.resolvedExact ? ` · Resolved ${record.resolvedExact}` : ""
        }`}
      >
        Opened {record.openedLabel} · Updated {record.updatedLabel}
        {record.resolvedLabel ? ` · Resolved ${record.resolvedLabel}` : ""}
      </p>
    </Link>
  );
}
