/**
 * Overview ViewModel for recent changes since last visit (Phase 5A-3).
 */

import type {
  DashboardPayload,
  Incident,
  InvestigationPrioritySummary,
  ModelPatternSummary,
  SharedAvailabilityEventSummary,
  TimelineEvent,
} from "@zigbeelens/shared";
import { formatTime } from "@/lib/format";
import { buildInvestigationIdentityViewModel } from "@/viewModels/topology/investigationIdentity";

export const RECENT_CHANGES_SECTION_TITLE = "Since your last visit";
export const RECENT_CHANGES_SUBTITLE =
  "Changes recorded after your previous Overview visit.";
export const RECENT_CHANGES_FIRST_VISIT_COPY =
  "Recent changes will appear here after your next visit.";
export const MAX_OVERVIEW_RECENT_CHANGES = 6;

export type RecentChangeKind =
  | "shared_event"
  | "model_pattern"
  | "investigation"
  | "timeline"
  | "incident";

export interface RecentChangeViewModel {
  id: string;
  kind: RecentChangeKind;
  title: string;
  summary: string;
  timingLabel: string;
  occurredAt: string;
  href?: string;
  linkLabel?: string;
}

export interface RecentChangesSectionViewModel {
  title: string;
  mode: "first_visit" | "changes";
  firstVisitCopy?: string;
  subtitle?: string;
  items: RecentChangeViewModel[];
}

function afterBoundary(occurredAt: string, boundary: string): boolean {
  return Date.parse(occurredAt) > Date.parse(boundary);
}

function sharedEventSummary(event: SharedAvailabilityEventSummary): string {
  if (event.duration_minutes < 1) {
    return `${event.device_count} devices went offline around the same time.`;
  }
  const minuteWord = event.duration_minutes === 1 ? "minute" : "minutes";
  return `${event.device_count} devices went offline during a shared availability event lasting about ${event.duration_minutes} ${minuteWord}.`;
}

function modelPatternSummary(pattern: ModelPatternSummary): string {
  const dayWord = pattern.lookback_days === 1 ? "day" : "days";
  return `${pattern.affected_count} of ${pattern.group_size} devices with this model have gone offline in the last ${pattern.lookback_days} ${dayWord}.`;
}

function timingLabel(occurredAt: string): string {
  return formatTime(occurredAt) || "Timing unavailable";
}

function isMeaningfulTimelineEvent(event: TimelineEvent): boolean {
  if (event.severity === "healthy") {
    return false;
  }
  const kind = event.kind.toLowerCase();
  if (kind.includes("linkquality") || kind.includes("heartbeat")) {
    return false;
  }
  return Boolean(event.title?.trim());
}

function fromSharedEvent(
  event: SharedAvailabilityEventSummary,
): RecentChangeViewModel {
  return {
    id: event.event_id,
    kind: "shared_event",
    title: "Shared availability event recorded",
    summary: sharedEventSummary(event),
    timingLabel: timingLabel(event.ended_at || event.started_at),
    occurredAt: event.ended_at || event.started_at,
    href: `/investigate/${event.network_id}`,
    linkLabel: "Review Mesh evidence →",
  };
}

function fromModelPattern(pattern: ModelPatternSummary): RecentChangeViewModel {
  const occurredAt = pattern.latest_supporting_evidence_at || "";
  return {
    id: pattern.pattern_id,
    kind: "model_pattern",
    title: "Recent same-model pattern observed",
    summary: modelPatternSummary(pattern),
    timingLabel: timingLabel(occurredAt),
    occurredAt,
    href: `/investigate/${pattern.network_id}`,
    linkLabel: "Review Mesh evidence →",
  };
}

function fromInvestigation(
  priority: InvestigationPrioritySummary,
): RecentChangeViewModel | null {
  const occurredAt = priority.latest_supporting_evidence_at;
  if (!occurredAt) {
    return null;
  }
  const identity = buildInvestigationIdentityViewModel({
    priority: priority.priority,
    actionGroup: priority.action_group,
  });
  return {
    id: priority.id,
    kind: "investigation",
    title: identity.actionLead,
    summary: priority.summary,
    timingLabel: timingLabel(occurredAt),
    occurredAt,
    href: `/investigate/${priority.network_id}`,
    linkLabel: "Investigate in Mesh →",
  };
}

function fromIncident(incident: Incident): RecentChangeViewModel {
  const occurredAt = incident.updated_at || incident.opened_at;
  return {
    id: incident.id,
    kind: "incident",
    title: incident.title,
    summary: incident.summary,
    timingLabel: timingLabel(occurredAt),
    occurredAt,
    href: `/incidents/${incident.id}`,
    linkLabel: "Open incident →",
  };
}

function fromTimeline(event: TimelineEvent): RecentChangeViewModel {
  const href =
    event.incident_id != null
      ? `/incidents/${event.incident_id}`
      : event.network_id && event.ieee_address
        ? `/devices/${event.network_id}/${encodeURIComponent(event.ieee_address)}`
        : event.network_id
          ? `/investigate/${event.network_id}`
          : undefined;
  return {
    id: event.id,
    kind: "timeline",
    title: event.title,
    summary: event.summary,
    timingLabel: timingLabel(event.timestamp),
    occurredAt: event.timestamp,
    href,
    linkLabel: href ? "Open →" : undefined,
  };
}

export function buildRecentChangesSectionViewModel(input: {
  previousLastViewedAt: string | null;
  dashboard: DashboardPayload;
  incidents: Incident[];
}): RecentChangesSectionViewModel {
  const previous = input.previousLastViewedAt;
  if (!previous) {
    return {
      title: RECENT_CHANGES_SECTION_TITLE,
      mode: "first_visit",
      firstVisitCopy: RECENT_CHANGES_FIRST_VISIT_COPY,
      items: [],
    };
  }

  const seenIds = new Set<string>();
  const candidates: RecentChangeViewModel[] = [];

  const pushUnique = (item: RecentChangeViewModel | null) => {
    if (!item || !item.occurredAt) {
      return;
    }
    if (!afterBoundary(item.occurredAt, previous)) {
      return;
    }
    if (seenIds.has(item.id)) {
      return;
    }
    seenIds.add(item.id);
    candidates.push(item);
  };

  // Prefer dedicated domain events over equivalent investigation cards.
  for (const event of input.dashboard.shared_availability_events) {
    pushUnique(fromSharedEvent(event));
  }
  for (const pattern of input.dashboard.model_patterns) {
    pushUnique(fromModelPattern(pattern));
  }
  for (const priority of input.dashboard.investigation_priorities) {
    if (
      priority.card_type === "shared_availability_event" ||
      priority.card_type === "model_pattern_review"
    ) {
      // Dedicated shared-event / model-pattern entries already occupy this id.
      if (seenIds.has(priority.id)) {
        continue;
      }
    }
    pushUnique(fromInvestigation(priority));
  }
  for (const incident of input.incidents) {
    pushUnique(fromIncident(incident));
  }
  for (const event of input.dashboard.recent_timeline) {
    if (!isMeaningfulTimelineEvent(event)) {
      continue;
    }
    if (event.incident_id && seenIds.has(event.incident_id)) {
      continue;
    }
    pushUnique(fromTimeline(event));
  }

  candidates.sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt));
  const items = candidates.slice(0, MAX_OVERVIEW_RECENT_CHANGES);

  return {
    title: RECENT_CHANGES_SECTION_TITLE,
    mode: "changes",
    subtitle: RECENT_CHANGES_SUBTITLE,
    items,
  };
}
