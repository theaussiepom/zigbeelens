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
    max_snapshots: 30,
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
    expect(viewModel.recentMissingLinks.helper).toMatch(/could not be evaluated/i);
    expect(viewModel.lastKnownLinks.state).toBe("not_evaluated");
    expect(viewModel.lastKnownLinks.helper).not.toMatch(/every device/i);
  });

  it("qualifies both controls when the latest layout is limited", () => {
    const viewModel = buildConnectionHistoryPresentationViewModel(
      makeTopologyEvidenceGraphDetail({
        nodes: [{ ieee_address: "0x1" }],
        latest_layout_limited: true,
        ...evaluatedWindows,
      }),
    );

    expect(viewModel.recentMissingLinks.state).toBe("layout_limited");
    expect(viewModel.recentMissingLinks.helper).toMatch(/cannot be measured reliably/i);
    expect(viewModel.lastKnownLinks.state).toBe("layout_limited");
    expect(viewModel.lastKnownLinks.helper).toMatch(/cannot be assessed/i);
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
