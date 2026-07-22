import { describe, expect, it } from "vitest";
import type {
  HistoricalEdgeAggregate,
  LastKnownLinkAggregate,
} from "@/types/topology";
import { makeTopologyEvidenceGraphDetail } from "@/test/topologyEvidenceGraphFixture";
import { buildConnectionHistoryPresentationViewModel } from "./connectionHistoryPresentationViewModel";

const historicalLink: HistoricalEdgeAggregate = {
  source_ieee: "0x1",
  target_ieee: "0x2",
  evidence_class: "historical_neighbor",
  directional: false,
  not_seen_in_latest_snapshot: true,
  latest_layout_limited: false,
  confidence: "medium",
  limitations: [],
};

const lastKnownLink: LastKnownLinkAggregate = {
  source_ieee: "0x1",
  target_ieee: "0x3",
  evidence_class: "last_known_link",
  directional: false,
  last_reported_at: "2026-07-05T00:00:00Z",
  last_snapshot_id: "snap-previous",
  not_seen_in_latest_snapshot: true,
  confidence: "low",
  limitations: [],
};

const evaluatedWindows = {
  history_window: {
    days: 7,
    max_snapshots: 3,
    snapshots_considered: 3,
    earliest_captured_at: "2026-07-01T00:00:00Z",
    latest_captured_at: "2026-07-05T00:00:00Z",
  },
  last_known_window: {
    snapshots_considered: 3,
    earliest_captured_at: "2026-07-01T00:00:00Z",
    latest_captured_at: "2026-07-05T00:00:00Z",
  },
};

describe("buildConnectionHistoryPresentationViewModel", () => {
  it("keeps missing history distinct from an evaluated empty result", () => {
    const viewModel = buildConnectionHistoryPresentationViewModel(
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        inventory: { device_count: 2, router_count: 0, end_device_count: 1 },
      }),
    );

    expect(viewModel.recentMissingLinks.state).toBe("not_evaluated");
    expect(viewModel.recentMissingLinks.helper).toBe(
      "No previous complete snapshots are available in the selected 7-day history window, so recent missing links could not be evaluated.",
    );
    expect(viewModel.lastKnownLinks.state).toBe("not_evaluated");
    expect(viewModel.lastKnownLinks.helper).not.toMatch(/every device/i);
  });

  it.each([1, 13])(
    "uses the DTO's %i-day selected window without changing last-known wording",
    (days) => {
      const viewModel = buildConnectionHistoryPresentationViewModel(
        makeTopologyEvidenceGraphDetail({
          nodes: [{ ieee_address: "0x1" }],
          inventory: { device_count: 1, router_count: 0, end_device_count: 0 },
          history_window: {
            days,
            max_snapshots: 3,
            snapshots_considered: 0,
            earliest_captured_at: null,
            latest_captured_at: null,
          },
        }),
      );

      expect(viewModel.recentMissingLinks.helper).toBe(
        `No previous complete snapshots are available in the selected ${days}-day history window, so recent missing links could not be evaluated.`,
      );
      expect(viewModel.lastKnownLinks.helper).toBe(
        "No previous complete snapshots are available, so last known links could not be evaluated.",
      );
    },
  );

  it("uses exact Core precedence when the latest layout is limited with no history", () => {
    const viewModel = buildConnectionHistoryPresentationViewModel(
      makeTopologyEvidenceGraphDetail({
        nodes: [],
        links: [],
        layout_available: false,
        latest_layout_limited: true,
      }),
    );

    // Recent-missing aggregation had no previous snapshots to examine, so it
    // remains unmeasured. Core separately skips last-known evaluation because
    // absence cannot be assessed against a limited latest layout.
    expect(viewModel.recentMissingLinks.state).toBe("not_evaluated");
    expect(viewModel.recentMissingLinks.helper).toMatch(/no previous complete snapshots/i);
    expect(viewModel.lastKnownLinks.state).toBe("layout_limited");
    expect(viewModel.lastKnownLinks.helper).toMatch(/cannot be assessed/i);
    expect(viewModel.lastKnownLinks.helper).not.toMatch(/no previous complete snapshots/i);
  });

  it("describes measured empty history only after snapshots were considered", () => {
    const viewModel = buildConnectionHistoryPresentationViewModel(
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        ...evaluatedWindows,
      }),
    );

    expect(viewModel.recentMissingLinks.state).toBe("evaluated_empty");
    expect(viewModel.recentMissingLinks.helper).toMatch(/no recent missing links were measured/i);
    expect(viewModel.lastKnownLinks.state).toBe("evaluated_empty");
    expect(viewModel.lastKnownLinks.helper).toMatch(/no last known link qualified/i);
  });

  it("reports positive recent-missing and last-known evidence counts", () => {
    const viewModel = buildConnectionHistoryPresentationViewModel(
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        historical_neighbors: [historicalLink],
        last_known_links: [lastKnownLink],
        ...evaluatedWindows,
      }),
    );

    expect(viewModel.recentMissingLinks).toMatchObject({ state: "available", evidenceCount: 1 });
    expect(viewModel.recentMissingLinks.helper).toMatch(/1 recent missing link is available/i);
    expect(viewModel.lastKnownLinks).toMatchObject({ state: "available", evidenceCount: 1 });
    expect(viewModel.lastKnownLinks.helper).toMatch(/1 last known link is available/i);
  });
});
