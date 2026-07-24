import { describe, expect, it } from "vitest";
import {
  DEVICE_COVERAGE_EVENTS,
  DEVICE_PROJECTION_EVENTS,
  DEVICE_STORY_EVENTS,
  ENRICHMENT_HEALTH_EVENTS,
  EVIDENCE_GRAPH_EVENTS,
  INCIDENT_COLLECTION_EVENTS,
  NETWORK_PROJECTION_EVENTS,
  MESH_INVENTORY_EVENTS,
  OVERVIEW_DASHBOARD_EVENTS,
  RAW_TOPOLOGY_HISTORY_EVENTS,
  REPORT_COLLECTION_EVENTS,
  STORAGE_STATUS_EVENTS,
  TIMELINE_COLLECTION_EVENTS,
  shouldRefetchForLiveEvent,
} from "@/lib/liveResourceEvents";

const ENRICHMENT = "home_assistant_enrichment_updated";

describe("live event to resource ownership", () => {
  it("owns enrichment only for projections whose public payload can change", () => {
    for (const events of [
      OVERVIEW_DASHBOARD_EVENTS,
      DEVICE_PROJECTION_EVENTS,
      NETWORK_PROJECTION_EVENTS,
      EVIDENCE_GRAPH_EVENTS,
      MESH_INVENTORY_EVENTS,
      DEVICE_STORY_EVENTS,
      DEVICE_COVERAGE_EVENTS,
      ENRICHMENT_HEALTH_EVENTS,
    ]) {
      expect(events).toContain(ENRICHMENT);
    }

    for (const events of [
      INCIDENT_COLLECTION_EVENTS,
      TIMELINE_COLLECTION_EVENTS,
      RAW_TOPOLOGY_HISTORY_EVENTS,
      STORAGE_STATUS_EVENTS,
      REPORT_COLLECTION_EVENTS,
    ]) {
      expect(events).not.toContain(ENRICHMENT);
      expect(events).not.toContain("dashboard_updated");
    }
  });

  it("preserves ordinary Dashboard invalidation ownership", () => {
    for (const events of [
      OVERVIEW_DASHBOARD_EVENTS,
      DEVICE_PROJECTION_EVENTS,
      NETWORK_PROJECTION_EVENTS,
      MESH_INVENTORY_EVENTS,
    ]) {
      expect(
        shouldRefetchForLiveEvent(
          events,
          "dashboard_updated",
          {
            type: "dashboard_updated",
            causes: ["health_updated"],
          },
        ),
      ).toBe(true);
      expect(
        shouldRefetchForLiveEvent(
          events,
          "dashboard_updated",
          { type: "dashboard_updated" },
        ),
      ).toBe(true);
    }
    expect(
      shouldRefetchForLiveEvent(
        OVERVIEW_DASHBOARD_EVENTS,
        "dashboard_updated",
        {
          type: "dashboard_updated",
          causes: [ENRICHMENT, "health_updated"],
        },
      ),
    ).toBe(true);
  });

  it("suppresses only the attributed companion Dashboard event without timing", () => {
    expect(
      shouldRefetchForLiveEvent(
        OVERVIEW_DASHBOARD_EVENTS,
        ENRICHMENT,
        { type: ENRICHMENT },
      ),
    ).toBe(true);
    for (const events of [
      OVERVIEW_DASHBOARD_EVENTS,
      DEVICE_PROJECTION_EVENTS,
      NETWORK_PROJECTION_EVENTS,
      MESH_INVENTORY_EVENTS,
    ]) {
      expect(
        shouldRefetchForLiveEvent(
          events,
          "dashboard_updated",
          {
            type: "dashboard_updated",
            causes: [ENRICHMENT],
          },
        ),
      ).toBe(false);
    }
  });
});
