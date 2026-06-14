import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { liveConnection } from "@/lib/events";

interface Options {
  /** Refetch only when one of these SSE events arrives. Defaults to all. */
  refetchOn?: string[];
  /** Debounce window for burst events. */
  debounceMs?: number;
  /** Skip fetching (e.g. missing route params). */
  enabled?: boolean;
}

export interface LiveResource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refetch: () => void;
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

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const tokenRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const run = useCallback(() => {
    if (!enabled) return;
    const token = ++tokenRef.current;
    fetcherRef
      .current()
      .then((result) => {
        if (token !== tokenRef.current) return;
        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (token !== tokenRef.current) return;
        setError(e instanceof ApiError ? e.message : String(e));
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Initial + dependency-driven fetch.
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setData(null);
    setError(null);
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Live refetch on SSE events (debounced).
  useEffect(() => {
    if (!enabled) return;
    const unsubscribe = liveConnection.subscribeEvents((eventName) => {
      if (refetchOn && !refetchOn.includes(eventName)) return;
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
      if (state === "disconnected") {
        interval = setInterval(run, pollMs);
      }
    });
    return () => {
      unsubscribe();
      if (interval) clearInterval(interval);
    };
  }, [enabled, run]);

  return { data, error, loading, refetch: run };
}
