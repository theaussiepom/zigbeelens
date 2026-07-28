import { describe, expect, it } from "vitest";
import type {
  DeviceSnapshotHistoryLimitedRow,
  DeviceSnapshotHistoryDetail,
  DeviceSnapshotHistoryRow,
} from "@/types/devices";
import type { TopologyDeviceFactsDto } from "@/types/decisions";
import { parseDeviceSnapshotHistoryDetail } from "@/lib/deviceSnapshotHistoryContract";
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
    layout_state: "available",
    is_usable: true,
    device_present_in_snapshot: true,
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
      device_presence: {
        latest: true,
        selected: true,
        changed: false,
      },
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

function makeLimitedRow(
  overrides: Partial<DeviceSnapshotHistoryLimitedRow> = {},
): DeviceSnapshotHistoryLimitedRow {
  return {
    snapshot_id: "snap-limited",
    captured_at: "2026-07-04T19:10:00+00:00",
    is_latest: false,
    layout_state: "limited",
    is_usable: false,
    device_present_in_snapshot: null,
    links_for_device_count: null,
    route_hints_for_device_count: null,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: null,
    ...overrides,
  };
}

function withExactTopologyFacts(
  detail: DeviceSnapshotHistoryDetail,
): DeviceSnapshotHistoryDetail {
  const deviceFacts: TopologyDeviceFactsDto["device_facts"] = [];
  const latest = detail.latest_snapshot;
  if (latest?.layout_state === "available") {
    deviceFacts.push({
      code: latest.device_present_in_snapshot
        ? "device_seen_in_latest_snapshot"
        : "device_absent_from_latest_snapshot",
      params: {
        device_ieee: detail.device_ieee,
        snapshot_id: latest.snapshot_id,
      },
    });
    if (latest.links_for_device_count > 0) {
      deviceFacts.push({
        code: "device_has_latest_links",
        params: {
          device_ieee: detail.device_ieee,
          link_count: latest.links_for_device_count,
        },
      });
    } else {
      deviceFacts.push({
        code: "device_no_latest_links",
        params: { device_ieee: detail.device_ieee },
      });
    }
  }

  const comparisonFacts: TopologyDeviceFactsDto["comparison_facts_by_snapshot_id"] =
    {};
  for (const row of detail.snapshots) {
    const comparison = row.comparison_to_latest;
    if (row.layout_state !== "available" || comparison === null) continue;
    const facts: TopologyDeviceFactsDto["comparison_facts_by_snapshot_id"][string] =
      [];
    if (row.links_for_device_count > 0) {
      facts.push({
        code: "device_has_selected_snapshot_links",
        params: {
          device_ieee: detail.device_ieee,
          snapshot_id: row.snapshot_id,
          link_count: row.links_for_device_count,
        },
      });
    }
    if (comparison.status !== "no_notable_change") {
      facts.push({
        code: "device_latest_vs_selected_changed",
        params: {
          device_ieee: detail.device_ieee,
          comparison_status: comparison.status,
          snapshot_id: row.snapshot_id,
          latest_device_present_in_snapshot:
            comparison.device_presence.latest,
          selected_device_present_in_snapshot:
            comparison.device_presence.selected,
          device_presence_changed: comparison.device_presence.changed,
        },
      });
    }
    if (
      row.availability_coverage_status === "off" ||
      row.availability_coverage_status === "building" ||
      row.availability_coverage_status === "unknown"
    ) {
      facts.push({
        code: "availability_coverage_affects_snapshot_comparison",
        params: {
          device_ieee: detail.device_ieee,
          availability_coverage_status: row.availability_coverage_status,
          snapshot_id: row.snapshot_id,
        },
      });
    }
    if (facts.length > 0) comparisonFacts[row.snapshot_id] = facts;
  }

  return parseDeviceSnapshotHistoryDetail({
    ...detail,
    topology_facts: {
      stale_threshold_hours: detail.topology_facts.stale_threshold_hours,
      device_facts: deviceFacts,
      comparison_facts_by_snapshot_id: comparisonFacts,
    },
  });
}

const worthReviewingDetail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
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
        status: "worth_reviewing",
        reasons: [
          "8 links only in the selected snapshot.",
          "This device currently needs attention.",
        ],
        suggested_checks: [],
        device_presence: {
          latest: true,
          selected: true,
          changed: false,
        },
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
      links_for_device_count: 0,
      route_hints_for_device_count: 0,
      availability_coverage_status: "building",
      availability_state_near_snapshot: null,
      comparison_to_latest: {
        status: "no_notable_change",
        reasons: ["Similar number of links shown."],
        suggested_checks: [],
        device_presence: {
          latest: true,
          selected: true,
          changed: false,
        },
        link_counts: {
          latest_count: 0,
          selected_count: 0,
          latest_only_count: 0,
          selected_only_count: 0,
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
});

describe("snapshotHistoryViewModel", () => {
  it("defaults selection to the previous usable snapshot", () => {
    expect(defaultSelectedSnapshotId(worthReviewingDetail)).toBe("snap-prev");
  });

  it("maps row status labels through decision copy", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-prev");
    expect(vm.rows[0].statusLabel).toBe("Worth reviewing");
    expect(vm.rows[1].statusLabel).toBe("Worth reviewing");
    expect(vm.rows[2].statusLabel).toBe("Similar");
  });

  it("builds worth-reviewing comparison card from selected row", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-prev");
    expect(vm.comparison?.statusLabel).toBe("Worth reviewing");
    expect(vm.comparison?.statusLead).toContain("device-level changes");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
    expect(vm.comparison?.suggestedChecks).toContain("Confirm the device is powered.");
    expect(vm.comparison?.evidenceDetails.showSelectedOnlyNote).toBe(true);
    expect(vm.comparison?.evidenceDetails.presenceLines).toEqual([
      "Device observed in the latest snapshot",
      "Device observed in the selected snapshot",
    ]);
  });

  it("retains complete backend comparison reasons when topology facts also exist", () => {
    const detail = worthReviewingDetail;
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
  });

  it("does not let comparison facts for another snapshot affect the selected comparison", () => {
    const detail = worthReviewingDetail;
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.comparison?.reasons).toEqual(worthReviewingReasons);
    expect(vm.comparison?.statusLabel).toBe("Worth reviewing");
  });

  it("updates comparison when a different snapshot is selected", () => {
    const vm = buildSnapshotHistoryViewModel(worthReviewingDetail, "snap-older");
    expect(vm.rows[1].selected).toBe(true);
    expect(vm.comparison?.statusLabel).toBe("Worth reviewing");
    expect(vm.comparison?.statusLead).toContain("device-level changes");
    expect(vm.comparison?.reasons).toEqual([
      "8 links only in the selected snapshot.",
      "This device currently needs attention.",
    ]);
  });

  it("shows tracking-off banner when availability reporting is disabled", () => {
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
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
    });
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
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      snapshots: [
        makeRow({
          snapshot_id: "snap-unknown",
          availability_coverage_status: "unknown",
          availability_state_near_snapshot: null,
        }),
      ],
    });
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
    expect(vm.latest?.summaryText).toBe(
      "Device observed in this snapshot · 0 links shown · no route hints · Offline",
    );
    expect(vm.latest?.capturedAtTitle).toBe(formatTime(latest.captured_at ?? undefined));
  });

  it("preserves factual available zero and factual device absence as measured values", () => {
    const present = buildSnapshotHistoryViewModel(worthReviewingDetail, null);
    expect(present.latest?.summaryText).toContain("Device observed in this snapshot");
    expect(present.latest?.summaryText).toContain("0 links shown");
    expect(present.latest?.summaryText).toContain("no route hints");

    const absentDetail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      latest_snapshot: makeRow({
        snapshot_id: "snap-live",
        is_latest: true,
        device_present_in_snapshot: false,
        links_for_device_count: 0,
        route_hints_for_device_count: 0,
        comparison_to_latest: null,
      }),
      snapshots: [],
    });
    const absent = buildSnapshotHistoryViewModel(absentDetail, null);
    expect(absent.latest?.summaryText).toContain(
      "Device not observed in this snapshot",
    );
    expect(absent.latest?.summaryText).toContain("0 links shown");
  });

  it("presents limited latest layout as unavailable without zero or comparison status", () => {
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      latest_snapshot: makeLimitedRow({
        snapshot_id: "snap-live-limited",
        captured_at: "2026-07-06T00:30:00+00:00",
        is_latest: true,
        availability_state_near_snapshot: "offline",
      }),
      snapshots: [
        makeRow({
          snapshot_id: "snap-prev",
          comparison_to_latest: null,
        }),
      ],
    });
    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.latest?.summaryText).toBe("Topology layout unavailable · Offline");
    expect(vm.latest?.summaryText).not.toMatch(/\b0\b|no route hints/i);
    expect(vm.rows[0]?.statusLabel).toBeNull();
    expect(vm.comparison).toBeNull();
    expect(vm.comparisonUnavailableCopy).toMatch(
      /latest topology layout is unavailable/i,
    );
  });

  it("keeps a limited earlier row selectable but defaults to the first comparable row", () => {
    const comparable = makeRow({
      snapshot_id: "snap-comparable",
      comparison_to_latest: {
        status: "worth_reviewing",
        reasons: ["Similar number of links shown."],
        suggested_checks: [],
        device_presence: {
          latest: true,
          selected: true,
          changed: false,
        },
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
    });
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      snapshots: [makeLimitedRow(), comparable],
    });
    expect(defaultSelectedSnapshotId(detail)).toBe("snap-comparable");

    const limited = buildSnapshotHistoryViewModel(detail, "snap-limited");
    expect(limited.rows[0]?.countsText).toBe("Topology layout unavailable");
    expect(limited.rows[0]?.statusLabel).toBeNull();
    expect(limited.comparison).toBeNull();
    expect(limited.comparisonUnavailableCopy).toMatch(
      /selected topology layout is unavailable/i,
    );
  });

  it("presents both measured presence values for a presence-only change", () => {
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      has_current_issue: false,
      latest_snapshot: makeRow({
        snapshot_id: "snap-live",
        is_latest: true,
        device_present_in_snapshot: false,
        links_for_device_count: 0,
        route_hints_for_device_count: 0,
        comparison_to_latest: null,
      }),
      snapshots: [
        makeRow({
          snapshot_id: "snap-prev",
          links_for_device_count: 0,
          route_hints_for_device_count: 0,
          comparison_to_latest: {
            status: "changed",
            reasons: [
              "The device was observed in the selected snapshot but not the latest snapshot.",
            ],
            suggested_checks: [],
            device_presence: {
              latest: false,
              selected: true,
              changed: true,
            },
            link_counts: {
              latest_count: 0,
              selected_count: 0,
              latest_only_count: 0,
              selected_only_count: 0,
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
    });

    const vm = buildSnapshotHistoryViewModel(detail, "snap-prev");
    expect(vm.comparison?.statusLabel).toBe("Changed");
    expect(vm.comparison?.evidenceDetails.presenceLines).toEqual([
      "Device not observed in the latest snapshot",
      "Device observed in the selected snapshot",
    ]);
  });

  it("exposes empty state copy when no earlier snapshots exist", () => {
    const detail: DeviceSnapshotHistoryDetail = withExactTopologyFacts({
      ...worthReviewingDetail,
      snapshots: [],
    });
    const vm = buildSnapshotHistoryViewModel(detail, null);
    expect(vm.rows).toHaveLength(0);
    expect(vm.comparison).toBeNull();
    expect(vm.emptyCopy).toContain("No earlier complete topology captures");
  });
});
