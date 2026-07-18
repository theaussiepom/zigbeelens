import { eventStreamUrl, fetchSessionStatus } from "@/lib/api";
import { authRuntime } from "@/lib/authRuntime";

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
 *
 * Connections are created only while access is enabled (authenticated UI).
 */
class LiveConnection {
  private source: EventSource | null = null;
  private eventListeners = new Set<EventListener>();
  private stateListeners = new Set<StateListener>();
  private state: ConnectionState = "connecting";
  private refCount = 0;
  private accessEnabled = false;
  private statusProbeAt = 0;
  private statusProbeTimer: ReturnType<typeof setTimeout> | null = null;

  getState(): ConnectionState {
    return this.state;
  }

  isAccessEnabled(): boolean {
    return this.accessEnabled;
  }

  setAccessEnabled(enabled: boolean): void {
    this.accessEnabled = enabled;
    if (!enabled) {
      this.closeSource();
      if (this.statusProbeTimer) {
        clearTimeout(this.statusProbeTimer);
        this.statusProbeTimer = null;
      }
      this.setState("disconnected");
      return;
    }
    if (this.refCount > 0 && !this.source) {
      this.connect();
    }
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

  /** Test helper */
  resetForTests(): void {
    this.closeSource();
    this.eventListeners.clear();
    this.stateListeners.clear();
    this.refCount = 0;
    this.accessEnabled = false;
    this.statusProbeAt = 0;
    if (this.statusProbeTimer) {
      clearTimeout(this.statusProbeTimer);
      this.statusProbeTimer = null;
    }
    this.state = "connecting";
  }

  private ensureConnected() {
    this.refCount += 1;
    if (!this.accessEnabled) return;
    if (this.source) return;
    this.connect();
  }

  private maybeDisconnect() {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount === 0 && this.source) {
      this.closeSource();
      this.setState("connecting");
    }
  }

  private closeSource() {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
  }

  private connect() {
    if (!this.accessEnabled) return;
    this.setState("connecting");
    let source: EventSource;
    try {
      source = new EventSource(eventStreamUrl(), { withCredentials: true });
    } catch {
      this.setState("disconnected");
      return;
    }
    this.source = source;

    source.onopen = () => this.setState("open");
    source.onerror = () => {
      this.setState("disconnected");
      this.scheduleStatusProbe();
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

  private scheduleStatusProbe() {
    if (!this.accessEnabled) return;
    const now = Date.now();
    if (now - this.statusProbeAt < 5_000) return;
    if (this.statusProbeTimer) return;
    this.statusProbeTimer = setTimeout(() => {
      this.statusProbeTimer = null;
      this.statusProbeAt = Date.now();
      void this.probeSessionOnce();
    }, 400);
  }

  private async probeSessionOnce() {
    if (!this.accessEnabled) return;
    try {
      const status = await fetchSessionStatus();
      if (!status.authenticated) {
        authRuntime.notifyUnauthorized();
      }
    } catch {
      // Network failure — keep disconnected/retry behavior; do not treat as auth loss.
    }
  }

  private setState(state: ConnectionState) {
    if (this.state === state) return;
    this.state = state;
    for (const listener of this.stateListeners) listener(state);
  }
}

export const liveConnection = new LiveConnection();
