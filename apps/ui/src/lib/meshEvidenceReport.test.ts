import { describe, expect, it } from "vitest";
import type { InvestigationCard, SnapshotCompareDetail } from "@/lib/api";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { findForbiddenUserFacingPhrases } from "@/lib/meshGraphCopy";
import {
  buildMeshEvidenceReport,
  sanitizeFilenamePart,
  type MeshEvidenceReportInput,
} from "@/lib/meshEvidenceReport";

const GENERATED_AT = new Date(2026, 6, 9, 16, 42); // local 2026-07-09 16:42

const REPORT_FORBIDDEN_PHRASES = [
  "drawer",
  "lost link",
  "broken link",
  "dropped",
  "disconnected",
  "parent router",
  "child device",
  "current route",
  "currently routed",
  "actual route",
  "actual path",
  "connected through",
  "root cause",
  "caused by",
  "failed because",
  "AI suggested",
  "confidence score",
  "semantic inference",
  "nothing to see",
  "no problems found",
];

function makeDevice(overrides: Partial<MeshEvidenceDevice>): MeshEvidenceDevice {
  return {
    ieee_address: "0x01",
    network_id: "home",
    friendly_name: "Device",
    role: "end_device",
    power: "mains",
    availability: "online",
    in_inventory: true,
    in_latest_snapshot: true,
    health_bucket: "healthy",
    flags: [],
    inventory_status: "In Zigbee2MQTT device inventory",
    topology_evidence_summary: "Observed in the latest topology snapshot.",
    passive_observation_summary: "",
    open_issue: null,
    diagnostic_stats: [],
    ...overrides,
  };
}

function makeEdge(overrides: Partial<MeshEvidenceEdge>): MeshEvidenceEdge {
  return {
    id: "edge-1",
    network_id: "home",
    source: "0x01",
    target: "0x02",
    evidence_class: "latest_snapshot_neighbor",
    confidence: "high",
    directional: false,
    in_latest_snapshot: true,
    limitations: [],
    suggested_investigation: [],
    ...overrides,
  };
}

const SHARED_AVAILABILITY_EVENT_LIMITATION =
  "Devices changing availability around the same time does not prove they share a Zigbee route, path, parent, or root cause.";

function makeSharedAvailabilityCard(
  overrides: Partial<InvestigationCard> = {},
): InvestigationCard {
  return makeCard({
    id: "shared-availability-test",
    type: "shared_availability_event",
    priority: "Worth checking",
    score: 6,
    title: "Several devices went offline around the same time",
    summary:
      "11 devices went offline during a shared availability event lasting about 22 minutes.",
    why_it_matters:
      "The timing is more useful as a shared event than as evidence of a relationship between individual device pairs.",
    supporting_evidence: [
      "11 devices went offline in this shared event.",
      "Evidence comes from stored offline availability transitions.",
      "Event duration about 22 minutes.",
    ],
    limitations: [
      "This is a place to look first based on available ZigbeeLens evidence. It is not a root-cause claim and does not prove live routing or current connectivity.",
      SHARED_AVAILABILITY_EVENT_LIMITATION,
    ],
    suggested_next_steps: [
      "Check Zigbee2MQTT status or logs around the event time.",
      "Check MQTT broker or ZigbeeLens collector interruptions around the event time.",
      "Check host restart, maintenance, or broad power events around the same time.",
      "Compare any active incidents or timeline events from that period.",
    ],
    device_ieees: ["0xd00", "0xd01"],
    edge_ids: [],
    primary_device_ieee: null,
    primary_neighbourhood_ieee: null,
    created_from_evidence_classes: ["availability_transition"],
    latest_supporting_evidence_at: "2026-07-06T08:22:00+00:00",
    action_group: "investigate_shared_event",
    ...overrides,
  });
}

function makeCard(overrides: Partial<InvestigationCard>): InvestigationCard {
  return {
    id: "card-1",
    type: "recent_missing_cluster",
    priority: "Worth checking",
    score: 8,
    title: "Several recent missing links involve Hall Router",
    summary: "Hall Router has links seen recently but not in the latest usable snapshot.",
    why_it_matters: "May be worth checking if the device moved or is powered.",
    supporting_evidence: ["3 recent missing links involve Hall Router."],
    limitations: [
      "This is a place to look first based on available ZigbeeLens evidence. It is not a claim about live routing or current connectivity.",
    ],
    suggested_next_steps: ["Check device power."],
    device_ieees: ["0x02"],
    edge_ids: [],
    primary_device_ieee: "0x02",
    primary_neighbourhood_ieee: null,
    created_from_evidence_classes: ["historical_neighbor"],
    latest_supporting_evidence_at: null,
    action_group: "check_power_reporting",
    ...overrides,
  };
}

function makeCompare(overrides: Partial<SnapshotCompareDetail>): SnapshotCompareDetail {
  return {
    network_id: "home",
    base_snapshot: { snapshot_id: "snap-old", captured_at: "2026-07-08T10:00:00+00:00" },
    compare_snapshot: { snapshot_id: "snap-new", captured_at: "2026-07-09T10:00:00+00:00" },
    comparison_window: { usable_snapshots: 3 },
    has_comparison: true,
    summary:
      "Compared with the previous usable snapshot, ZigbeeLens found moderate topology-evidence churn. Most changes are neighbour-link evidence changes. This can be normal between Zigbee topology snapshots and does not prove live routing changed.",
    summary_items: [
      "6 neighbour links seen in latest snapshot only",
      "4 neighbour links seen in previous snapshot only",
    ],
    changes: [
      {
        id: "c1",
        type: "new_neighbour_link",
        title: "New neighbour link",
        summary: "…",
        device_ieees: ["0x01", "0x02"],
        edge_key: "0x01|0x02",
        before: {},
        after: {},
        supporting_evidence: [],
        practical_note: "…",
        focus_device_ieees: ["0x01", "0x02"],
        focus_edge_ids: [],
      },
    ],
    counts: {
      newly_observed_devices: 0,
      devices_no_topology_evidence: 0,
      new_neighbour_links: 6,
      neighbour_links_not_present_latest: 4,
      changed_neighbour_links: 0,
      new_route_hints: 0,
      route_hints_not_present_latest: 0,
      changed_route_hints: 0,
      total_changes: 10,
    },
    churn: {
      level: "moderate",
      changed_evidence_total: 10,
      available_compare_evidence: 40,
    },
    worth_reviewing: [],
    limitations: [],
    ...overrides,
  };
}

function baseInput(overrides: Partial<MeshEvidenceReportInput>): MeshEvidenceReportInput {
  return {
    networkId: "home",
    networkName: "Home",
    latestSnapshotCapturedAt: "2026-07-09T06:31:00+00:00",
    generatedAt: GENERATED_AT,
    devices: [
      makeDevice({ ieee_address: "0x01", friendly_name: "Coordinator", role: "coordinator" }),
      makeDevice({ ieee_address: "0x02", friendly_name: "Hall Router", role: "router" }),
    ],
    edges: [makeEdge({})],
    investigations: [],
    compare: null,
    selectedDevice: null,
    ...overrides,
  };
}

describe("buildMeshEvidenceReport", () => {
  it("includes a header with network name, id and generated time", () => {
    const { markdown } = buildMeshEvidenceReport(baseInput({}));
    expect(markdown).toContain("# ZigbeeLens evidence summary");
    expect(markdown).toContain("Network: Home (home)");
    expect(markdown).toContain("Generated: 2026-07-09 16:42");
  });

  it("includes latest snapshot info when available and omits it when unknown", () => {
    const withSnapshot = buildMeshEvidenceReport(baseInput({}));
    expect(withSnapshot.markdown).toContain("Latest topology snapshot: ");
    const withoutSnapshot = buildMeshEvidenceReport(
      baseInput({ latestSnapshotCapturedAt: null }),
    );
    expect(withoutSnapshot.markdown).not.toContain("Latest topology snapshot");
  });

  it("includes useful non-zero counts and omits zero-count lines", () => {
    const { markdown } = buildMeshEvidenceReport(baseInput({}));
    expect(markdown).toContain("- 2 known devices");
    expect(markdown).toContain("- 2 devices observed in the latest topology snapshot");
    expect(markdown).toContain("- 1 latest snapshot evidence link available");
    // No recent missing / passive / investigation evidence: those lines are
    // omitted entirely, never rendered as zero.
    expect(markdown).not.toMatch(/- 0 /);
    expect(markdown).not.toContain("recent missing");
    expect(markdown).not.toContain("suggested investigation");
    expect(markdown).not.toContain("investigation priorit");
  });

  it("formats large counts with separators", () => {
    const edges = Array.from({ length: 1019 }, (_, i) =>
      makeEdge({ id: `edge-${i}`, source: "0x01", target: `0x${i + 10}` }),
    );
    const { markdown } = buildMeshEvidenceReport(baseInput({ edges }));
    expect(markdown).toContain("1,019 latest snapshot evidence links available");
  });

  it("omits What changed unless compare data is provided", () => {
    const without = buildMeshEvidenceReport(baseInput({}));
    expect(without.markdown).not.toContain("## What changed");
    const withCompare = buildMeshEvidenceReport(baseInput({ compare: makeCompare({}) }));
    expect(withCompare.markdown).toContain("## What changed");
    // The section leads with the calm churn summary, then neutral counts.
    expect(withCompare.markdown).toContain("moderate topology-evidence churn");
    expect(withCompare.markdown).toContain(
      "- 6 neighbour links seen in latest snapshot only",
    );
    expect(withCompare.markdown).toContain(
      "- 4 neighbour links seen in previous snapshot only",
    );
  });

  it("explains not-enough-history and no-change compare states inside the section", () => {
    const notEnough = buildMeshEvidenceReport(
      baseInput({
        compare: makeCompare({ has_comparison: false, changes: [], summary_items: [] }),
      }),
    );
    expect(notEnough.markdown).toContain(
      "There is not enough snapshot history to compare yet.",
    );
    const noChanges = buildMeshEvidenceReport(
      baseInput({ compare: makeCompare({ changes: [], summary_items: [] }) }),
    );
    expect(noChanges.markdown).toContain(
      "No topology-evidence differences were found between these usable snapshots.",
    );
  });

  it("includes investigation priorities with priority-labelled headings", () => {
    const { markdown } = buildMeshEvidenceReport(
      baseInput({ investigations: [makeCard({})] }),
    );
    expect(markdown).toContain("## Where to look first");
    expect(markdown).toContain(
      "### Worth checking: Several recent missing links involve Hall Router",
    );
    expect(markdown).toContain("Supporting evidence:");
    expect(markdown).toContain("- 3 recent missing links involve Hall Router.");
    expect(markdown).toContain("Suggested checks:");
    expect(markdown).toContain("- Check device power.");
    // Historical evidence is easy to over-read: the limitation is included.
    expect(markdown).toContain("What this does not prove:");
  });

  it("omits card limitations where they do not change interpretation", () => {
    const { markdown } = buildMeshEvidenceReport(
      baseInput({
        investigations: [
          makeCard({
            type: "issue_cluster",
            created_from_evidence_classes: ["latest_snapshot_neighbor"],
          }),
        ],
      }),
    );
    expect(markdown).toContain("## Where to look first");
    expect(markdown).not.toContain("What this does not prove:");
  });

  it("includes the selected device section only when a device is selected", () => {
    const without = buildMeshEvidenceReport(baseInput({}));
    expect(without.markdown).not.toContain("## Selected device");

    const device = makeDevice({
      ieee_address: "0x02",
      friendly_name: "Hall Router",
      role: "router",
      health_bucket: "needs_attention",
      diagnostic_stats: [{ label: "Last seen", value: "2h ago" }],
    });
    const edges = [
      makeEdge({ id: "n1", source: "0x02", target: "0x01" }),
      makeEdge({
        id: "h1",
        source: "0x02",
        target: "0x03",
        evidence_class: "historical_neighbor",
        in_latest_snapshot: false,
      }),
      makeEdge({
        id: "p1",
        source: "0x02",
        target: "0x04",
        evidence_class: "passive_derived_association",
        in_latest_snapshot: false,
        suggested_investigation: ["Review both devices' recent availability history."],
      }),
    ];
    const { markdown } = buildMeshEvidenceReport(
      baseInput({ selectedDevice: device, edges }),
    );
    expect(markdown).toContain("## Selected device");
    expect(markdown).toContain("Device: Hall Router");
    expect(markdown).toContain("IEEE: 0x02");
    expect(markdown).toContain("Status: Needs attention");
    expect(markdown).toContain("Role: Router");
    expect(markdown).toContain("- 1 latest snapshot neighbour link");
    expect(markdown).toContain("- 1 recent missing link");
    expect(markdown).toContain("- 1 suggested investigation link");
    expect(markdown).toContain("- Last seen: 2h ago");
    // Checks come only from real backend suggestions on touching evidence.
    expect(markdown).toContain("- Review both devices' recent availability history.");
  });

  it("never invents suggested checks for the selected device", () => {
    const device = makeDevice({ ieee_address: "0x02", friendly_name: "Hall Router" });
    const { markdown } = buildMeshEvidenceReport(
      baseInput({ selectedDevice: device, edges: [makeEdge({ source: "0x02" })] }),
    );
    const selectedSection = markdown.split("## Selected device")[1];
    expect(selectedSection).not.toContain("Suggested checks:");
  });

  it("keeps evidence notes short and only includes notes that apply", () => {
    const neighbourOnly = buildMeshEvidenceReport(baseInput({}));
    expect(neighbourOnly.markdown).toContain(
      "This is an evidence summary, not a live routing map.",
    );
    expect(neighbourOnly.markdown).not.toContain("Route hints come from");
    expect(neighbourOnly.markdown).not.toContain("passive observations");

    const withRoutesAndHints = buildMeshEvidenceReport(
      baseInput({
        edges: [
          makeEdge({}),
          makeEdge({
            id: "r1",
            evidence_class: "latest_snapshot_route",
            directional: true,
          }),
          makeEdge({
            id: "p1",
            evidence_class: "passive_derived_association",
            in_latest_snapshot: false,
          }),
        ],
      }),
    );
    expect(withRoutesAndHints.markdown).toContain("Route hints come from");
    expect(withRoutesAndHints.markdown).toContain(
      "Suggested investigation links come from passive observations.",
    );
  });

  it("is deterministic for the same input", () => {
    const input = baseInput({
      investigations: [makeCard({})],
      compare: makeCompare({}),
      selectedDevice: makeDevice({ ieee_address: "0x02" }),
    });
    expect(buildMeshEvidenceReport(input).markdown).toBe(
      buildMeshEvidenceReport(input).markdown,
    );
  });

  it("builds a sanitised filename from the network name and timestamp", () => {
    const { filenameBase } = buildMeshEvidenceReport(
      baseInput({ networkName: "My Home! (Upstairs)" }),
    );
    expect(filenameBase).toBe("zigbeelens-my-home-upstairs-evidence-summary-2026-07-09-1642");
    expect(sanitizeFilenamePart("///")).toBe("network");
  });

  it("JSON summary uses null for unknown values, never zero", () => {
    const { jsonSummary } = buildMeshEvidenceReport(
      baseInput({ latestSnapshotCapturedAt: null, networkName: null }),
    );
    expect(jsonSummary.latest_snapshot).toBeNull();
    expect(jsonSummary.network_name).toBeNull();
    expect(jsonSummary.snapshot_comparison).toBeNull();
    expect(jsonSummary.selected_device).toBeNull();
  });

  it("renders shared availability event cards with explicit limitations and duration copy", () => {
    const card = makeSharedAvailabilityCard();
    const { markdown, jsonSummary } = buildMeshEvidenceReport(
      baseInput({ investigations: [card] }),
    );
    expect(markdown).toContain("## Where to look first");
    expect(markdown).toContain(
      "### Worth checking: Several devices went offline around the same time",
    );
    expect(markdown).toContain("lasting about 22 minutes");
    expect(markdown).not.toContain("within 5 minutes");
    expect(markdown).toContain("What this does not prove:");
    expect(markdown).toContain(SHARED_AVAILABILITY_EVENT_LIMITATION);
    expect(markdown).toContain("Suggested checks:");
    expect(markdown).toContain("- Check Zigbee2MQTT status or logs around the event time.");
    const shared = jsonSummary.investigation_priorities.find(
      (item) => item.type === "shared_availability_event",
    );
    expect(shared).toBeDefined();
    expect(shared?.edge_ids).toEqual([]);
    expect(shared?.limitations).toContain(SHARED_AVAILABILITY_EVENT_LIMITATION);
  });

  it("keeps shared availability suggested checks cautious in report copy", () => {
    const { markdown } = buildMeshEvidenceReport(
      baseInput({ investigations: [makeSharedAvailabilityCard()] }),
    );
    const checksSection = markdown.split("Suggested checks:")[1] ?? "";
    expect(checksSection.toLowerCase()).not.toMatch(/caused by|outage caused|because/);
    for (const line of checksSection.split("\n").filter((line) => line.startsWith("- "))) {
      expect(line.toLowerCase()).toMatch(/^- check |^- compare /);
    }
  });

  it("uses Phase 5 approved language with no forbidden phrases", () => {
    const { markdown, jsonSummary } = buildMeshEvidenceReport(
      baseInput({
        investigations: [makeCard({})],
        compare: makeCompare({}),
        selectedDevice: makeDevice({ ieee_address: "0x02", friendly_name: "Hall Router" }),
        edges: [
          makeEdge({}),
          makeEdge({ id: "r1", evidence_class: "latest_snapshot_route", directional: true }),
          makeEdge({
            id: "p1",
            source: "0x02",
            evidence_class: "passive_derived_association",
            in_latest_snapshot: false,
          }),
        ],
      }),
    );
    expect(findForbiddenUserFacingPhrases(markdown)).toEqual([]);
    const lower = markdown.toLowerCase();
    for (const phrase of REPORT_FORBIDDEN_PHRASES) {
      expect(lower).not.toContain(phrase.toLowerCase());
    }
    expect(findForbiddenUserFacingPhrases(JSON.stringify(jsonSummary.limitations))).toEqual(
      [],
    );
  });
});
