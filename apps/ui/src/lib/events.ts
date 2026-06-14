import { eventStreamUrl } from "@/lib/api";

export type ConnectionState = "connecting" | "open" | "disconnected";

/** Known SSE event names emitted by ZigbeeLens Core. */
export const LIVE_EVENTS = [
  "dashboard_update",
  "dashboard_updated",
  "health_updated",
  "device_health_updated",
  "network_health_updated",
  "incident_opened",
  "incident_updated",
  "incident_resolved",
  "incidents_updated",
  "collector_connected",
  "collector_disconnected",
  "collector_status",
] as const;

type EventListener = (eventName: string) => void;
type StateListener = (state: ConnectionState) => void;

/**
 * Single shared EventSource connection to Core. Pages subscribe to event-name
 * notifications and refetch their own data; connection state is exposed
 * separately for a subtle live/stale indicator.
 */
class LiveConnection {
  private source: EventSource | null = null;
  private eventListeners = new Set<EventListener>();
  private stateListeners = new Set<StateListener>();
  private state: ConnectionState = "connecting";
  private refCount = 0;

  getState(): ConnectionState {
    return this.state;
  }

  subscribeEvents(listener: EventListener): () => void {
    this.eventListeners.add(listener);
    this.ensureConnected();
    return () => {
      this.eventListeners.delete(listener);
      this.maybeDisconnect();
    };
  }

  subscribeState(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    this.ensureConnected();
    listener(this.state);
    return () => {
      this.stateListeners.delete(listener);
      this.maybeDisconnect();
    };
  }

  private ensureConnected() {
    this.refCount += 1;
    if (this.source) return;
    this.connect();
  }

  private maybeDisconnect() {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount === 0 && this.source) {
      this.source.close();
      this.source = null;
      this.setState("connecting");
    }
  }

  private connect() {
    this.setState("connecting");
    let source: EventSource;
    try {
      source = new EventSource(eventStreamUrl());
    } catch {
      this.setState("disconnected");
      return;
    }
    this.source = source;

    source.onopen = () => this.setState("open");
    source.onerror = () => {
      // EventSource retries automatically; reflect the gap to the UI.
      this.setState("disconnected");
    };

    const notify = (eventName: string) => () => {
      this.setState("open");
      for (const listener of this.eventListeners) listener(eventName);
    };

    for (const name of LIVE_EVENTS) {
      source.addEventListener(name, notify(name));
    }
    source.addEventListener("message", () => this.setState("open"));
  }

  private setState(state: ConnectionState) {
    if (this.state === state) return;
    this.state = state;
    for (const listener of this.stateListeners) listener(state);
  }
}

export const liveConnection = new LiveConnection();
