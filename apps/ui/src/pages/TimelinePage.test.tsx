import { act, fireEvent, render, screen } from "@testing-library/react";
import { useLayoutEffect } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
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

const TIMELINE_STALE_COPY =
  "Timeline could not be refreshed. Showing the last accepted view; it may not include the newest Core data or Home Assistant enrichment.";

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

function timelineElement() {
  return (
    <MemoryRouter>
      <TimelinePage />
    </MemoryRouter>
  );
}

function renderTimeline() {
  return render(timelineElement());
}

function TimelineRouteNavigationHarness({
  onRouteCommit,
}: {
  onRouteCommit: (oldRowVisible: boolean) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  useLayoutEffect(() => {
    if (
      new URLSearchParams(location.search).get("network") === "other"
    ) {
      onRouteCommit(
        document.body.textContent?.includes("Route home row") ?? false,
      );
    }
  }, [location.search, onRouteCommit]);
  return (
    <>
      <button
        type="button"
        onClick={() => navigate("/timeline?network=other")}
      >
        Navigate to other network
      </button>
      <TimelinePage />
    </>
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

  it("retains filtered rows through background and repeated errors, then replaces them after Retry", async () => {
    let rejectRefresh: ((reason?: unknown) => void) | undefined;
    apiMocks.timeline
      .mockResolvedValueOnce({
        items: [
          timelineEvent("Accepted Timeline row"),
          timelineEvent("Unmatched incident", {
            id: "unmatched-incident",
            kind: "incident_opened",
            severity: "incident",
          }),
        ],
        total: 2,
      })
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectRefresh = reject;
          }),
      )
      .mockRejectedValueOnce(new Error("repeated Timeline refresh failure"))
      .mockResolvedValueOnce({
        items: [timelineEvent("Refreshed Timeline row")],
        total: 1,
      });

    renderTimeline();
    await flushAsyncWork();
    fireEvent.change(screen.getByLabelText("Event type"), {
      target: { value: "device_payload_seen" },
    });
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "Timeline" },
    });
    expect(screen.getByText("Accepted Timeline row")).toBeInTheDocument();
    expect(screen.queryByText("Unmatched incident")).not.toBeInTheDocument();

    await emitLiveEvent("dashboard_updated");

    const page = screen
      .getByRole("heading", { name: "Timeline" })
      .closest("[aria-busy]");
    expect(page).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Accepted Timeline row")).toBeInTheDocument();
    expect(screen.getByLabelText("Event type")).toHaveValue(
      "device_payload_seen",
    );
    expect(screen.getByLabelText("Search")).toHaveValue("Timeline");

    await act(async () => {
      rejectRefresh?.(new Error("injected Timeline background failure"));
      await Promise.resolve();
    });

    expect(page).toHaveAttribute("aria-busy", "false");
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry Timeline" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Accepted Timeline row")).toBeInTheDocument();
    expect(screen.queryByText("No timeline events")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry Timeline" }));
    await flushAsyncWork();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(3);
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();
    expect(screen.getByText("Accepted Timeline row")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry Timeline" }));
    await flushAsyncWork();
    expect(apiMocks.timeline).toHaveBeenCalledTimes(4);
    expect(screen.getByText("Refreshed Timeline row")).toBeInTheDocument();
    expect(screen.queryByText("Accepted Timeline row")).not.toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();
    expect(page).toHaveAttribute("aria-busy", "false");
    expect(screen.getByLabelText("Event type")).toHaveValue(
      "device_payload_seen",
    );
    expect(screen.getByLabelText("Search")).toHaveValue("Timeline");
  });

  it("keeps an accepted empty Timeline distinct from an unavailable Timeline", async () => {
    apiMocks.timeline
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockRejectedValueOnce(new Error("empty Timeline refresh failure"));

    renderTimeline();
    await flushAsyncWork();
    expect(screen.getByText("No timeline events")).toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();

    await emitLiveEvent("dashboard_updated");

    expect(screen.getByText("No timeline events")).toBeInTheDocument();
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry Timeline" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/empty Timeline refresh failure/i),
    ).not.toBeInTheDocument();
  });

  it("discards stale accepted Timeline rows immediately when network scope changes", async () => {
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
      .mockRejectedValueOnce(new Error("home Timeline refresh failure"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOther = resolve;
          }),
      );

    renderTimeline();
    await flushAsyncWork();
    expect(screen.getByText("Home scope row")).toBeInTheDocument();

    await emitLiveEvent("dashboard_updated");
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();
    expect(screen.getByText("Home scope row")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Network"), {
      target: { value: "other" },
    });
    expect(screen.queryByText("Home scope row")).not.toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();
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

  it("masks stale rows on the render that changes the route network", async () => {
    const routeCommitSnapshots: boolean[] = [];
    const observeRouteCommit = (oldRowVisible: boolean) => {
      routeCommitSnapshots.push(oldRowVisible);
    };
    let resolveOther:
      | ((value: { items: TimelineEvent[]; total: number }) => void)
      | undefined;
    apiMocks.timeline
      .mockResolvedValueOnce({
        items: [timelineEvent("Route home row")],
        total: 1,
      })
      .mockRejectedValueOnce(new Error("route home refresh failure"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOther = resolve;
          }),
      );

    render(
      <MemoryRouter initialEntries={["/timeline?network=home"]}>
        <Routes>
          <Route
            path="/timeline"
            element={
              <TimelineRouteNavigationHarness
                onRouteCommit={observeRouteCommit}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    await flushAsyncWork();
    await emitLiveEvent("dashboard_updated");
    expect(screen.getByText("Route home row")).toBeInTheDocument();
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Navigate to other network" }),
    );

    expect(routeCommitSnapshots).toEqual([false]);
    expect(screen.queryByText("Route home row")).not.toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();
    expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

    await act(async () => {
      resolveOther?.({
        items: [
          timelineEvent("Route other row", {
            id: "route-other",
            network_id: "other",
          }),
        ],
        total: 1,
      });
      await Promise.resolve();
    });

    expect(screen.getByText("Route other row")).toBeInTheDocument();
    expect(screen.queryByText("Route home row")).not.toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenLastCalledWith(undefined, "other");
  });

  it("discards stale accepted Timeline rows immediately when scenario scope changes", async () => {
    let resolveScenario:
      | ((value: { items: TimelineEvent[]; total: number }) => void)
      | undefined;
    apiMocks.timeline
      .mockResolvedValueOnce({
        items: [timelineEvent("Scenario A row")],
        total: 1,
      })
      .mockRejectedValueOnce(new Error("scenario A Timeline refresh failure"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveScenario = resolve;
          }),
      );

    const timeline = renderTimeline();
    await flushAsyncWork();
    await emitLiveEvent("dashboard_updated");
    expect(screen.getByText("Scenario A row")).toBeInTheDocument();
    expect(screen.getByText(TIMELINE_STALE_COPY)).toBeInTheDocument();

    scenarioState.scenario = "scenario-b";
    timeline.rerender(timelineElement());
    expect(screen.queryByText("Scenario A row")).not.toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();
    expect(screen.getByText("Loading ZigbeeLens…")).toBeInTheDocument();

    await act(async () => {
      resolveScenario?.({
        items: [timelineEvent("Scenario B row")],
        total: 1,
      });
      await Promise.resolve();
    });

    expect(screen.getByText("Scenario B row")).toBeInTheDocument();
    expect(screen.queryByText("Scenario A row")).not.toBeInTheDocument();
    expect(apiMocks.timeline).toHaveBeenLastCalledWith(
      "scenario-b",
      undefined,
    );
  });

  it("uses a full error only when no Timeline has been accepted", async () => {
    apiMocks.timeline.mockRejectedValueOnce(
      new Error("injected Timeline initial failure"),
    );

    renderTimeline();
    await flushAsyncWork();

    expect(
      screen.getByText(/injected Timeline initial failure/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry Timeline" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_STALE_COPY)).not.toBeInTheDocument();
    expect(screen.queryByText("No timeline events")).not.toBeInTheDocument();
  });
});
