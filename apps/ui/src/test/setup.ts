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

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(init?.withCredentials);
    eventSourceTestState.constructs.push({
      url: this.url,
      withCredentials: this.withCredentials,
    });
    eventSourceTestState.instances.push(this);
  }

  addEventListener() {}
  removeEventListener() {}
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
