import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  type LiveEventPayload,
} from "@/lib/events";

const INCIDENT_LIFECYCLE_EVENTS = [
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  "incidents_updated",
] as const;

/** Dashboard/Overview projection ownership, including generic Dashboard rebuilds. */
export const OVERVIEW_DASHBOARD_EVENTS = [
  "dashboard_update",
  "dashboard_updated",
  "health_updated",
  "network_health_updated",
  "device_health_updated",
  ...INCIDENT_LIFECYCLE_EVENTS,
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

/** Incident membership/content is not changed by HA enrichment. */
export const INCIDENT_COLLECTION_EVENTS = [
  ...INCIDENT_LIFECYCLE_EVENTS,
] as const;

/** Timeline ownership is explicit and excludes generic Dashboard rebuilds. */
export const TIMELINE_COLLECTION_EVENTS = [
  ...INCIDENT_LIFECYCLE_EVENTS,
  "timeline_updated",
  "collector_status",
] as const;

/** Device inventory/detail projections can change when HA enrichment commits. */
export const DEVICE_PROJECTION_EVENTS = [
  "dashboard_updated",
  "device_health_updated",
  "health_updated",
  ...INCIDENT_LIFECYCLE_EVENTS,
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

/** Network summary/detail projections include HA-derived coverage. */
export const NETWORK_PROJECTION_EVENTS = [
  "dashboard_updated",
  "network_health_updated",
  "health_updated",
  ...INCIDENT_LIFECYCLE_EVENTS,
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

/** Evidence graph facts and coverage change on topology or HA enrichment only. */
export const EVIDENCE_GRAPH_EVENTS = [
  "topology_updated",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

/** Mesh display-name inventory follows device projection ownership. */
export const MESH_INVENTORY_EVENTS = [
  ...DEVICE_PROJECTION_EVENTS,
] as const;

/** Volatile HA-derived nested projections. */
export const DEVICE_STORY_EVENTS = [
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;
export const DEVICE_COVERAGE_EVENTS = [
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

export const ENRICHMENT_HEALTH_EVENTS = [
  "collector_status",
  "collector_connected",
  "collector_disconnected",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

export const STORAGE_STATUS_EVENTS = [
  "storage_maintenance_completed",
] as const;
export const REPORT_COLLECTION_EVENTS = ["reports_updated"] as const;
export const RAW_TOPOLOGY_HISTORY_EVENTS = ["topology_updated"] as const;

function categoricalDashboardCauses(
  payload: LiveEventPayload,
): string[] {
  if (!payload || !Array.isArray(payload.causes)) return [];
  return payload.causes.filter(
    (cause): cause is string => typeof cause === "string",
  );
}

/**
 * Enrichment publishes its exact invalidation before rebuilding Dashboard.
 * A resource that owns that exact event must ignore only the accompanying
 * categorically attributed Dashboard event, regardless of delivery delay.
 */
export function shouldRefetchForLiveEvent(
  refetchOn: readonly string[] | undefined,
  eventName: string,
  payload: LiveEventPayload,
): boolean {
  if (refetchOn && !refetchOn.includes(eventName)) return false;
  const dashboardCauses =
    eventName === "dashboard_updated"
      ? categoricalDashboardCauses(payload)
      : [];
  if (
    eventName === "dashboard_updated" &&
    refetchOn?.includes(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT) &&
    dashboardCauses.length === 1 &&
    dashboardCauses[0] === HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT
  ) {
    return false;
  }
  return true;
}
