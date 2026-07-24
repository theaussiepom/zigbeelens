import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { liveConnection } from "@/lib/events";
import { shouldRefetchForLiveEvent } from "@/lib/liveResourceEvents";

interface Options {
  /** Refetch only when one of these SSE events arrives. Defaults to all. */
  refetchOn?: readonly string[];
  /** Debounce window for burst events. */
  debounceMs?: number;
  /** Skip fetching (e.g. missing route params). */
  enabled?: boolean;
}

export interface LiveResource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** A later request is running while accepted data remains available. */
  refreshing: boolean;
  refetch: () => void;
}

function inputsEqual(
  previous: ReadonlyArray<unknown>,
  current: ReadonlyArray<unknown>,
): boolean {
  return (
    previous.length === current.length &&
    previous.every((value, index) => Object.is(value, current[index]))
  );
}

/**
 * Fetch a resource and keep it fresh via debounced refetches when matching
 * SSE events arrive. Avoids request spam and tolerates rapid event bursts.
 */
export function useLiveResource<T>(
  fetcher: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
  options: Options = {},
): LiveResource<T> {
  const { refetchOn, debounceMs = 350, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const dataRef = useRef<T | null>(null);
  const tokenRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scopeInputs: ReadonlyArray<unknown> = [enabled, ...deps];
  const committedScopeRef = useRef<ReadonlyArray<unknown>>(scopeInputs);
  const scopeChanged = !inputsEqual(committedScopeRef.current, scopeInputs);

  const run = useCallback(() => {
    if (!enabled) return;
    const token = ++tokenRef.current;
    if (dataRef.current === null) {
      setError(null);
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    fetcherRef
      .current()
      .then((result) => {
        if (token !== tokenRef.current) return;
        dataRef.current = result;
        setData(result);
        setError(null);
        setLoading(false);
        setRefreshing(false);
      })
      .catch((e: unknown) => {
        if (token !== tokenRef.current) return;
        setError(e instanceof ApiError ? e.message : String(e));
        setLoading(false);
        setRefreshing(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Initial + dependency-driven fetch.
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    committedScopeRef.current = [enabled, ...deps];
    dataRef.current = null;
    setData(null);
    setError(null);
    setRefreshing(false);

    if (!enabled) {
      tokenRef.current += 1;
      setLoading(false);
      return;
    }

    setLoading(true);
    run();

    return () => {
      // Invalidate a response owned by an unmounted or superseded scope.
      tokenRef.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  // Live refetch on SSE events (debounced).
  useEffect(() => {
    if (!enabled) return;
    const unsubscribe = liveConnection.subscribeEvents((eventName, payload) => {
      if (!shouldRefetchForLiveEvent(refetchOn, eventName, payload)) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(run, debounceMs);
    });
    return () => {
      unsubscribe();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, debounceMs, refetchOn ? refetchOn.join(",") : "*"]);

  // Poll when SSE is unavailable (some Ingress proxies block EventSource).
  useEffect(() => {
    if (!enabled) return;
    const pollMs = 30_000;
    let interval: ReturnType<typeof setInterval> | null = null;
    const unsubscribe = liveConnection.subscribeState((state) => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
      if (state === "disconnected" && liveConnection.isAccessEnabled()) {
        interval = setInterval(run, pollMs);
      }
    });
    return () => {
      unsubscribe();
      if (interval) clearInterval(interval);
    };
    // A disconnected polling interval is owned by the current resource scope.
    // Tear it down and restart its clock when route/scenario identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps]);

  if (scopeChanged) {
    // Dependency effects run after render. Mask the previous scope immediately
    // so accepted or stale data cannot appear under a new identity meanwhile.
    return {
      data: null,
      error: null,
      loading: enabled,
      refreshing: false,
      refetch: run,
    };
  }

  return { data, error, loading, refreshing, refetch: run };
}
