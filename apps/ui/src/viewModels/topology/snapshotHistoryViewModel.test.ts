import { describe, expect, it } from "vitest";
import type {
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
} from "@/types/devices";
import type { TopologyDeviceFactsDto } from "@/types/decisions";
import { formatTime, relativeTime } from "@/lib/format";
import {
  buildSnapshotHistoryViewModel,
  defaultSelectedSnapshotId,
} from "@/viewModels/topology/snapshotHistoryViewModel";

const emptyTopologyFacts: TopologyDeviceFactsDto = {
  stale_threshold_hours: null,
  device_facts: [],
  comparison_facts_by_snapshot_id: {},
};

const worthReviewingReasons = [
  "Latest snapshot shows no links for this device.",
  "The selected snapshot showed 6 links.",
  "This device currently needs attention.",
];

function makeRow(overrides: Partial<DeviceSnapshotHistoryRow>): DeviceSnapshotHistoryRow {
  return {
    snapshot_id: "snap-prev",
    captured_at: "2026-07-05T19:10:00+00:00",
    is_latest: false,
    is_usable: true,
    links_for_device_count: 6,
    route_hints_for_device_count: 2,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: {
      status: "worth_reviewing",
      reasons: worthReviewingReasons,
      suggested_checks: [
        "Confirm the device is powered.",
        "Check whether it is reporting in Zigbee2MQTT.",
      ],
      link_counts: {
        latest_count: 0,
        selected_count: 6,
        latest_only_count: 0,
        selected_only_count: 6,
        changed_count: 0,
      },
      route_hint_counts: {
        latest_count: 0,
        selected_count: 2,
        latest_only_count: 0,
        selected_only_count: 2,
        changed_count: 0,
      },
    },
    ...overrides,
  };
}

const worthReviewingDetail: DeviceSnapshotHistoryDetail = {
  network_id: "home",
  device_ieee: "0xr1",
  friendly_name: "Live Hall Router",
  has_current_issue: true,
  availability_tracking: {
    enabled: true,
    earliest_observation_at: "2026-07-01T00:00:00+00:00",
  },
  latest_snapshot: makeRow({
    snapshot_id: "snap-live",
    captured_at: "2026-07-06T00:30:00+00:00",
    is_latest: true,
    links_for_device_count: 0,
    route_hints_for_device_count: 0,
    availability_state_near_snapshot: "offline",
    comparison_to_latest: null,
  }),
  snapshots: [
    makeRow({ snapshot_id: "snap-prev" }),
    makeRow({
      snapshot_id: "snap-older",
      captured_at: "2026-07-03T09:03:00+00:00",
      links_for_device_count: 8,
      route_hints_for_device_count: 3,
      comparison_to_latest: {
        status: "changed",
        reasons: ["8 links only in the selected snapshot."],
        suggested_checks: [],
        link_counts: {
          latest_count: 0,
          selected_count: 8,
          latest_only_count: 0,
          selected_only_count: 8,
          changed_count: 0,
        },
        route_hint_counts: {
          latest_count: 0,
          selected_count: 3,
          latest_only_count: 0,
          selected_only_count: 3,
          changed_count: 0,
        },
      },
    }),
    makeRow({
      snapshot_id: "snap-oldest",
      captured_at: "2026-06-28T10:00:00+00:00",
      links_for_device_count: 7,
      route_hints_for_device_count: 0,
      availability_coverage_status: "building",
      availability_state_near_snapshot: null,
      comparison_to_latest: {
        status: "no_notable_change",
        reasons: ["Similar number of links shown."],
        suggested_checks: [],
        link_counts: {
          latest_count: 0,
          selected_count: 7,
          latest_only_count: 0,
          selected_only_count: 7,
          changed_count: 0,
        },
        route_hint_counts: {
          latest_count: 0,
          selected_count: 0,
          latest_only_count: 0,
          selected_only_count: 0,
          changed_count: 0,
        },
      },
    }),
  ],
  topology_facts: emptyTopologyFacts,
};

describe("snapshotHistoryViewModel", () => {
  it("defaults selection to the previous usable snapshot", () => {
    expect(defaultSelectedSnapshotId(worthReviewingDetail)).toBe("snap-prev");
  });

  it("maps row status labels through decision copy", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-prev");
    expect(vm.rows[0].statusLabel).toBe("Worth reviewing");
    expect(vm.rows[1].statusLabel).toBe("Changed");
    expect(vm.rows[2].statusLabel).toBe("Similar");
  });

  it("builds worth-reviewing comparison card from selected row", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-prev");
    expect(vm.comparison?.statusLabel).toBe("Worth reviewing");
    expect(vm.comparison?.statusLead).toContain("device-level changes");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
    expect(vm.comparison?.suggestedChecks).toContain("Confirm the device is powered.");
    expect(vm.comparison?.evidenceDetails.showSelectedOnlyNote).toBe(true);
  });

  it("retains complete backend comparison reasons when topology facts also exist", () => {
    const detail: DeviceSnapshotHistoryDetail = {
      ...worthReviewingDetail,
      topology_facts: {
        stale_threshold_hours: null,
        device_facts: [
          { code: "device_no_latest_links", params: { device_ieee: "0xr1" } },
        ],
        comparison_facts_by_snapshot_id: {
          "snap-prev": [
            {
              code: "device_has_selected_snapshot_links",
              params: {
                device_ieee: "0xr1",
                snapshot_id: "snap-prev",
                link_count: 6,
              },
            },
            {
              code: "device_latest_vs_selected_changed",
              params: {
                device_ieee: "0xr1",
                snapshot_id: "snap-prev",
                comparison_status: "worth_reviewing",
              },
            },
          ],
        },
      },
    };
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
  });

  it("does not let comparison facts for another snapshot affect the selected comparison", () => {
    const detail: DeviceSnapshotHistoryDetail = {
      ...worthReviewingDetail,
      topology_facts: {
        stale_threshold_hours: null,
        device_facts: [],
        comparison_facts_by_snapshot_id: {
          "snap-older": [
            {
              code: "device_has_selected_snapshot_links",
              params: {
                device_ieee: "0xr1",
                snapshot_id: "snap-older",
                link_count: 8,
              },
            },
          ],
        },
      },
    };
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
    expect(vm.comparison?.statusLabel).toBe("Worth reviewing");
  });

  it("updates comparison when a different snapshot is selected", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-older");
    expect(vm.rows[1].selected).toBe(true);
    expect(vm.comparison?.statusLabel).toBe("Changed");
    expect(vm.comparison?.statusLead).toContain("nothing here stands out");
    expect(vm.comparison?.reasons).toEqual(["8 links only in the selected snapshot."]);
  });

  it("shows tracking-off banner when availability reporting is disabled", () => {
    const detail: DeviceSnapshotHistoryDetail = {
      ...worthReviewingDetail,
      availability_tracking: { enabled: false, earliest_observation_at: null },
      latest_snapshot: makeRow({
        snapshot_id: "snap-live",
        captured_at: "2026-07-06T00:30:00+00:00",
        is_latest: true,
        links_for_device_count: 0,
        route_hints_for_device_count: 0,
        availability_coverage_status: "off",
        availability_state_near_snapshot: null,
        comparison_to_latest: null,
      }),
      snapshots: [
        makeRow({
          snapshot_id: "snap-prev",
          availability_coverage_status: "off",
          availability_state_near_snapshot: null,
        }),
      ],
    };
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.trackingOffBanner?.label).toBe("Availability tracking off");
    expect(vm.selectedCoverageBanner).toBeNull();
    expect(vm.latest?.summaryText).not.toContain("Online");
    expect(vm.latest?.summaryText).not.toContain("Offline");
  });

  it("shows building coverage banner for selected snapshot with limited history", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-oldest");
    expect(vm.selectedCoverageBanner?.label).toBe("Availability history building");
    expect(vm.rows[2].coveragePill?.label).toBe("Availability history building");
  });

  it("shows unknown coverage banner for selected snapshot with unknown coverage", () => {
    const detail: DeviceSnapshotHistoryDetail = {
      ...worthReviewingDetail,
      snapshots: [
        makeRow({
          snapshot_id: "snap-unknown",
          availability_coverage_status: "unknown",
          availability_state_near_snapshot: null,
        }),
      ],
    };
    const vm = buildSnapshotHistoryViewModel(detail, "snap-unknown");
    expect(vm.selectedCoverageBanner?.label).toBe("Availability status unknown");
    expect(vm.rows[0].coveragePill?.label).toBe("Availability status unknown");
    expect(vm.rows[0].availabilityStateText).toBeNull();
  });

  it("builds latest snapshot display model with relative label, summary and title", () => {
    const latest = worthReviewingDetail.latest_snapshot!;
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-prev");
    expect(vm.latest).not.toBeNull();
    expect(vm.latest?.relativeLabel).toBe(relativeTime(latest.captured_at ?? undefined));
    expect(vm.latest?.summaryText).toBe("0 links shown · no route hints · Offline");
    expect(vm.latest?.capturedAtTitle).toBe(formatTime(latest.captured_at ?? undefined));
  });

  it("exposes empty state copy when no earlier snapshots exist", () => {
    const detail: DeviceSnapshotHistoryDetail = {
      ...worthReviewingDetail,
      snapshots: [],
    };
    const vm = buildSnapshotHistoryViewModel(detail, null);
    expect(vm.rows).toHaveLength(0);
    expect(vm.comparison).toBeNull();
    expect(vm.emptyCopy).toContain("No earlier usable topology snapshots");
  });
});
