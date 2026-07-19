/**
 * Incident list/record ViewModel (Phase 5C-2).
 *
 * Incidents are event/lifecycle records. Current device interpretation comes
 * from affected-device Device Story decisions — not health/lens fields.
 */

import type { Incident, IncidentDeviceRef, IncidentStatus } from "@zigbeelens/shared";
import {
  confidenceLabel,
  devicePath,
  formatTime,
  incidentTypeLabel,
  lifecycleLabel,
  relativeTime,
  scopeLabel,
  severityLabel,
} from "@/lib/format";
import {
  buildDeviceDecisionBadgeViewModel,
  type DeviceDecisionBadgeViewModel,
} from "@/viewModels/devices/deviceDecisionBadgeViewModel";
import { decisionStatusLabel } from "@/viewModels/decisionCopy";

export interface IncidentDeviceDecisionViewModel {
  key: string;
  name: string;
  networkId: string;
  ieeeAddress: string;
  deviceHref: string;
  decision: DeviceDecisionBadgeViewModel;
  /** Raw decision status from the validated Core contract. */
  decisionStatus: string;
}

export interface IncidentRecordViewModel {
  id: string;
  href: string;

  title: string;
  recordSummary: string;

  lifecycle: IncidentStatus;
  lifecycleLabel: string;

  typeLabel: string;
  scopeLabel: string;

  networks: string[];

  affectedDeviceCount: number;

  currentDecisionSummary: string | null;
  currentDecisionItems: IncidentDeviceDecisionViewModel[];

  openedLabel: string;
  openedExact: string;
  updatedLabel: string;
  updatedExact: string;
  resolvedLabel: string | null;
  resolvedExact: string | null;

  recordedSeverityLabel: string;
  recordedConfidenceLabel: string;
}

const LIFECYCLE_ORDER: Record<IncidentStatus, number> = {
  open: 0,
  watching: 1,
  resolved: 2,
};

/** True when copy mapping could not resolve a known decision status. */
function isUnknownDecisionStatus(status: string): boolean {
  return decisionStatusLabel(status) === "Status unknown";
}

export function buildIncidentDeviceDecisionViewModel(
  ref: IncidentDeviceRef,
): IncidentDeviceDecisionViewModel {
  return {
    key: `${ref.network_id}:${ref.ieee_address}`,
    name: ref.friendly_name,
    networkId: ref.network_id,
    ieeeAddress: ref.ieee_address,
    deviceHref: devicePath(ref.network_id, ref.ieee_address),
    decision: buildDeviceDecisionBadgeViewModel(ref.decision),
    decisionStatus: ref.decision.status,
  };
}

export function buildCurrentDecisionSummary(
  items: IncidentDeviceDecisionViewModel[],
): string | null {
  if (items.length === 0) return null;

  const known = items.filter((item) => !isUnknownDecisionStatus(item.decisionStatus));
  if (known.length === 0) {
    return "Current device decisions unavailable";
  }

  const counts = new Map<string, number>();
  for (const item of known) {
    const label = decisionStatusLabel(item.decisionStatus);
    if (label === "Status unknown") continue;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  if (counts.size === 0) {
    return "Current device decisions unavailable";
  }

  const parts = [...counts.entries()].map(([label, count]) => `${count} ${label}`);
  return `Current device decisions: ${parts.join(" · ")}`;
}

export function buildIncidentRecordViewModel(incident: Incident): IncidentRecordViewModel {
  const currentDecisionItems = incident.affected_devices.map(
    buildIncidentDeviceDecisionViewModel,
  );

  return {
    id: incident.id,
    href: `/incidents/${incident.id}`,
    title: incident.title,
    recordSummary: incident.summary,
    lifecycle: incident.status,
    lifecycleLabel: lifecycleLabel(incident.status),
    typeLabel: incidentTypeLabel(incident.type),
    scopeLabel: scopeLabel(incident.scope),
    networks: [...incident.network_ids],
    affectedDeviceCount: incident.affected_device_count,
    currentDecisionSummary: buildCurrentDecisionSummary(currentDecisionItems),
    currentDecisionItems,
    openedLabel: relativeTime(incident.opened_at),
    openedExact: formatTime(incident.opened_at),
    updatedLabel: relativeTime(incident.updated_at),
    updatedExact: formatTime(incident.updated_at),
    resolvedLabel: incident.resolved_at ? relativeTime(incident.resolved_at) : null,
    resolvedExact: incident.resolved_at ? formatTime(incident.resolved_at) : null,
    recordedSeverityLabel: severityLabel(incident.severity),
    recordedConfidenceLabel: confidenceLabel(incident.confidence),
  };
}

/** Sort raw incidents by server collection order (lifecycle, updated desc, id desc). */
export function compareIncidentsByRecordTiming(a: Incident, b: Incident): number {
  if (LIFECYCLE_ORDER[a.status] !== LIFECYCLE_ORDER[b.status]) {
    return LIFECYCLE_ORDER[a.status] - LIFECYCLE_ORDER[b.status];
  }
  const byUpdated = b.updated_at.localeCompare(a.updated_at);
  if (byUpdated !== 0) return byUpdated;
  return b.id.localeCompare(a.id);
}

export function incidentMatchesSearch(incident: Incident, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    incident.title,
    incident.summary,
    ...incident.affected_devices.map((d) => d.friendly_name),
    ...incident.affected_devices.map((d) => d.ieee_address),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}
