import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { authRuntime } from "@/lib/authRuntime";
import { liveConnection } from "@/lib/events";
import { resetSessionTransportForTests } from "@/lib/sessionTransport";

export type EventSourceConstruct = {
  url: string;
  withCredentials: boolean;
};

export const eventSourceTestState = {
  constructs: [] as EventSourceConstruct[],
  closeCount: 0,
  instances: [] as StubEventSource[],
  emit(eventName: string, data?: unknown) {
    this.instances.at(-1)?.emit(eventName, data);
  },
  reset() {
    this.constructs = [];
    this.closeCount = 0;
    this.instances = [];
  },
};

// jsdom does not implement EventSource; capture URL / withCredentials / close.
class StubEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = StubEventSource.CONNECTING;
  url: string;
  withCredentials: boolean;
  private listeners = new Map<string, Set<EventListenerOrEventListenerObject>>();

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(init?.withCredentials);
    eventSourceTestState.constructs.push({
      url: this.url,
      withCredentials: this.withCredentials,
    });
    eventSourceTestState.instances.push(this);
  }

  addEventListener(eventName: string, listener: EventListenerOrEventListenerObject | null) {
    if (!listener) return;
    const listeners = this.listeners.get(eventName) ?? new Set();
    listeners.add(listener);
    this.listeners.set(eventName, listeners);
  }
  removeEventListener(eventName: string, listener: EventListenerOrEventListenerObject | null) {
    if (!listener) return;
    this.listeners.get(eventName)?.delete(listener);
  }
  registeredEventNames(): string[] {
    return [...this.listeners.keys()];
  }
  emit(eventName: string, data?: unknown) {
    const event = new MessageEvent(eventName, {
      data: data === undefined ? "" : JSON.stringify(data),
    });
    for (const listener of this.listeners.get(eventName) ?? []) {
      if (typeof listener === "function") {
        listener(event);
      } else {
        listener.handleEvent(event);
      }
    }
  }
  close() {
    this.readyState = StubEventSource.CLOSED;
    eventSourceTestState.closeCount += 1;
  }
}

// @ts-expect-error - assigning a minimal stub for jsdom
globalThis.EventSource = StubEventSource;

afterEach(() => {
  cleanup();
  authRuntime.resetForTests();
  resetSessionTransportForTests();
  liveConnection.resetForTests();
  eventSourceTestState.reset();
});
