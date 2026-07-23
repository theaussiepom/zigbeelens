import { eventStreamUrl } from "@/lib/api";

export type ConnectionState = "connecting" | "open" | "disconnected";

export const HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT =
  "home_assistant_enrichment_updated" as const;

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
  "topology_updated",
  "timeline_updated",
  "reports_updated",
  "storage_maintenance_completed",
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
] as const;

export type SessionProbeReason = "sse_error";

type SessionProbeRequester = (reason: SessionProbeReason) => void;
type EventListener = (eventName: string) => void;
type StateListener = (state: ConnectionState) => void;

/**
 * Single shared EventSource connection to Core.
 * Connections are created only while access is enabled (authenticated UI).
 *
 * Does not fetch /api/auth/session. On errors it requests a bounded status
 * probe from BrowserAuthProvider via setSessionProbeRequester.
 */
class LiveConnection {
  private source: EventSource | null = null;
  private eventListeners = new Set<EventListener>();
  private stateListeners = new Set<StateListener>();
  private state: ConnectionState = "connecting";
  private refCount = 0;
  private accessEnabled = false;
  private statusProbesSuppressed = false;
  private statusProbeAt = 0;
  private statusProbeTimer: ReturnType<typeof setTimeout> | null = null;
  private sessionProbeRequester: SessionProbeRequester | null = null;
  private probeSource: EventSource | null = null;

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
      this.clearPendingSessionProbe();
      this.setState("disconnected");
      return;
    }
    if (this.refCount > 0 && !this.source) {
      this.connect();
    }
  }

  /** While true, EventSource errors do not request session-status probes (e.g. during logout). */
  setStatusProbesSuppressed(suppressed: boolean): void {
    this.statusProbesSuppressed = suppressed;
    if (suppressed) {
      this.clearPendingSessionProbe();
    }
  }

  /** Provider-owned callback for SSE-driven session probes. */
  setSessionProbeRequester(requester: SessionProbeRequester | null): void {
    this.sessionProbeRequester = requester;
  }

  clearPendingSessionProbe(): void {
    if (this.statusProbeTimer) {
      clearTimeout(this.statusProbeTimer);
      this.statusProbeTimer = null;
    }
    this.probeSource = null;
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

  resetForTests(): void {
    this.closeSource();
    this.eventListeners.clear();
    this.stateListeners.clear();
    this.refCount = 0;
    this.accessEnabled = false;
    this.statusProbesSuppressed = false;
    this.statusProbeAt = 0;
    this.sessionProbeRequester = null;
    this.clearPendingSessionProbe();
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

    source.onopen = () => {
      if (!this.accessEnabled || this.source !== source) return;
      this.setState("open");
    };
    source.onerror = () => {
      if (!this.accessEnabled || this.source !== source) return;
      this.setState("disconnected");
      this.scheduleStatusProbe(source);
    };

    const notify = (eventName: string) => () => {
      if (!this.accessEnabled || this.source !== source) return;
      this.setState("open");
      for (const listener of this.eventListeners) listener(eventName);
    };

    for (const name of LIVE_EVENTS) {
      source.addEventListener(name, notify(name));
    }
    source.addEventListener("message", () => {
      if (!this.accessEnabled || this.source !== source) return;
      this.setState("open");
    });
  }

  private scheduleStatusProbe(source: EventSource) {
    if (!this.accessEnabled || this.statusProbesSuppressed) return;
    if (!this.sessionProbeRequester) return;
    const now = Date.now();
    if (now - this.statusProbeAt < 5_000) return;
    if (this.statusProbeTimer) return;
    this.probeSource = source;
    this.statusProbeTimer = setTimeout(() => {
      this.statusProbeTimer = null;
      this.statusProbeAt = Date.now();
      const requester = this.sessionProbeRequester;
      const owned = this.probeSource;
      this.probeSource = null;
      if (!requester) return;
      if (!this.accessEnabled || this.statusProbesSuppressed) return;
      if (this.source !== owned) return;
      requester("sse_error");
    }, 400);
  }

  private setState(state: ConnectionState) {
    if (this.state === state) return;
    this.state = state;
    for (const listener of this.stateListeners) listener(state);
  }
}

export const liveConnection = new LiveConnection();
