import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  LIVE_EVENTS,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

describe("live event catalogue", () => {
  beforeEach(() => {
    liveConnection.resetForTests();
    eventSourceTestState.reset();
  });

  it("registers and forwards the exact Home Assistant enrichment invalidation", () => {
    const coreOwnedEvent = oracleFixture.vocabulary.live_event_types[0];
    expect(oracleFixture.vocabulary.live_event_types).toEqual([
      "home_assistant_enrichment_updated",
    ]);
    expect(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT).toBe(coreOwnedEvent);

    const listener = vi.fn();
    liveConnection.setAccessEnabled(true);
    const unsubscribe = liveConnection.subscribeEvents(listener);

    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeDefined();
    expect(LIVE_EVENTS).toContain(coreOwnedEvent);
    expect(source?.registeredEventNames()).toContain(
      HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    );

    act(() => {
      eventSourceTestState.emit(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
    });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(
      HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
      null,
    );

    unsubscribe();
  });

  it("forwards categorical Dashboard causes from the production event payload", () => {
    const listener = vi.fn();
    liveConnection.setAccessEnabled(true);
    const unsubscribe = liveConnection.subscribeEvents(listener);

    eventSourceTestState.emit("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });

    expect(listener).toHaveBeenCalledWith("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });
    unsubscribe();
  });
});
