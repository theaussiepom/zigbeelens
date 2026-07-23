import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  LIVE_EVENTS,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";

describe("live event catalogue", () => {
  beforeEach(() => {
    liveConnection.resetForTests();
    eventSourceTestState.reset();
  });

  it("registers and forwards the exact Home Assistant enrichment invalidation", () => {
    const listener = vi.fn();
    liveConnection.setAccessEnabled(true);
    const unsubscribe = liveConnection.subscribeEvents(listener);

    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeDefined();
    expect(LIVE_EVENTS).toContain(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
    expect(source?.registeredEventNames()).toContain(
      HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    );

    act(() => {
      eventSourceTestState.emit(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
    });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(
      HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
    );

    unsubscribe();
  });
});
