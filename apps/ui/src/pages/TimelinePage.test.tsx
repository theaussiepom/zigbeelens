import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TimelineEvent } from "@zigbeelens/shared";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { TimelinePage } from "@/pages/TimelinePage";

const apiMocks = vi.hoisted(() => ({
  timeline: vi.fn(),
}));

const scenarioState = vi.hoisted(() => ({
  scenario: "",
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      timeline: apiMocks.timeline,
    },
  };
});

vi.mock("@/context/ScenarioContext", () => ({
  useScenario: () => ({
    scenario: scenarioState.scenario,
  }),
}));

function timelineEvent(
  title: string,
  overrides: Partial<TimelineEvent> = {},
): TimelineEvent {
  return {
    id: title.toLowerCase().replace(/\s+/g, "-"),
    timestamp: "2026-07-24T05:00:00+00:00",
    kind: "device_payload_seen",
    severity: "healthy",
    network_id: "home",
    title,
    summary: "Stored normalized MQTT event.",
    ...overrides,
  };
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function emitLiveEvent(
  eventName: string,
  payload: Record<string, unknown> = { type: eventName },
) {
  act(() => {
    eventSourceTestState.emit(eventName, payload);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

function renderTimeline() {
  return render(
    <MemoryRouter>
      <TimelinePage />
    </MemoryRouter>,
  );
}

describe("TimelinePage live ownership", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    apiMocks.timeline.mockReset();
    scenarioState.scenario = "";
    liveConnection.resetForTests();
    eventSourceTestState.reset();
    liveConnection.setAccessEnabled(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows an ingested row after an ordinary Dashboard invalidation and ignores enrichment companions", async () => {
    apiMocks.timeline
      .mockResolvedValueOnce({
        items: [timelineEvent("Existing MQTT row")],
        total: 1,
      })
      .mockResolvedValueOnce({
        items: [timelineEvent("New MQTT row")],
        total: 1,
      })
      .mockResolvedValueOnce({
        items: [timelineEvent("Health-attributed row")],
        total: 1,
      })
      .mockResolvedValueOnce({
        items: [timelineEvent("Fallback row")],
        total: 1,
      });

    renderTimeline();
    await flushAsyncWork();
    expect(screen.getByText("Existing MQTT row")).toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(1);

    await emitLiveEvent(HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT);
    expect(apiMocks.timeline).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    await emitLiveEvent("dashboard_updated", {
      type: "dashboard_updated",
      causes: [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT],
    });
    expect(apiMocks.timeline).toHaveBeenCalledTimes(1);

    await emitLiveEvent("dashboard_updated");
    expect(screen.getByText("New MQTT row")).toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(2);

    await emitLiveEvent("dashboard_updated", {
      type: "dashboard_updated",
      causes: ["health_updated"],
    });
    expect(screen.getByText("Health-attributed row")).toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(3);

    await emitLiveEvent("dashboard_updated");
    expect(screen.getByText("Fallback row")).toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(4);
  });

  it("discards accepted Timeline rows immediately when network scope changes", async () => {
    let resolveOther:
      | ((value: { items: TimelineEvent[]; total: number }) => void)
      | undefined;
    apiMocks.timeline
      .mockResolvedValueOnce({
        items: [
          timelineEvent("Home scope row"),
          timelineEvent("Other option row", {
            id: "other-option",
            network_id: "other",
          }),
        ],
        total: 2,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOther = resolve;
          }),
      );

    renderTimeline();
    await flushAsyncWork();
    expect(screen.getByText("Home scope row")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Network"), {
      target: { value: "other" },
    });
    expect(screen.queryByText("Home scope row")).not.toBeInTheDocument();
    expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

    await act(async () => {
      resolveOther?.({
        items: [
          timelineEvent("Other scope row", {
            id: "other-scope",
            network_id: "other",
          }),
        ],
        total: 1,
      });
      await Promise.resolve();
    });

    expect(screen.getByText("Other scope row")).toBeInTheDocument();
    expect(screen.queryByText("Home scope row")).not.toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenLastCalledWith(undefined, "other");
  });

  it("keeps an initial request failure distinct from an accepted empty Timeline", async () => {
    apiMocks.timeline.mockRejectedValueOnce(
      new Error("injected Timeline initial failure"),
    );

    renderTimeline();
    await flushAsyncWork();

    expect(
      screen.getByText(/injected Timeline initial failure/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("No timeline events")).not.toBeInTheDocument();
  });
});
