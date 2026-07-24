import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { authRuntime } from "@/lib/authRuntime";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { DeviceDetailPage } from "@/pages/DevicesPage";

const CORE_URL = process.env.ZIGBEELENS_E2E_CORE_URL ?? "";
const HA_CONTROL_URL = process.env.ZIGBEELENS_E2E_HA_CONTROL_URL ?? "";
const IEEE = "0x00124b0024abcd01";
const DEVICE_PATH = `/api/devices/home/${IEEE}`;
const DEVICE_STORY_PATH = `${DEVICE_PATH}/story`;
const INCIDENTS_PATH = "/api/incidents";
const SNAPSHOT_HISTORY_PATH =
  `/api/topology/home/devices/${IEEE}/snapshot-history`;

type Listener = EventListenerOrEventListenerObject;

const networkState = {
  rawEvents: new Map<string, number>(),
  deliveredEvents: new Map<string, number>(),
  droppedEvents: new Map<string, number>(),
  dropNextEvents: new Map<string, number>(),
  openCount: 0,
  lastError: "",
};

function dropNextNetworkEvent(eventName: string): void {
  networkState.dropNextEvents.set(
    eventName,
    (networkState.dropNextEvents.get(eventName) ?? 0) + 1,
  );
}

class NetworkEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  readonly url: string;
  readonly withCredentials: boolean;
  readyState = NetworkEventSource.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  private readonly listeners = new Map<string, Set<Listener>>();
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private closed = false;

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(init?.withCredentials);
    void this.connect();
  }

  addEventListener(type: string, listener: Listener | null): void {
    if (!listener) return;
    const listeners = this.listeners.get(type) ?? new Set<Listener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: Listener | null): void {
    if (!listener) return;
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.closed = true;
    this.readyState = NetworkEventSource.CLOSED;
    void this.reader?.cancel();
    this.reader = null;
  }

  private dispatch(type: string, data: string): void {
    const event = new MessageEvent(type, { data });
    if (type === "message") this.onmessage?.(event);
    for (const listener of this.listeners.get(type) ?? []) {
      if (typeof listener === "function") {
        listener(event);
      } else {
        listener.handleEvent(event);
      }
    }
  }

  private consumeBlock(block: string): void {
    let type = "message";
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) type = line.slice(6).trimStart();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) return;
    networkState.rawEvents.set(type, (networkState.rawEvents.get(type) ?? 0) + 1);
    const remainingDrops = networkState.dropNextEvents.get(type) ?? 0;
    if (remainingDrops > 0) {
      networkState.droppedEvents.set(
        type,
        (networkState.droppedEvents.get(type) ?? 0) + 1,
      );
      if (remainingDrops === 1) {
        networkState.dropNextEvents.delete(type);
      } else {
        networkState.dropNextEvents.set(type, remainingDrops - 1);
      }
      return;
    }
    networkState.deliveredEvents.set(
      type,
      (networkState.deliveredEvents.get(type) ?? 0) + 1,
    );
    this.dispatch(type, data.join("\n"));
  }

  private async connect(): Promise<void> {
    try {
      const response = await fetch(this.url, {
        headers: { Accept: "text/event-stream" },
      });
      if (!response.ok || !response.body) {
        throw new Error(`SSE request failed (${response.status})`);
      }
      this.readyState = NetworkEventSource.OPEN;
      networkState.openCount += 1;
      this.onopen?.(new Event("open"));
      const reader = response.body.getReader();
      this.reader = reader;
      const decoder = new TextDecoder();
      let buffered = "";
      while (!this.closed) {
        const result = await reader.read();
        buffered += decoder.decode(result.value, { stream: !result.done });
        const blocks = buffered.split(/\r?\n\r?\n/);
        buffered = blocks.pop() ?? "";
        for (const block of blocks) this.consumeBlock(block);
        if (result.done) break;
      }
      this.reader = null;
    } catch (error) {
      if (!this.closed) {
        networkState.lastError =
          error instanceof Error ? error.message : String(error);
        this.readyState = NetworkEventSource.CLOSED;
        this.onerror?.(new Event("error"));
      }
    }
  }
}

const originalEventSource = globalThis.EventSource;
const originalFetch = globalThis.fetch;
let detailFetches = 0;
let deviceStoryFetches = 0;
let incidentFetches = 0;
let snapshotHistoryFetches = 0;

async function applyHomeAssistantState(state: string): Promise<{
  ha_device_id: string;
}> {
  const response = await originalFetch(`${HA_CONTROL_URL}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  });
  if (!response.ok) {
    throw new Error(`HA control failed (${response.status}): ${await response.text()}`);
  }
  return (await response.json()) as { ha_device_id: string };
}

function identityRow(label: string): HTMLElement {
  const term = screen.getByText(label);
  const row = term.closest("div");
  if (!row) throw new Error(`Missing identity row: ${label}`);
  return row;
}

describe("Home Assistant enrichment live production path", () => {
  beforeAll(() => {
    if (!CORE_URL || !HA_CONTROL_URL) {
      throw new Error(
        "ZIGBEELENS_E2E_CORE_URL and ZIGBEELENS_E2E_HA_CONTROL_URL are required",
      );
    }
    networkState.rawEvents.clear();
    networkState.deliveredEvents.clear();
    networkState.droppedEvents.clear();
    networkState.dropNextEvents.clear();
    networkState.openCount = 0;
    networkState.lastError = "";
    detailFetches = 0;
    deviceStoryFetches = 0;
    incidentFetches = 0;
    snapshotHistoryFetches = 0;
    globalThis.EventSource = NetworkEventSource as unknown as typeof EventSource;
    globalThis.fetch = async (input, init) => {
      const request = input instanceof Request ? input : new Request(input, init);
      const url = new URL(request.url);
      if (request.method === "GET" && url.pathname === DEVICE_PATH) {
        detailFetches += 1;
      }
      if (request.method === "GET" && url.pathname === DEVICE_STORY_PATH) {
        deviceStoryFetches += 1;
      }
      if (request.method === "GET" && url.pathname === INCIDENTS_PATH) {
        incidentFetches += 1;
      }
      if (request.method === "GET" && url.pathname === SNAPSHOT_HISTORY_PATH) {
        snapshotHistoryFetches += 1;
      }
      return originalFetch(input, init);
    };
  });

  afterAll(() => {
    liveConnection.resetForTests();
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
  });

  it(
    "keeps one mounted device page converged when one exact event is lost",
    async () => {
      const initial = await applyHomeAssistantState("initial");

      localStorage.clear();
      authRuntime.setTrustedLocal(false);
      liveConnection.setAccessEnabled(true);
      render(
        <MemoryRouter initialEntries={[`/devices/home/${IEEE}`]}>
          <ScenarioProvider>
            <Routes>
              <Route
                path="/devices/:networkId/:ieeeAddress"
                element={<DeviceDetailPage />}
              />
            </Routes>
          </ScenarioProvider>
        </MemoryRouter>,
      );

      await screen.findByRole("heading", { level: 1, name: "HA Kitchen Lamp" });
      expect(within(identityRow("Home Assistant area")).getByText("Kitchen")).toBeVisible();
      await screen.findByText(
        "No earlier usable topology snapshots are available for this device yet.",
      );
      await waitFor(() => {
        expect(networkState.lastError).toBe("");
        expect(networkState.openCount).toBe(1);
      });
      expect(detailFetches).toBe(1);
      expect(deviceStoryFetches).toBe(1);
      expect(incidentFetches).toBe(1);
      expect(snapshotHistoryFetches).toBe(1);
      expect(networkState.rawEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT) ?? 0).toBe(
        0,
      );
      expect(networkState.rawEvents.get("dashboard_updated") ?? 0).toBe(0);

      // Simulate the bounded broadcaster/network loss mode without synthesizing
      // an event: the real Core companion still traverses production
      // LiveConnection and must refresh enrichment-owning resources.
      dropNextNetworkEvent(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
      const renamed = await applyHomeAssistantState("renamed");
      expect(renamed.ha_device_id).toBe(initial.ha_device_id);
      await screen.findByRole("heading", { level: 1, name: "HA Study Lamp" });
      expect(within(identityRow("Home Assistant area")).getByText("Study")).toBeVisible();
      await waitFor(() => {
        expect(networkState.rawEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT)).toBe(1);
        expect(networkState.rawEvents.get("dashboard_updated")).toBe(1);
      });
      expect(
        networkState.deliveredEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT) ?? 0,
      ).toBe(0);
      expect(
        networkState.droppedEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT),
      ).toBe(1);
      expect(networkState.deliveredEvents.get("dashboard_updated")).toBe(1);
      expect(detailFetches).toBe(2);
      expect(deviceStoryFetches).toBe(2);
      expect(incidentFetches).toBe(1);
      expect(snapshotHistoryFetches).toBe(1);

      const removed = await applyHomeAssistantState("removed");
      expect(removed.ha_device_id).toBe(initial.ha_device_id);
      await screen.findByRole("heading", { level: 1, name: "source-lamp" });
      await waitFor(() => {
        expect(screen.queryByText("Home Assistant name")).not.toBeInTheDocument();
        expect(screen.queryByText("Home Assistant area")).not.toBeInTheDocument();
      });
      await waitFor(() => {
        expect(networkState.rawEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT)).toBe(2);
        expect(networkState.rawEvents.get("dashboard_updated")).toBe(2);
      });
      expect(
        networkState.deliveredEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT),
      ).toBe(1);
      expect(
        networkState.droppedEvents.get(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT),
      ).toBe(1);
      expect(networkState.deliveredEvents.get("dashboard_updated")).toBe(2);
      expect(detailFetches).toBe(3);
      expect(deviceStoryFetches).toBe(3);
      expect(incidentFetches).toBe(1);
      expect(snapshotHistoryFetches).toBe(1);
    },
    30_000,
  );
});
