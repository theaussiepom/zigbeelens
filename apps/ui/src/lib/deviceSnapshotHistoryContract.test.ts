import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { parseDeviceSnapshotHistoryDetail } from "@/lib/deviceSnapshotHistoryContract";

function comparison() {
  return {
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
  };
}

function availableRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    snapshot_id: "snap-latest",
    captured_at: "2026-07-13T02:00:00Z",
    is_latest: true,
    layout_state: "available",
    is_usable: true,
    device_present_in_snapshot: true,
    links_for_device_count: 0,
    route_hints_for_device_count: 0,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: "online",
    comparison_to_latest: null,
    ...overrides,
  };
}

function limitedRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    snapshot_id: "snap-limited",
    captured_at: "2026-07-12T02:00:00Z",
    is_latest: false,
    layout_state: "limited",
    is_usable: false,
    device_present_in_snapshot: null,
    links_for_device_count: null,
    route_hints_for_device_count: null,
    availability_coverage_status: "tracked",
    availability_state_near_snapshot: null,
    comparison_to_latest: null,
    ...overrides,
  };
}

function detail(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    network_id: "home",
    device_ieee: "0xabc",
    friendly_name: "Sensor",
    has_current_issue: false,
    availability_tracking: {
      enabled: true,
      earliest_observation_at: "2026-07-01T00:00:00Z",
    },
    latest_snapshot: availableRow(),
    snapshots: [limitedRow()],
    topology_facts: {
      stale_threshold_hours: 24,
      device_facts: [
        {
          code: "device_seen_in_latest_snapshot",
          params: {
            device_ieee: "0xabc",
            snapshot_id: "snap-latest",
          },
        },
        {
          code: "device_no_latest_links",
          params: {
            device_ieee: "0xabc",
          },
        },
      ],
      comparison_facts_by_snapshot_id: {},
    },
    ...overrides,
  };
}

function changedTopologyFacts(
  latest: boolean,
  selected: boolean,
  status: "changed" | "watch" | "worth_reviewing" = "changed",
): Record<string, unknown> {
  return {
    stale_threshold_hours: 24,
    device_facts: [
      {
        code: latest
          ? "device_seen_in_latest_snapshot"
          : "device_absent_from_latest_snapshot",
        params: {
          device_ieee: "0xabc",
          snapshot_id: "snap-latest",
        },
      },
      {
        code: "device_no_latest_links",
        params: {
          device_ieee: "0xabc",
        },
      },
    ],
    comparison_facts_by_snapshot_id: {
      "snap-earlier": [
        {
          code: "device_latest_vs_selected_changed",
          params: {
            device_ieee: "0xabc",
            comparison_status: status,
            snapshot_id: "snap-earlier",
            latest_device_present_in_snapshot: latest,
            selected_device_present_in_snapshot: selected,
            device_presence_changed: true,
          },
        },
      ],
    },
  };
}

function expectProtocolFailure(value: unknown): void {
  try {
    parseDeviceSnapshotHistoryDetail(value);
    throw new Error("expected parser to reject malformed value");
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "protocol", detail: "malformed" });
  }
}

describe("device snapshot-history runtime contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("preserves factual available zero and null limited evidence", () => {
    const parsed = parseDeviceSnapshotHistoryDetail(detail());
    expect(parsed.latest_snapshot).toMatchObject({
      layout_state: "available",
      is_usable: true,
      device_present_in_snapshot: true,
      links_for_device_count: 0,
      route_hints_for_device_count: 0,
    });
    expect(parsed.snapshots[0]).toEqual(
      expect.objectContaining({
        layout_state: "limited",
        is_usable: false,
        device_present_in_snapshot: null,
        links_for_device_count: null,
        route_hints_for_device_count: null,
        comparison_to_latest: null,
      }),
    );
  });

  it.each([
    ["is_usable", true],
    ["device_present_in_snapshot", false],
    ["links_for_device_count", 0],
    ["route_hints_for_device_count", 0],
    ["comparison_to_latest", comparison()],
  ])("rejects limited layout with legacy or inferred %s=%j", (field, value) => {
    expectProtocolFailure(
      detail({
        snapshots: [limitedRow({ [field]: value })],
      }),
    );
  });

  it.each([
    ["is_usable", false],
    ["device_present_in_snapshot", null],
    ["links_for_device_count", null],
    ["route_hints_for_device_count", null],
    ["links_for_device_count", -1],
    ["route_hints_for_device_count", 1.5],
  ])("rejects malformed available %s=%j", (field, value) => {
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({ [field]: value }),
      }),
    );
  });

  it("rejects positive counts when an available row says the device was absent", () => {
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({
          device_present_in_snapshot: false,
          links_for_device_count: 1,
        }),
      }),
    );
  });

  it("requires comparison exactly when both latest and earlier layouts are available", () => {
    expectProtocolFailure(
      detail({
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: null,
          }),
        ],
      }),
    );

    const parsed = parseDeviceSnapshotHistoryDetail(
      detail({
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: comparison(),
          }),
        ],
      }),
    );
    expect(parsed.snapshots[0]?.comparison_to_latest?.status).toBe(
      "no_notable_change",
    );
  });

  it.each([
    [false, true],
    [true, false],
  ])(
    "accepts a presence-only comparison from latest=%j to selected=%j",
    (latestPresent, selectedPresent) => {
      const presenceComparison = {
        ...comparison(),
        status: "changed",
        reasons: [
          latestPresent
            ? "The device was observed in the latest snapshot but not the selected snapshot."
            : "The device was observed in the selected snapshot but not the latest snapshot.",
        ],
        device_presence: {
          latest: latestPresent,
          selected: selectedPresent,
          changed: true,
        },
      };
      const parsed = parseDeviceSnapshotHistoryDetail(
        detail({
          latest_snapshot: availableRow({
            device_present_in_snapshot: latestPresent,
          }),
          snapshots: [
            availableRow({
              snapshot_id: "snap-earlier",
              is_latest: false,
              device_present_in_snapshot: selectedPresent,
              comparison_to_latest: presenceComparison,
            }),
          ],
          topology_facts: changedTopologyFacts(
            latestPresent,
            selectedPresent,
          ),
        }),
      );
      expect(parsed.snapshots[0]?.comparison_to_latest?.device_presence).toEqual(
        presenceComparison.device_presence,
      );
    },
  );

  it("rejects a false changed flag when the presence values differ", () => {
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({
          device_present_in_snapshot: false,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: {
              ...comparison(),
              status: "changed",
              device_presence: {
                latest: false,
                selected: true,
                changed: false,
              },
            },
          }),
        ],
      }),
    );
  });

  it("rejects presence values that contradict their snapshot rows", () => {
    expectProtocolFailure(
      detail({
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: {
              ...comparison(),
              status: "changed",
              device_presence: {
                latest: false,
                selected: true,
                changed: true,
              },
            },
          }),
        ],
      }),
    );
  });

  it("rejects no-notable and watch statuses for a presence-only difference", () => {
    for (const status of ["no_notable_change", "watch"]) {
      expectProtocolFailure(
        detail({
          latest_snapshot: availableRow({
            device_present_in_snapshot: false,
          }),
          snapshots: [
            availableRow({
              snapshot_id: "snap-earlier",
              is_latest: false,
              comparison_to_latest: {
                ...comparison(),
                status,
                device_presence: {
                  latest: false,
                  selected: true,
                  changed: true,
                },
              },
            }),
          ],
        }),
      );
    }
  });

  it("requires worth-reviewing when presence changes with a current issue", () => {
    expectProtocolFailure(
      detail({
        has_current_issue: true,
        latest_snapshot: availableRow({
          device_present_in_snapshot: false,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: {
              ...comparison(),
              status: "changed",
              device_presence: {
                latest: false,
                selected: true,
                changed: true,
              },
            },
          }),
        ],
      }),
    );
  });

  it("accepts worth-reviewing when presence changes with a current issue", () => {
    const parsed = parseDeviceSnapshotHistoryDetail(
      detail({
        has_current_issue: true,
        latest_snapshot: availableRow({
          device_present_in_snapshot: false,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            device_present_in_snapshot: true,
            comparison_to_latest: {
              ...comparison(),
              status: "worth_reviewing",
              device_presence: {
                latest: false,
                selected: true,
                changed: true,
              },
            },
          }),
        ],
        topology_facts: changedTopologyFacts(
          false,
          true,
          "worth_reviewing",
        ),
      }),
    );

    expect(parsed.snapshots[0]?.comparison_to_latest?.status).toBe(
      "worth_reviewing",
    );
  });

  it("enforces current-issue-plus-change for link-only differences", () => {
    const linkDifference = {
      ...comparison(),
      status: "changed",
      link_counts: {
        latest_count: 1,
        selected_count: 0,
        latest_only_count: 1,
        selected_only_count: 0,
        changed_count: 0,
      },
    };
    expectProtocolFailure(
      detail({
        has_current_issue: true,
        latest_snapshot: availableRow({
          links_for_device_count: 1,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: linkDifference,
          }),
        ],
      }),
    );
    expectProtocolFailure(
      detail({
        latest_snapshot: availableRow({
          links_for_device_count: 1,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: {
              ...linkDifference,
              status: "worth_reviewing",
            },
          }),
        ],
      }),
    );
  });

  it("rejects omitted nullable fields instead of inferring null", () => {
    for (const field of ["friendly_name", "latest_snapshot", "topology_facts"]) {
      const malformed = detail();
      delete malformed[field];
      expectProtocolFailure(malformed);
    }

    const missingTrackingField = detail();
    delete (
      missingTrackingField.availability_tracking as Record<string, unknown>
    ).earliest_observation_at;
    expectProtocolFailure(missingTrackingField);

    for (const field of [
      "captured_at",
      "availability_state_near_snapshot",
      "device_present_in_snapshot",
      "links_for_device_count",
      "route_hints_for_device_count",
      "comparison_to_latest",
    ]) {
      const malformed = detail();
      delete (
        (malformed.snapshots as Record<string, unknown>[])[0] as Record<
          string,
          unknown
        >
      )[field];
      expectProtocolFailure(malformed);
    }
  });

  it("rejects unknown fields at exact runtime contract boundaries", () => {
    expectProtocolFailure({ ...detail(), unexpected: true });

    const extraRow = detail();
    (
      (extraRow.latest_snapshot as Record<string, unknown>)
    ).unexpected = true;
    expectProtocolFailure(extraRow);

    const extraComparison = detail({
      snapshots: [
        availableRow({
          snapshot_id: "snap-earlier",
          is_latest: false,
          comparison_to_latest: {
            ...comparison(),
            unexpected: true,
          },
        }),
      ],
    });
    expectProtocolFailure(extraComparison);

    const extraPresence = detail({
      snapshots: [
        availableRow({
          snapshot_id: "snap-earlier",
          is_latest: false,
          comparison_to_latest: {
            ...comparison(),
            device_presence: {
              ...comparison().device_presence,
              unexpected: true,
            },
          },
        }),
      ],
    });
    expectProtocolFailure(extraPresence);

    const extraFact = detail();
    (
      (
        (extraFact.topology_facts as Record<string, unknown>)
          .device_facts as Record<string, unknown>[]
      )[0]
    ).unexpected = true;
    expectProtocolFailure(extraFact);
  });

  it("rejects incoherent pair counts and totals that contradict rows", () => {
    for (const countOverrides of [
      { latest_only_count: 1 },
      { changed_count: 1 },
      { selected_count: 1 },
      { latest_count: 1, latest_only_count: 1 },
    ]) {
      const malformedComparison = comparison();
      Object.assign(malformedComparison.link_counts, countOverrides);
      expectProtocolFailure(
        detail({
          snapshots: [
            availableRow({
              snapshot_id: "snap-earlier",
              is_latest: false,
              comparison_to_latest: malformedComparison,
            }),
          ],
        }),
      );
    }
  });

  it("rejects missing or contradictory comparison changed facts", () => {
    const presenceComparison = {
      ...comparison(),
      status: "changed",
      device_presence: {
        latest: false,
        selected: true,
        changed: true,
      },
    };
    const base = detail({
      latest_snapshot: availableRow({
        device_present_in_snapshot: false,
      }),
      snapshots: [
        availableRow({
          snapshot_id: "snap-earlier",
          is_latest: false,
          comparison_to_latest: presenceComparison,
        }),
      ],
      topology_facts: changedTopologyFacts(false, true),
    });

    const missing = structuredClone(base);
    (
      (
        (
          missing.topology_facts as Record<string, unknown>
        ).comparison_facts_by_snapshot_id as Record<string, unknown[]>
      )["snap-earlier"][0] as Record<string, Record<string, unknown>>
    ).params = {};
    expectProtocolFailure(missing);

    const contradictory = structuredClone(base);
    (
      (
        (
          contradictory.topology_facts as Record<string, unknown>
        ).comparison_facts_by_snapshot_id as Record<string, unknown[]>
      )["snap-earlier"][0] as Record<string, Record<string, unknown>>
    ).params.latest_device_present_in_snapshot = true;
    expectProtocolFailure(contradictory);

    expectProtocolFailure({
      ...base,
      topology_facts: {
        stale_threshold_hours: 24,
        device_facts: [],
        comparison_facts_by_snapshot_id: {},
      },
    });
  });

  it("accepts a limited latest layout only without earlier comparisons", () => {
    const parsed = parseDeviceSnapshotHistoryDetail(
      detail({
        latest_snapshot: limitedRow({
          snapshot_id: "snap-latest",
          is_latest: true,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: null,
          }),
        ],
        topology_facts: {
          stale_threshold_hours: 24,
          device_facts: [],
          comparison_facts_by_snapshot_id: {},
        },
      }),
    );
    expect(parsed.latest_snapshot?.layout_state).toBe("limited");
    expect(parsed.snapshots[0]?.comparison_to_latest).toBeNull();

    expectProtocolFailure(
      detail({
        latest_snapshot: limitedRow({
          snapshot_id: "snap-latest",
          is_latest: true,
        }),
        snapshots: [
          availableRow({
            snapshot_id: "snap-earlier",
            is_latest: false,
            comparison_to_latest: comparison(),
          }),
        ],
        topology_facts: {
          stale_threshold_hours: 24,
          device_facts: [],
          comparison_facts_by_snapshot_id: {},
        },
      }),
    );
  });

  it("rejects latest device facts when the latest layout is limited", () => {
    const limitedDetail = detail({
      latest_snapshot: limitedRow({
        snapshot_id: "snap-latest",
        is_latest: true,
      }),
      snapshots: [],
      topology_facts: {
        stale_threshold_hours: 24,
        device_facts: [],
        comparison_facts_by_snapshot_id: {},
      },
    });
    parseDeviceSnapshotHistoryDetail(limitedDetail);

    for (const impossibleFact of [
      {
        code: "device_absent_from_latest_snapshot",
        params: {
          device_ieee: "0xabc",
          snapshot_id: "snap-latest",
        },
      },
      {
        code: "device_no_latest_links",
        params: { device_ieee: "0xabc" },
      },
      {
        code: "device_latest_vs_selected_changed",
        params: {
          device_ieee: "0xabc",
          comparison_status: "changed",
          snapshot_id: "snap-earlier",
          latest_device_present_in_snapshot: false,
          selected_device_present_in_snapshot: true,
          device_presence_changed: true,
        },
      },
    ]) {
      expectProtocolFailure({
        ...limitedDetail,
        topology_facts: {
          stale_threshold_hours: 24,
          device_facts: [impossibleFact],
          comparison_facts_by_snapshot_id: {},
        },
      });
    }
  });

  it("wires the strict parser into the API client and fails closed", async () => {
    const malformed = detail({
      snapshots: [limitedRow({ links_for_device_count: 0 })],
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(malformed), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api.topologyDeviceSnapshotHistory("home", "0xabc"),
    ).rejects.toMatchObject({
      kind: "protocol",
      detail: "malformed",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
