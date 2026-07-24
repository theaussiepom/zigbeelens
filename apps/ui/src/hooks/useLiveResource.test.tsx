import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

type TestPayload = Record<string, unknown> | null;
let emit: (eventName: string, payload?: TestPayload) => void = () => {};
type TestConnectionState = "connecting" | "open" | "disconnected";
let connectionState: TestConnectionState = "open";
let emitState: (state: TestConnectionState) => void = () => {};

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: (
      listener: (eventName: string, payload: TestPayload) => void,
    ) => {
      emit = (eventName, payload = null) => listener(eventName, payload);
      return () => {};
    },
    subscribeState: (listener: (state: TestConnectionState) => void) => {
      emitState = (state) => {
        connectionState = state;
        listener(state);
      };
      listener(connectionState);
      return () => {};
    },
    getState: () => connectionState,
    isAccessEnabled: () => true,
  },
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT:
    "home_assistant_enrichment_updated",
  LIVE_EVENTS: [],
}));

import { useLiveResource } from "./useLiveResource";

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useLiveResource", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    connectionState = "open";
  });
  afterEach(() => vi.useRealTimers());

  it("fetches once on mount and debounces matching live events", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], { refetchOn: ["incident_opened"], debounceMs: 300 }),
    );
    await flushAsyncWork();

    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => {
      emit("incident_opened");
      emit("incident_opened");
      emit("incident_opened");
    });
    // Burst is debounced — no refetch yet.
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("ignores events that are not in refetchOn", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], { refetchOn: ["incident_opened"], debounceMs: 300 }),
    );
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => emit("device_health_updated"));
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("ignores the causally attributed Dashboard companion without timing dependence", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], {
        refetchOn: [
          "home_assistant_enrichment_updated",
          "dashboard_updated",
        ],
        debounceMs: 300,
      }),
    );
    await flushAsyncWork();

    act(() =>
      emit("home_assistant_enrichment_updated", {
        type: "home_assistant_enrichment_updated",
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() => vi.advanceTimersByTime(1_000));
    act(() =>
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["home_assistant_enrichment_updated"],
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() => emit("dashboard_updated", { type: "dashboard_updated" }));
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("suppresses the enrichment-attributed Dashboard companion for a Dashboard-only resource", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() =>
      useLiveResource(fetcher, [], {
        refetchOn: ["dashboard_updated", "health_updated"],
        debounceMs: 300,
      }),
    );
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() =>
      emit("home_assistant_enrichment_updated", {
        type: "home_assistant_enrichment_updated",
      }),
    );
    act(() =>
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["home_assistant_enrichment_updated"],
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() =>
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["health_updated"],
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() => emit("dashboard_updated", { type: "dashboard_updated" }));
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("does not fetch when disabled", () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useLiveResource(fetcher, [], { enabled: false }));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(false);
  });

  it("distinguishes initial failure from a failed refresh with accepted data", async () => {
    let rejectRefresh: ((reason?: unknown) => void) | undefined;
    const fetcher = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error("initial failure"));
    const { result } = renderHook(() =>
      useLiveResource(fetcher, [], {
        refetchOn: ["home_assistant_enrichment_updated"],
        debounceMs: 300,
      }),
    );

    await flushAsyncWork();
    expect(result.current.error).toContain("initial failure");
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(false);

    fetcher.mockResolvedValueOnce("accepted");
    act(() => result.current.refetch());
    expect(result.current.loading).toBe(true);
    await flushAsyncWork();
    expect(result.current.data).toBe("accepted");
    expect(result.current.error).toBeNull();

    fetcher.mockImplementationOnce(
      () =>
        new Promise<string>((_resolve, reject) => {
          rejectRefresh = reject;
        }),
    );
    act(() => emit("home_assistant_enrichment_updated"));
    act(() => vi.advanceTimersByTime(300));

    expect(result.current.data).toBe("accepted");
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(true);

    await act(async () => {
      rejectRefresh?.(new Error("background failure"));
      await Promise.resolve();
    });

    expect(result.current.data).toBe("accepted");
    expect(result.current.error).toContain("background failure");
    expect(result.current.refreshing).toBe(false);

    fetcher.mockRejectedValueOnce(new Error("repeated failure"));
    act(() => result.current.refetch());
    expect(result.current.data).toBe("accepted");
    expect(result.current.refreshing).toBe(true);
    await flushAsyncWork();
    expect(result.current.data).toBe("accepted");
    expect(result.current.error).toContain("repeated failure");
    expect(result.current.refreshing).toBe(false);

    fetcher.mockResolvedValueOnce("updated");
    act(() => result.current.refetch());
    expect(result.current.data).toBe("accepted");
    expect(result.current.refreshing).toBe(true);
    await flushAsyncWork();
    expect(result.current.data).toBe("updated");
    expect(result.current.error).toBeNull();
    expect(result.current.refreshing).toBe(false);
  });

  it("masks accepted data immediately across identity changes and ignores superseded work", async () => {
    const pending = new Map<string, (value: string) => void>();
    const { result, rerender } = renderHook(
      ({ identity }) =>
        useLiveResource(
          () =>
            new Promise<string>((resolve) => {
              pending.set(`${identity}-${pending.size}`, resolve);
            }),
          [identity],
        ),
      { initialProps: { identity: "device-a" } },
    );

    expect(pending.size).toBe(1);
    await act(async () => {
      pending.get("device-a-0")?.("accepted-a");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("accepted-a");

    act(() => emit("scope-a-live-event"));
    act(() => result.current.refetch());
    expect(pending.size).toBe(2);
    rerender({ identity: "device-b" });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(pending.size).toBe(3);
    act(() => vi.advanceTimersByTime(350));
    expect(pending.size).toBe(3);

    await act(async () => {
      pending.get("device-a-1")?.("superseded-a");
      await Promise.resolve();
    });
    expect(result.current.data).toBeNull();

    await act(async () => {
      pending.get("device-b-2")?.("accepted-b");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("accepted-b");
  });

  it("restarts disconnected polling at an identity boundary without duplicating the new request", async () => {
    const pending = new Map<string, (value: string) => void>();
    const fetches: string[] = [];
    const { result, rerender } = renderHook(
      ({ identity }) =>
        useLiveResource(
          () =>
            new Promise<string>((resolve) => {
              fetches.push(identity);
              pending.set(`${identity}-${fetches.length}`, resolve);
            }),
          [identity],
        ),
      { initialProps: { identity: "network-a" } },
    );

    await act(async () => {
      pending.get("network-a-1")?.("accepted-a");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("accepted-a");

    act(() => emitState("disconnected"));
    act(() => vi.advanceTimersByTime(29_999));
    rerender({ identity: "network-b" });

    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(fetches).toEqual(["network-a", "network-b"]);

    // Crossing scope A's original 30-second boundary must not fire its poll.
    act(() => vi.advanceTimersByTime(1));
    expect(fetches).toEqual(["network-a", "network-b"]);

    await act(async () => {
      pending.get("network-b-2")?.("accepted-b");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("accepted-b");
  });
});
