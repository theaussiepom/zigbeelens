import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

type TestPayload = Record<string, unknown> | null;
type TestConnectionState = "connecting" | "open" | "disconnected";
let connectionState: TestConnectionState = "open";
let accessEnabled = true;
const eventListeners = new Set<
  (eventName: string, payload: TestPayload) => void
>();
const stateListeners = new Set<(state: TestConnectionState) => void>();

function emit(eventName: string, payload: TestPayload = null) {
  for (const listener of eventListeners) listener(eventName, payload);
}

function emitState(state: TestConnectionState) {
  connectionState = state;
  for (const listener of stateListeners) listener(state);
}

vi.mock("@/lib/events", () => ({
  liveConnection: {
    subscribeEvents: (
      listener: (eventName: string, payload: TestPayload) => void,
    ) => {
      eventListeners.add(listener);
      return () => eventListeners.delete(listener);
    },
    subscribeState: (listener: (state: TestConnectionState) => void) => {
      stateListeners.add(listener);
      listener(connectionState);
      return () => stateListeners.delete(listener);
    },
    getState: () => connectionState,
    isAccessEnabled: () => accessEnabled,
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
    accessEnabled = true;
    eventListeners.clear();
    stateListeners.clear();
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

  it("coalesces exact-event bursts and their immediate Dashboard companion", async () => {
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

    act(() => {
      emit("home_assistant_enrichment_updated", {
        type: "home_assistant_enrichment_updated",
      });
      emit("home_assistant_enrichment_updated", {
        type: "home_assistant_enrichment_updated",
      });
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["home_assistant_enrichment_updated"],
      });
    });
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("accepts a delayed Dashboard companion for an enrichment owner", async () => {
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
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("converges when either half of the event pair is delivered alone", async () => {
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
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["home_assistant_enrichment_updated"],
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() =>
      emit("home_assistant_enrichment_updated", {
        type: "home_assistant_enrichment_updated",
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(3);

    act(() => emit("dashboard_updated", { type: "dashboard_updated" }));
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(4);
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

  it("does not duplicate the initial request when EventSource first opens", async () => {
    connectionState = "connecting";
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() => useLiveResource(fetcher, []));
    await flushAsyncWork();

    expect(fetcher).toHaveBeenCalledTimes(1);
    act(() => emitState("open"));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("reconciles once immediately after reconnect and cancels disconnected polling", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() => useLiveResource(fetcher, []));
    await flushAsyncWork();

    act(() => emitState("disconnected"));
    act(() => vi.advanceTimersByTime(29_999));
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => emitState("open"));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() => emitState("open"));
    act(() => vi.advanceTimersByTime(30_001));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("uses reconnect as the immediate reconciliation when both events were missed", async () => {
    const fetcher = vi.fn().mockResolvedValue("accepted");
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

    act(() => emitState("disconnected"));
    // The committed exact event and companion are absent while disconnected.
    act(() => emitState("open"));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("reconciles before a post-reconnect companion and accepts that companion", async () => {
    const fetcher = vi.fn().mockResolvedValue("accepted");
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

    act(() => emitState("disconnected"));
    // The exact event is missed. Reopening must reconcile before its companion.
    act(() => emitState("open"));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() =>
      emit("dashboard_updated", {
        type: "dashboard_updated",
        causes: ["home_assistant_enrichment_updated"],
      }),
    );
    act(() => vi.advanceTimersByTime(300));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("does not poll or reconcile while live access is disabled", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() => useLiveResource(fetcher, []));
    await flushAsyncWork();

    act(() => emitState("disconnected"));
    accessEnabled = false;
    act(() => vi.advanceTimersByTime(30_000));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => emitState("open"));
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("lets reconnect supersede an in-flight disconnected poll", async () => {
    let resolvePoll: ((value: string) => void) | undefined;
    let resolveReconnect: ((value: string) => void) | undefined;
    const fetcher = vi
      .fn<() => Promise<string>>()
      .mockResolvedValueOnce("accepted")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePoll = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReconnect = resolve;
          }),
      );
    const { result } = renderHook(() => useLiveResource(fetcher, []));
    await flushAsyncWork();
    expect(result.current.data).toBe("accepted");

    act(() => emitState("disconnected"));
    act(() => vi.advanceTimersByTime(30_000));
    expect(fetcher).toHaveBeenCalledTimes(2);

    act(() => emitState("open"));
    expect(fetcher).toHaveBeenCalledTimes(3);
    await act(async () => {
      resolveReconnect?.("reconciled");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("reconciled");

    await act(async () => {
      resolvePoll?.("older-poll");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("reconciled");
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

  it("restarts disconnected ownership at a scope boundary and reconciles only the new scope", async () => {
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

    act(() => emitState("open"));
    expect(fetches).toEqual(["network-a", "network-b", "network-b"]);

    await act(async () => {
      pending.get("network-b-2")?.("accepted-b");
      await Promise.resolve();
    });
    expect(result.current.data).toBeNull();

    await act(async () => {
      pending.get("network-b-3")?.("reconciled-b");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("reconciled-b");

    await act(async () => {
      pending.get("network-a-1")?.("superseded-a");
      await Promise.resolve();
    });
    expect(result.current.data).toBe("reconciled-b");
  });

  it("removes reconnect, poll, and event ownership on unmount", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { unmount } = renderHook(() =>
      useLiveResource(fetcher, [], {
        refetchOn: ["dashboard_updated"],
        debounceMs: 300,
      }),
    );
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => emitState("disconnected"));
    act(() => emit("dashboard_updated", { type: "dashboard_updated" }));
    unmount();
    expect(eventListeners.size).toBe(0);
    expect(stateListeners.size).toBe(0);

    act(() => {
      emitState("open");
      vi.advanceTimersByTime(30_000);
    });
    await flushAsyncWork();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
