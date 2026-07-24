import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceStoryDto } from "@/types/devices";
import {
  HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
  liveConnection,
} from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import { DeviceStorySection } from "./DeviceStorySection";

const storyA: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0xa1",
  status: "review_first",
  priority: "high",
  headline_code: "current_issue_present",
  reasons: [{ code: "current_issue_present", params: {} }],
  evidence: [
    {
      source: "topology_snapshot",
      id: "snapshot-a",
      captured_at: "2026-07-23T01:00:00+00:00",
      label: null,
    },
  ],
  limitations: [{ code: "absence_from_latest_not_failure", params: {} }],
  suggested_checks: [{ code: "confirm_powered", params: {} }],
  coverage: [
    {
      dimension: "route_hints",
      state: "not_observed",
      label_code: "route_hints_unavailable",
      params: {},
    },
  ],
  timeline: [],
};

const storyB: DeviceStoryDto = {
  ...storyA,
  subject_id: "0xb2",
  status: "watch",
  priority: "medium",
  headline_code: "stale_last_seen",
  reasons: [{ code: "last_seen_stale", params: {} }],
  evidence: [],
  limitations: [],
  suggested_checks: [],
  coverage: [],
};

const lateStory: DeviceStoryDto = {
  ...storyA,
  headline_code: "low_battery",
  reasons: [{ code: "battery_low", params: { battery_percent: 12 } }],
};

const deviceStory = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      deviceStory,
    },
  };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function emitRefresh(eventName = HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT) {
  act(() => {
    eventSourceTestState.emit(eventName, { type: eventName });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
  await flushAsyncWork();
}

const staleStoryCopy =
  "Device story could not be refreshed. Showing the last accepted view; it may not include the newest Core data or Home Assistant enrichment.";

describe("DeviceStorySection refresh state ownership", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    deviceStory.mockReset();
    liveConnection.resetForTests();
    eventSourceTestState.reset();
    liveConnection.setAccessEnabled(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders initial loading, initial failure, and initial success distinctly", async () => {
    const initial = deferred<DeviceStoryDto>();
    deviceStory.mockReturnValueOnce(initial.promise);

    const first = render(
      <DeviceStorySection networkId="home" deviceIeee="0xa1" />,
    );
    expect(screen.getByText("Loading device story…")).toBeInTheDocument();
    expect(screen.queryByText(/unavailable right now/i)).not.toBeInTheDocument();

    await act(async () => {
      initial.reject(new Error("initial story failure"));
      await Promise.resolve();
    });
    expect(
      screen.getByText(
        "Device story is unavailable right now. Other device details still reflect stored evidence.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry device story" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(staleStoryCopy)).not.toBeInTheDocument();
    first.unmount();

    deviceStory.mockResolvedValueOnce(storyA);
    render(<DeviceStorySection networkId="home" deviceIeee="0xa1" />);
    await flushAsyncWork();
    expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();
    expect(screen.queryByText(/unavailable right now/i)).not.toBeInTheDocument();
  });

  it("passes scenario to api.deviceStory", async () => {
    deviceStory.mockResolvedValue(storyA);
    render(
      <DeviceStorySection
        networkId="home"
        deviceIeee="0xa1"
        scenario="offline_cluster"
      />,
    );
    await flushAsyncWork();
    expect(deviceStory).toHaveBeenCalledWith(
      "home",
      "0xa1",
      "offline_cluster",
    );
  });

  it("retains accepted story evidence while refreshing and across repeated failures, then replaces it after a successful retry", async () => {
    const refresh = deferred<DeviceStoryDto>();
    deviceStory
      .mockResolvedValueOnce(storyA)
      .mockReturnValueOnce(refresh.promise)
      .mockRejectedValueOnce(new Error("repeated story failure"))
      .mockResolvedValueOnce(storyB);

    render(<DeviceStorySection networkId="home" deviceIeee="0xa1" />);
    await flushAsyncWork();

    await emitRefresh();
    const section = screen.getByTestId("device-story-section");
    expect(section).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();
    expect(screen.getByText(/currently needs attention/i)).toBeInTheDocument();
    expect(
      screen.getByText(/absence from the latest snapshot does not prove/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Confirm the device is powered.")).toBeInTheDocument();
    expect(screen.getByText("Route hints unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/Latest stored topology snapshot/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(staleStoryCopy)).not.toBeInTheDocument();

    await act(async () => {
      refresh.reject(new Error("story refresh failure"));
      await Promise.resolve();
    });
    expect(section).toHaveAttribute("aria-busy", "false");
    expect(screen.getByText(staleStoryCopy)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(staleStoryCopy);
    expect(
      screen.getByRole("button", { name: "Retry device story" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();
    expect(screen.getByText(/currently needs attention/i)).toBeInTheDocument();
    expect(
      screen.getByText(/absence from the latest snapshot does not prove/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Confirm the device is powered.")).toBeInTheDocument();
    expect(screen.getByText("Route hints unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/Latest stored topology snapshot/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/unavailable right now/i)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry device story" }),
    );
    await flushAsyncWork();
    expect(screen.getByText(staleStoryCopy)).toBeInTheDocument();
    expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry device story" }),
    );
    await flushAsyncWork();
    expect(screen.getByText("Last seen looks stale")).toBeInTheDocument();
    expect(
      screen.queryByText("Current issue needs attention"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(staleStoryCopy)).not.toBeInTheDocument();
  });

  it("retains the accepted story after an ordinary Dashboard refresh failure", async () => {
    deviceStory
      .mockResolvedValueOnce(storyA)
      .mockRejectedValueOnce(new Error("Dashboard story failure"));

    render(<DeviceStorySection networkId="home" deviceIeee="0xa1" />);
    await flushAsyncWork();
    await emitRefresh("dashboard_updated");

    expect(deviceStory).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();
    expect(screen.getByText(staleStoryCopy)).toBeInTheDocument();
    expect(screen.queryByText(/unavailable right now/i)).not.toBeInTheDocument();
  });

  it.each([
    {
      boundary: "network",
      next: { networkId: "other", deviceIeee: "0xa1", scenario: "scenario_a" },
    },
    {
      boundary: "device",
      next: { networkId: "home", deviceIeee: "0xb2", scenario: "scenario_a" },
    },
    {
      boundary: "scenario",
      next: { networkId: "home", deviceIeee: "0xa1", scenario: "scenario_b" },
    },
  ])(
    "masks accepted and stale story immediately across a $boundary identity change",
    async ({ next }) => {
      const nextStory = deferred<DeviceStoryDto>();
      deviceStory
        .mockResolvedValueOnce(storyA)
        .mockRejectedValueOnce(new Error("old identity refresh failure"))
        .mockReturnValueOnce(nextStory.promise);

      const { rerender } = render(
        <DeviceStorySection
          networkId="home"
          deviceIeee="0xa1"
          scenario="scenario_a"
        />,
      );
      await flushAsyncWork();
      await emitRefresh();
      expect(screen.getByText(staleStoryCopy)).toBeInTheDocument();

      rerender(<DeviceStorySection {...next} />);
      expect(screen.getByText("Loading device story…")).toBeInTheDocument();
      expect(
        screen.queryByText("Current issue needs attention"),
      ).not.toBeInTheDocument();
      expect(screen.queryByText(staleStoryCopy)).not.toBeInTheDocument();

      await act(async () => {
        nextStory.resolve(storyB);
        await Promise.resolve();
      });
      expect(screen.getByText("Last seen looks stale")).toBeInTheDocument();
      expect(
        screen.queryByText("Current issue needs attention"),
      ).not.toBeInTheDocument();
    },
  );

  it("does not let an obsolete in-flight result restore an old story after identity change", async () => {
    const oldRefresh = deferred<DeviceStoryDto>();
    const newIdentity = deferred<DeviceStoryDto>();
    deviceStory
      .mockResolvedValueOnce(storyA)
      .mockReturnValueOnce(oldRefresh.promise)
      .mockReturnValueOnce(newIdentity.promise);

    const { rerender } = render(
      <DeviceStorySection networkId="home" deviceIeee="0xa1" />,
    );
    await flushAsyncWork();
    await emitRefresh();
    expect(screen.getByTestId("device-story-section")).toHaveAttribute(
      "aria-busy",
      "true",
    );

    rerender(<DeviceStorySection networkId="home" deviceIeee="0xb2" />);
    expect(screen.getByText("Loading device story…")).toBeInTheDocument();
    expect(
      screen.queryByText("Current issue needs attention"),
    ).not.toBeInTheDocument();

    await act(async () => {
      oldRefresh.resolve(lateStory);
      await Promise.resolve();
    });
    expect(
      screen.queryByText("Battery reported low"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Loading device story…")).toBeInTheDocument();

    await act(async () => {
      newIdentity.resolve(storyB);
      await Promise.resolve();
    });
    expect(screen.getByText("Last seen looks stale")).toBeInTheDocument();
    expect(
      screen.queryByText("Battery reported low"),
    ).not.toBeInTheDocument();
  });
});
