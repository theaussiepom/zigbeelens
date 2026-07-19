import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

let emit: (eventName: string) => void = () => {};

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: (listener: (e: string) => void) => {
      emit = listener;
      return () => {};
    },
    subscribeState: () => () => {},
    getState: () => "open",
    isAccessEnabled: () => true,
  },
  LIVE_EVENTS: [],
}));

import { useLiveResource } from "./useLiveResource";

describe("useLiveResource", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("fetches once on mount and debounces matching live events", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], { refetchOn: ["incident_opened"], debounceMs: 300 }),
    );

    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => {
      emit("incident_opened");
      emit("incident_opened");
      emit("incident_opened");
    });
    // Burst is debounced — no refetch yet.
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(300));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("ignores events that are not in refetchOn", () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], { refetchOn: ["incident_opened"], debounceMs: 300 }),
    );
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => emit("device_health_updated"));
    act(() => vi.advanceTimersByTime(300));
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not fetch when disabled", () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useLiveResource(fetcher, [], { enabled: false }));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});
