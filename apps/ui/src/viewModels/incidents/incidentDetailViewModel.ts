/**
 * Incident Detail ViewModel (Phase 5C-3).
 *
 * Separates the stored incident record from current Device Story decisions.
 */

import type { EvidenceItem, Incident, LimitationItem, TimelineEvent } from "@zigbeelens/shared";
import {
  confidenceLabel,
  formatTime,
  incidentTypeLabel,
  lifecycleLabel,
  relativeTime,
  scopeLabel,
  severityLabel,
} from "@/lib/format";
import {
  buildIncidentDeviceDecisionViewModel,
  buildIncidentRecordViewModel,
  type IncidentDeviceDecisionViewModel,
  type IncidentRecordViewModel,
} from "@/viewModels/incidents/incidentViewModel";

export interface IncidentDetailViewModel {
  record: IncidentRecordViewModel;
  recordedInterpretation: string | null;
  currentDeviceDecisions: IncidentDeviceDecisionViewModel[];
  evidence: EvidenceItem[];
  counterEvidence: EvidenceItem[];
  limitations: LimitationItem[];
  timeline: TimelineEvent[];
  snippet: string;
}

function recordedInterpretation(
  summary: string,
  interpretation: string,
): string | null {
  const text = interpretation.trim();
  if (!text) return null;
  if (text === summary.trim()) return null;
  return text;
}

export function buildIncidentRecordSnippet(vm: IncidentDetailViewModel): string {
  const lines = [
    `# ${vm.record.title}`,
    "",
    `- Lifecycle: ${vm.record.lifecycleLabel}`,
    `- Type: ${vm.record.typeLabel}`,
    `- Scope: ${vm.record.scopeLabel}`,
    `- Networks: ${vm.record.networks.join(", ") || "—"}`,
    `- Opened: ${vm.record.openedExact}`,
    `- Updated: ${vm.record.updatedExact}`,
    `- Resolved: ${vm.record.resolvedExact ?? "—"}`,
    "",
    "## Recorded summary",
    "",
    vm.record.recordSummary,
  ];

  if (vm.currentDeviceDecisions.length > 0) {
    lines.push("", "## Current device decisions", "");
    for (const device of vm.currentDeviceDecisions) {
      lines.push(
        `- ${device.name} — ${device.decision.statusLabel} — ${device.decision.headline}`,
      );
    }
  }

  if (vm.evidence.length > 0) {
    lines.push("", "## Stored evidence", "");
    for (const item of vm.evidence) {
      lines.push(`- ${item.summary}`);
    }
  }

  if (vm.limitations.length > 0) {
    lines.push("", "## Stored limitations", "");
    for (const item of vm.limitations) {
      lines.push(`- ${item.summary}`);
    }
  }

  return lines.join("\n");
}

export function buildIncidentDetailViewModel(incident: Incident): IncidentDetailViewModel {
  const record = buildIncidentRecordViewModel(incident);
  const currentDeviceDecisions = incident.affected_devices.map(
    buildIncidentDeviceDecisionViewModel,
  );
  const vm: IncidentDetailViewModel = {
    record,
    recordedInterpretation: recordedInterpretation(
      incident.summary,
      incident.interpretation,
    ),
    currentDeviceDecisions,
    evidence: incident.evidence,
    counterEvidence: incident.counter_evidence,
    limitations: incident.limitations,
    timeline: incident.timeline,
    snippet: "",
  };
  vm.snippet = buildIncidentRecordSnippet(vm);
  return vm;
}

/** Metadata helpers retained for detail header secondary copy. */
export function recordedSeverityConfidenceLine(incident: Incident): string {
  return `Recorded severity: ${severityLabel(incident.severity)} · Recorded confidence: ${confidenceLabel(incident.confidence)}`;
}

export function incidentTimingLine(incident: Incident): string {
  const parts = [
    `Opened ${formatTime(incident.opened_at)}`,
    `Updated ${relativeTime(incident.updated_at)}`,
  ];
  if (incident.resolved_at) {
    parts.push(`Resolved ${formatTime(incident.resolved_at)}`);
  }
  return parts.join(" · ");
}

export function incidentHeaderMeta(incident: Incident): {
  lifecycleLabel: string;
  typeLabel: string;
  scopeLabel: string;
} {
  return {
    lifecycleLabel: lifecycleLabel(incident.status),
    typeLabel: incidentTypeLabel(incident.type),
    scopeLabel: scopeLabel(incident.scope),
  };
}
