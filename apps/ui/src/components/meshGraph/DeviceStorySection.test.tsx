import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { DeviceStoryDto } from "@/types/devices";
import { DeviceStorySection } from "./DeviceStorySection";

const storyA: DeviceStoryDto = {
  subject_type: "device",
  subject_id: "0xa1",
  status: "review_first",
  priority: "high",
  headline_code: "current_issue_present",
  reasons: [{ code: "current_issue_present", params: {} }],
  evidence: [],
  limitations: [],
  suggested_checks: [],
  coverage: [],
  timeline: [],
};

const storyB: DeviceStoryDto = {
  ...storyA,
  status: "watch",
  priority: "medium",
  headline_code: "stale_last_seen",
  reasons: [{ code: "last_seen_stale", params: {} }],
};

const deviceStory = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  api: {
    deviceStory,
  },
}));

describe("DeviceStorySection scenario propagation", () => {
  beforeEach(() => {
    deviceStory.mockReset();
    deviceStory.mockResolvedValue(storyA);
  });

  it("passes scenario to api.deviceStory", async () => {
    render(
      <DeviceStorySection
        networkId="home"
        deviceIeee="0xa1"
        scenario="offline_cluster"
      />,
    );
    await waitFor(() => {
      expect(deviceStory).toHaveBeenCalledWith("home", "0xa1", "offline_cluster");
    });
  });

  it("resets story and refetches when scenario changes", async () => {
    deviceStory.mockImplementation(async (_n: string, _i: string, scenario?: string) => {
      if (scenario === "scenario_b") {
        await new Promise((resolve) => setTimeout(resolve, 30));
        return storyB;
      }
      return storyA;
    });

    const { rerender } = render(
      <DeviceStorySection networkId="home" deviceIeee="0xa1" scenario="scenario_a" />,
    );
    await waitFor(() => {
      expect(screen.getByText("Current issue needs attention")).toBeInTheDocument();
    });
    expect(deviceStory).toHaveBeenCalledWith("home", "0xa1", "scenario_a");

    rerender(
      <DeviceStorySection networkId="home" deviceIeee="0xa1" scenario="scenario_b" />,
    );
    await waitFor(() => {
      expect(screen.getByText("Loading device story…")).toBeInTheDocument();
    });
    expect(screen.queryByText("Current issue needs attention")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Last seen looks stale")).toBeInTheDocument();
    });
    expect(deviceStory).toHaveBeenCalledWith("home", "0xa1", "scenario_b");
  });
});
