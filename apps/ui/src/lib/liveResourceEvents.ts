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

/** Timeline rows follow ordinary Dashboard/health ingestion invalidations. */
export const TIMELINE_COLLECTION_EVENTS = [
  "dashboard_updated",
  "health_updated",
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

/** Evidence graph facts and coverage change on topology or enrichment fallback. */
export const EVIDENCE_GRAPH_EVENTS = [
  "dashboard_updated",
  "topology_updated",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

/** Mesh display-name inventory follows device projection ownership. */
export const MESH_INVENTORY_EVENTS = [
  ...DEVICE_PROJECTION_EVENTS,
] as const;

/** Volatile HA-derived nested projections. */
export const DEVICE_STORY_EVENTS = [
  "dashboard_updated",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;
export const DEVICE_COVERAGE_EVENTS = [
  "dashboard_updated",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

export const ENRICHMENT_HEALTH_EVENTS = [
  "dashboard_updated",
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

/**
 * Enrichment publishes its exact invalidation before rebuilding Dashboard.
 * A resource that owns the exact event must also accept its Dashboard
 * companion: the current browser may have missed the exact event. Resources
 * whose payload does not change from enrichment can safely ignore the
 * enrichment-only companion.
 */
export function shouldRefetchForLiveEvent(
  refetchOn: readonly string[] | undefined,
  eventName: string,
  payload: LiveEventPayload | undefined,
): boolean {
  const enrichmentOnlyDashboard =
    eventName === "dashboard_updated" &&
    payload !== null &&
    payload !== undefined &&
    Array.isArray(payload.causes) &&
    payload.causes.length === 1 &&
    payload.causes[0] === HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT;
  const ownsEnrichment =
    refetchOn === undefined ||
    refetchOn.includes(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
  if (enrichmentOnlyDashboard && !ownsEnrichment) {
    return false;
  }
  if (refetchOn && !refetchOn.includes(eventName)) return false;
  return true;
}
