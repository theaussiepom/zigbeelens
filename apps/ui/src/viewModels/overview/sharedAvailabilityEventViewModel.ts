/**
 * Overview ViewModel for shared availability events (Phase 4E-3).
 */

import type { SharedAvailabilityEventSummary } from "@zigbeelens/shared";
import { formatTime } from "@/lib/format";

export const SHARED_AVAILABILITY_EVENT_TITLE =
  "Several devices went offline around the same time";

export const SHARED_AVAILABILITY_EVENT_LIMITATION =
  "Devices changing availability around the same time does not prove they share a Zigbee route, path, parent, or root cause.";

const SHARED_AVAILABILITY_EVENT_CHECKS = [
  "Check Zigbee2MQTT status or logs around the event time.",
  "Check MQTT broker or ZigbeeLens collector interruptions around the event time.",
  "Check host restart, maintenance, or broad power events around the same time.",
  "Compare incidents or timeline events from that period.",
] as const;

export interface SharedAvailabilityEventViewModel {
  id: string;
  networkId: string;
  networkLabel: string;
  title: string;
  summary: string;
  timingLabel: string;
  deviceCountLabel: string;
  limitation: string;
  suggestedChecks: string[];
  meshHref: string;
  meshLinkLabel: string;
}

function sharedEventSummary(deviceCount: number, durationMinutes: number): string {
  if (durationMinutes < 1) {
    return `${deviceCount} devices went offline around the same time.`;
  }
  const minuteWord = durationMinutes === 1 ? "minute" : "minutes";
  return `${deviceCount} devices went offline during a shared availability event lasting about ${durationMinutes} ${minuteWord}.`;
}

function timingLabel(startedAt: string, endedAt: string): string {
  const start = formatTime(startedAt);
  const end = formatTime(endedAt);
  if (start && end) {
    return `${start} – ${end}`;
  }
  if (end) return end;
  if (start) return start;
  return "Event timing unavailable";
}

export function buildSharedAvailabilityEventViewModel(
  event: SharedAvailabilityEventSummary,
  networkName?: string | null,
): SharedAvailabilityEventViewModel {
  const deviceCount = event.device_count;
  const durationMinutes = event.duration_minutes;
  const networkLabel = networkName?.trim() || event.network_id;

  return {
    id: event.event_id,
    networkId: event.network_id,
    networkLabel,
    title: SHARED_AVAILABILITY_EVENT_TITLE,
    summary: sharedEventSummary(deviceCount, durationMinutes),
    timingLabel: timingLabel(event.started_at, event.ended_at),
    deviceCountLabel: `${deviceCount} device${deviceCount === 1 ? "" : "s"}`,
    limitation: SHARED_AVAILABILITY_EVENT_LIMITATION,
    suggestedChecks: [...SHARED_AVAILABILITY_EVENT_CHECKS],
    meshHref: `/topology/${event.network_id}`,
    meshLinkLabel: "Review Mesh evidence →",
  };
}
