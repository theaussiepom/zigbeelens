import { useEffect, useState } from "react";
import { type ConnectionState, liveConnection } from "@/lib/events";

/** Subscribe to the shared SSE connection state for a live/stale indicator. */
export function useConnection(): ConnectionState {
  const [state, setState] = useState<ConnectionState>(liveConnection.getState());
  useEffect(() => liveConnection.subscribeState(setState), []);
  return state;
}
