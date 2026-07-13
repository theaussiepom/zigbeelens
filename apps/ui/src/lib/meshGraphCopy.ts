/**
 * Central human-facing copy for the Mesh Evidence Graph.
 *
 * Keep this aligned with docs/ubiquitous-language.md. Prefer these constants
 * over scattering product language through components.
 */

import type {
  EvidenceClass,
  EvidenceConfidence,
  MeshEvidenceEdge,
  MeshHealthBucket,
  MeshNodeFlag,
  MeshRole,
} from "@/lib/meshEvidence";
import { coverageHelperText, coverageLabel } from "@/viewModels/decisionCopy";

/* ------------------------------------------------------------------------ */
/* Safety banner                                                             */
/* ------------------------------------------------------------------------ */

export const GRAPH_SAFETY_COPY_LIVE =
  "This is an evidence view, not a live routing map. Lines show what ZigbeeLens has observed or suggested, with limits explained where they affect how you should interpret the evidence.";

/* ------------------------------------------------------------------------ */
/* Details panel chrome                                                      */
/* ------------------------------------------------------------------------ */

export const DEVICE_DETAILS_PANEL_LABEL = "Device details";
export const LINK_DETAILS_PANEL_LABEL = "Link details";
export const SUGGESTED_INVESTIGATION_PANEL_LABEL = "Suggested investigation link";

export const LINK_SECTION_WHAT_IT_MEANS = "What this line means";
export const LINK_SECTION_WHY_DRAWN = "Why ZigbeeLens drew it";
export const LINK_SECTION_SUPPORTING = "Supporting evidence";
export const LINK_SECTION_DOES_NOT_PROVE = "What this does not prove";
export const LINK_SECTION_CHECKS = "Suggested checks";

export const DEVICE_SECTION_SUMMARY = "Device summary";
export const DEVICE_SECTION_STATUS = "Current ZigbeeLens status";
export const DEVICE_SECTION_TOPOLOGY = "Topology evidence";
export const DEVICE_SECTION_STATS = "Diagnostic stats";
export const DEVICE_SECTION_RECENT_MISSING = "Recent missing evidence";
export const DEVICE_SECTION_PASSIVE_HINTS = "Suggested investigation links";
export const DEVICE_SECTION_OPEN_ISSUE = "Open issue";
export const DEVICE_SECTION_CHECKS = "What to check next";
export const DEVICE_SECTION_STORY = "Device story";

export const DEVICE_STORY_WHY_TITLE = "Why";
export const DEVICE_STORY_LIMITATIONS_TITLE = "What this does not prove";
export const DEVICE_STORY_CHECKS_TITLE = "Suggested checks";
export const DEVICE_STORY_COVERAGE_TITLE = "Data coverage";
export const DEVICE_STORY_EVIDENCE_TITLE = "Supporting evidence";
export const DEVICE_STORY_LOADING_COPY = "Loading device story…";
export const DEVICE_STORY_UNAVAILABLE_COPY =
  "Device story is unavailable right now. Other device details still reflect stored evidence.";

export const DEVICE_STORY_HEADLINE_LEADS: Record<string, string> = {
  current_issue_present:
    "Review the current issue signals before changing mesh setup or device placement.",
  topology_evidence_gap:
    "Latest topology evidence is missing links that existed earlier. Absence from the latest snapshot does not prove the device failed.",
  availability_tracking_needed:
    "Availability reporting is off, so offline history and passive observations are limited.",
  stale_last_seen: "Last-seen reporting looks older than expected for this device.",
  low_battery: "Battery is reported below the configured low threshold.",
  data_coverage_gaps:
    "Some interpretation context is limited by missing enrichment or route-hint evidence.",
  no_notable_signals: "No stronger device story signals were found in stored evidence.",
};

/* ------------------------------------------------------------------------ */
/* Connection controls                                                       */
/* ------------------------------------------------------------------------ */

export const CONNECTIONS_GROUP_LABEL = "Connections to show";
export const CONNECTIONS_EXPLAINER_TOGGLE = "What do these mean?";

export const CONNECTION_CONTROL_COPY = {
  routeHints: {
    label: "Route hints",
    empty:
      "No route hints in the latest snapshot. Capture a new topology snapshot; if they stay empty, your Zigbee2MQTT adapter may not report routing tables.",
  },
  bestNeighbourLinks: {
    label: "Best neighbour links",
  },
  allNeighbourLinks: {
    label: "All neighbour links",
  },
  oldUncertainLinks: {
    label: "Old or uncertain links",
    empty: "No old or uncertain links in this snapshot.",
  },
  recentMissingLinks: {
    label: "Recent missing links",
    empty: "No recent missing links in the selected history window.",
  },
  lastKnownLinks: {
    label: "Last known links",
    empty:
      "Every device has link evidence in the latest snapshot, so no last known links are needed.",
  },
  suggestedInvestigationLinks: {
    label: "Suggested investigation links",
    empty: "No suggested investigation links are available for this network yet.",
  },
} as const;

export const CONNECTIONS_FOOTNOTE =
  "Turning a connection type off only changes what is drawn. All evidence remains available by selecting a device or turning on “All neighbour links”.";

export const GRAPH_VIEW_GROUP_LABEL = "Graph view";
export const GRAPH_VIEW_DRAW_MORE_LINKS = "Draw more links";
export const GRAPH_VIEW_PRESET_CUSTOM_LABEL = "Custom";

export const GRAPH_VIEW_PRESET_COPY = {
  troubleshooting: {
    label: "Troubleshooting",
    description:
      "Focused snapshot links plus recent missing and suggested investigation hints.",
  },
  router_review: {
    label: "Router review",
    description: "Route hints and recent missing evidence around observed routers.",
  },
  battery_devices: {
    label: "Battery devices",
    description: "Best neighbour and last known links for sleepy battery devices.",
  },
  quiet_view: {
    label: "Quiet view",
    description: "A minimal set of strongest neighbour links only.",
  },
  full_snapshot_links: {
    label: "Full snapshot links",
    description: "All neighbour, route and old or uncertain links from the latest snapshot.",
  },
  custom: {
    label: GRAPH_VIEW_PRESET_CUSTOM_LABEL,
    description: "Your manual link choices differ from a preset.",
  },
} as const;

export const CONNECTIONS_EXPLAINER = {
  bestNeighbourLinks:
    "Best neighbour links come from each device’s neighbour table: other devices it could hear over the radio, with a link quality (LQI) reading. They show which connections are possible. ZigbeeLens draws a focused set of the strongest links per device so dense networks stay readable; “All neighbour links” draws every one.",
  routeHints:
    "Route hints come from each router’s routing table: the next-hop entries it reported when the snapshot was captured. They are closer to how the mesh was operating than radio audibility alone, but Zigbee routes change frequently — this is capture-time evidence, not proof of current live routing.",
  summary:
    "In short: neighbour links show what is possible, route hints show what was being used at capture time. Where a device pair has both, only the route hint is drawn — one line per pair. The neighbour evidence is never removed: select a device to see its full evidence neighbourhood.",
  recentMissingLinks:
    "Recent missing links were observed in recent previous topology snapshots but are not present in the latest usable snapshot. They help explain gaps — for example a device that dropped out of the latest map — but a missing link alone does not prove a failure.",
  lastKnownLinks:
    "Last known links keep otherwise-linkless devices on the map. Sleepy battery devices routinely age out of router neighbour tables, so a device can be healthy yet have no link entries in the latest snapshot. ZigbeeLens then draws its most recent stored link evidence in a distinct style — last known, not currently reported, and not proof of current connectivity.",
  allNeighbourLinks:
    "All neighbour links draws every observed neighbour link from the latest snapshot; dense networks may become hard to read. Old or uncertain links draws stale or low-confidence evidence that may help investigation but should not be treated as current.",
  suggestedInvestigationLinks:
    "Suggested investigation links are cautious hints from passive observations, such as devices repeatedly showing instability around the same time. They are not topology evidence and do not prove devices are connected or that anything is routing between them.",
} as const;

/* ------------------------------------------------------------------------ */
/* Device search                                                             */
/* ------------------------------------------------------------------------ */

export const DEVICE_SEARCH_LABEL = "Search devices";
export const DEVICE_SEARCH_PLACEHOLDER = "Search devices…";
export const DEVICE_SEARCH_HELPER =
  "Search by name, IEEE address, model, manufacturer or status.";

/** Shown only after the user has typed a query that matches nothing. */
export function deviceSearchNoResultsCopy(query: string): string {
  return `No matching devices for “${query}”.`;
}

/* ------------------------------------------------------------------------ */
/* Evidence report / export                                                  */
/* ------------------------------------------------------------------------ */

export const REPORT_MENU_LABEL = "Create report";
export const REPORT_COPY_LABEL = "Copy summary";
export const REPORT_DOWNLOAD_MARKDOWN_LABEL = "Download Markdown";
export const REPORT_DOWNLOAD_JSON_LABEL = "Download JSON evidence summary";
export const REPORT_COPIED_MESSAGE = "Copied evidence summary.";
export const REPORT_COPY_FAILED_MESSAGE =
  "Copy did not complete. Download the Markdown report instead.";

export const REPORT_TITLE = "ZigbeeLens evidence summary";
export const REPORT_SAFETY_NOTE =
  "This is an evidence summary, not a live routing map.";
export const REPORT_ROUTE_HINT_NOTE =
  "Route hints come from topology snapshot evidence at capture time. They are useful for review, but should not be treated as current live routing.";
export const REPORT_PASSIVE_HINT_NOTE =
  "Suggested investigation links come from passive observations. They can help decide which devices to inspect together, but they are not topology links.";

/* ------------------------------------------------------------------------ */
/* Snapshot compare (report builder support only)                            */
/* ------------------------------------------------------------------------ */

/** Only shown inside a compare-specific report, never in the graph view. */
export const COMPARE_NOT_ENOUGH_HISTORY_COPY =
  "There is not enough snapshot history to compare yet.";
/** Only shown inside a compare-specific report, never in the graph view. */
export const COMPARE_NO_CHANGES_COPY =
  "No topology-evidence differences were found between these usable snapshots.";

/* ------------------------------------------------------------------------ */
/* Device-led snapshot history                                               */
/* ------------------------------------------------------------------------ */

export const SNAPSHOT_HISTORY_SECTION_TITLE = "Snapshot history";
export const SNAPSHOT_HISTORY_LATEST_LABEL = "Latest snapshot";
export const SNAPSHOT_HISTORY_COMPARE_WITH_LABEL = "Compare latest snapshot with";
export const SNAPSHOT_HISTORY_EMPTY_COPY =
  "No earlier usable topology snapshots are available for this device yet.";
export const SNAPSHOT_HISTORY_UNAVAILABLE_COPY =
  "Snapshot history is unavailable right now.";

export const SNAPSHOT_HISTORY_WHY_TITLE = "Why";
export const SNAPSHOT_HISTORY_MEANING_TITLE = "What this means";
export const SNAPSHOT_HISTORY_CHECKS_TITLE = "Suggested checks";
export const SNAPSHOT_HISTORY_EVIDENCE_DETAILS_TITLE = "Evidence details";

/** Card headings for the comparison status — comparison only, not health. */
export const SNAPSHOT_COMPARE_STATUS_LABELS = {
  no_notable_change: "No notable change",
  changed: "Changed",
  watch: "Watch",
  worth_reviewing: "Worth reviewing",
} as const;

/** Compact per-row status labels for the snapshot list. */
export const SNAPSHOT_COMPARE_ROW_STATUS_LABELS = {
  no_notable_change: "Similar",
  changed: "Changed",
  watch: "Watch",
  worth_reviewing: "Worth reviewing",
} as const;

/** One-line lead copy under the status heading. */
export const SNAPSHOT_COMPARE_STATUS_LEADS = {
  no_notable_change: "No notable change compared with the selected snapshot.",
  changed: "Snapshot details changed, but nothing here stands out as needing review.",
  watch: "Worth keeping an eye on, especially if this device or nearby devices are also unstable.",
  worth_reviewing: "This comparison has device-level changes that may be worth checking.",
} as const;

/** "What this means" copy per comparison status. */
export const SNAPSHOT_COMPARE_MEANING = {
  no_notable_change:
    "Topology snapshots can vary between captures. This comparison does not show anything that stands out for this device.",
  changed:
    "This may be normal Zigbee snapshot variation. Review only if this device is also behaving poorly.",
  watch:
    "This is a difference between two point-in-time topology snapshots. It does not prove the device moved or that live routing changed.",
  worth_reviewing:
    "This is a difference between two point-in-time topology snapshots. It does not prove the device moved or that live routing changed.",
} as const;

export const SNAPSHOT_HISTORY_SOURCE_NOTE =
  "Source: Zigbee neighbour table and route-table hints from topology snapshots.";
export const SNAPSHOT_HISTORY_SELECTED_ONLY_NOTE =
  "Links only in the selected snapshot were shown for this device in that earlier snapshot but are not shown in the latest snapshot. This alone does not prove a problem.";
export const SNAPSHOT_HISTORY_ROUTE_HINT_NOTE =
  "Route hints are route-table hints captured during topology collection. They are not proof of current live routing.";

/* Availability tracking pills — labels and helpers sourced from decisionCopy. */

export const AVAILABILITY_PILL_OFF = coverageLabel("availability_tracking_off");
export const AVAILABILITY_PILL_OFF_HELPER = coverageHelperText("availability_tracking_off");
export const AVAILABILITY_PILL_BUILDING = coverageLabel("availability_history_building");
export const AVAILABILITY_PILL_BUILDING_HELPER = coverageHelperText(
  "availability_history_building",
);
export const AVAILABILITY_PILL_UNKNOWN = coverageLabel("availability_status_unknown");
export const AVAILABILITY_PILL_UNKNOWN_HELPER = coverageHelperText(
  "availability_status_unknown",
);

export const EVIDENCE_COVERAGE_STRIP_TITLE = "Evidence coverage";
export const DEVICE_SECTION_DATA_COVERAGE = "Evidence coverage";

/* ------------------------------------------------------------------------ */
/* Investigation panel                                                       */
/* ------------------------------------------------------------------------ */

export const INVESTIGATION_PANEL_TITLE = "Where to look first";
export const INVESTIGATION_PANEL_SUBTITLE =
  "Ranked from existing ZigbeeLens evidence. These are places to look first, not root-cause claims.";

/** Shown only when the panel is present and the backend returned no cards. */
export const INVESTIGATION_EMPTY_COPY =
  "No investigation priorities from the current evidence yet.";

export const INVESTIGATION_SECTION_WHY = "Why this is worth checking";
export const INVESTIGATION_SECTION_SUPPORTING = "Supporting evidence";
export const INVESTIGATION_SECTION_DOES_NOT_PROVE = "What this does not prove";
export const INVESTIGATION_SECTION_CHECKS = "Suggested checks";

export type InvestigationActionGroup =
  | "check_power_reporting"
  | "review_observed_router_area"
  | "investigate_shared_event"
  | "improve_data_coverage"
  | "watch_only";

export const INVESTIGATION_ACTION_GROUP_LABELS: Record<InvestigationActionGroup, string> = {
  check_power_reporting: "Check power/reporting",
  review_observed_router_area: "Review observed router area",
  investigate_shared_event: "Investigate shared event",
  improve_data_coverage: "Improve data coverage",
  watch_only: "Watch only",
};

export const INVESTIGATION_ACTION_LEADS: Record<InvestigationActionGroup, string> = {
  check_power_reporting:
    "Check whether affected devices have power and are reporting before treating this as a mesh problem.",
  review_observed_router_area:
    "Review the observed router neighbourhood, power, and placement around this concentration of evidence.",
  investigate_shared_event:
    "Investigate these devices together for a shared power, placement, or timing pattern.",
  improve_data_coverage:
    "Improve topology evidence coverage before relying on the graph for these devices.",
  watch_only:
    "Keep watching — weaker passive evidence is present, but no stronger check is suggested yet.",
};

/* ------------------------------------------------------------------------ */
/* Evidence class labels                                                     */
/* ------------------------------------------------------------------------ */

export function evidenceClassLabel(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Latest snapshot neighbour link";
    case "latest_snapshot_route":
      return "Route hint";
    case "historical_neighbor":
      return "Recent missing link";
    case "historical_route":
      return "Recent missing route hint";
    case "last_known_link":
      return "Last known link";
    case "passive_derived_association":
      return "Suggested investigation link";
    case "stale_low_confidence":
      return "Old or uncertain link";
  }
}

export function evidenceClassDescription(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "An observed neighbour link from the latest topology snapshot. A snapshot is point-in-time evidence; it does not prove current live routing.";
    case "latest_snapshot_route":
      return "A route hint from the latest topology snapshot. This suggests possible next-hop evidence at capture time. It does not prove current live routing.";
    case "historical_neighbor":
      return "This link was seen recently but is not in the latest usable snapshot. That can happen if the device is sleepy, recently moved, powered off, or simply absent from the latest map. Check the device before treating this as a mesh problem.";
    case "historical_route":
      return "Route-table evidence was observed in a recent previous topology snapshot. This suggests possible next-hop evidence at that time. It does not prove current live routing.";
    case "last_known_link":
      return "The most recent stored link evidence for a device that reported no links in the latest snapshot. Sleepy battery devices routinely age out of router neighbour tables, so this is last known evidence, not a currently reported link.";
    case "passive_derived_association":
      return "A cautious hint from passive observations, such as repeated instability around the same time. These devices may be worth investigating together. This is not topology evidence and does not prove the devices are connected.";
    case "stale_low_confidence":
      return "Old or weakly supported evidence. Treat this as background context, not as a description of the current mesh.";
  }
}

export function evidenceClassShortLabel(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Neighbour link";
    case "latest_snapshot_route":
      return "Route hint";
    case "historical_neighbor":
      return "Recent missing link";
    case "historical_route":
      return "Recent missing route";
    case "last_known_link":
      return "Last known";
    case "passive_derived_association":
      return "Investigation hint";
    case "stale_low_confidence":
      return "Old or uncertain";
  }
}

/** Metric-chip / control tooltips using the same approved language. */
export function evidenceClassTooltip(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Links reported in the latest topology snapshot.";
    case "latest_snapshot_route":
      return "Route-table / next-hop evidence from the latest topology snapshot.";
    case "historical_neighbor":
    case "historical_route":
      return "Links seen in recent previous snapshots but not present in the latest usable snapshot.";
    case "last_known_link":
      return "Most recent stored link evidence for a device with no links in the latest snapshot.";
    case "passive_derived_association":
      return "Passive-derived hints. These are not topology links.";
    case "stale_low_confidence":
      return "Old or weakly supported evidence for investigation context.";
  }
}

export function confidenceStrengthCopy(confidence: EvidenceConfidence): string {
  switch (confidence) {
    case "high":
      return "Looks strong";
    case "medium":
      return "Looks moderate";
    case "low":
      return "Looks weak";
  }
}

export function confidenceExplanation(confidence: EvidenceConfidence): string {
  return `${confidenceStrengthCopy(confidence)} — based on how often and how recently this evidence was observed, not on live measurements.`;
}

export function meshRoleLabel(role: MeshRole): string {
  switch (role) {
    case "coordinator":
      return "Coordinator";
    case "router":
      return "Router";
    case "end_device":
      return "End device";
    case "unknown":
      return "Unknown role";
  }
}

export function meshHealthBucketLabel(bucket: MeshHealthBucket): string {
  switch (bucket) {
    case "healthy":
      return "Healthy";
    case "needs_attention":
      return "Needs attention";
    case "unavailable":
      return "Unavailable";
    case "diagnostics_limited":
      return "Limited diagnostics";
    case "recently_unstable":
      return "Recently unstable";
    case "informational":
      return "Informational";
    case "unknown":
      return "Unknown";
  }
}

export function meshNodeFlagLabel(flag: MeshNodeFlag): string {
  switch (flag) {
    case "unavailable":
      return "Unavailable";
    case "needs_attention":
      return "Needs attention";
    case "diagnostics_limited":
      return "Limited diagnostics";
    case "interview_failure":
      return "Interview failure";
    case "weak_link_candidate":
      return "Weak-link candidate";
    case "router_risk_candidate":
      return "Router-risk candidate";
    case "battery_sleepy":
      return "Battery / sleepy";
  }
}

export function formatEvidenceCount(value: number | null | undefined): string {
  if (value == null) return "Not recorded";
  return String(value);
}

export function formatLqi(value: number | null | undefined): string {
  if (value == null) return "No data";
  return String(value);
}

export function latestSnapshotStatusCopy(edge: MeshEvidenceEdge): string {
  if (edge.evidence_class === "passive_derived_association") {
    return "Not from a topology snapshot — this suggestion comes from passive observations.";
  }
  if (edge.in_latest_snapshot) {
    return "Present in the latest topology snapshot.";
  }
  if (edge.latest_layout_limited) {
    return "The latest snapshot has limited topology evidence, so absence from the latest graph is not meaningful by itself.";
  }
  return "Not observed in the latest topology snapshot. This alone does not prove a failure.";
}

/**
 * Whether a link details panel should show “What this does not prove”.
 * Quiet latest neighbour links without issue context usually do not need it.
 */
export function linkNeedsDoesNotProve(edge: MeshEvidenceEdge): boolean {
  switch (edge.evidence_class) {
    case "latest_snapshot_route":
    case "historical_neighbor":
    case "historical_route":
    case "last_known_link":
    case "passive_derived_association":
    case "stale_low_confidence":
      return true;
    case "latest_snapshot_neighbor":
      return Boolean(edge.issue_related) || Boolean(edge.latest_layout_limited);
  }
}

/** Practical “what this does not prove” lines for a selected link. */
export function linkDoesNotProveCopy(edge: MeshEvidenceEdge): string[] {
  const lines: string[] = [];
  switch (edge.evidence_class) {
    case "latest_snapshot_neighbor":
      lines.push(
        "This is capture-time neighbour evidence. It does not prove current live routing.",
      );
      break;
    case "latest_snapshot_route":
      lines.push(
        "This suggests possible next-hop evidence at capture time. It does not prove current live routing.",
      );
      break;
    case "historical_neighbor":
      lines.push(
        "This does not prove a failure. A missing link can happen if the device is sleepy, recently moved, powered off, or simply absent from the latest map.",
      );
      break;
    case "historical_route":
      lines.push(
        "This does not prove current live routing, and its absence from the latest snapshot does not prove a failure.",
      );
      break;
    case "last_known_link":
      lines.push(
        "This is last known evidence, not a currently reported link. It does not prove current connectivity or live routing.",
      );
      break;
    case "passive_derived_association":
      lines.push(
        "This suggestion comes from passive observations, not topology evidence. It is useful for deciding which devices to inspect together, but it should not be treated as a connection between them.",
        "This does not prove current live routing.",
      );
      break;
    case "stale_low_confidence":
      lines.push(
        "This is background context only. It should not be treated as a description of the current mesh.",
      );
      break;
  }
  if (edge.latest_layout_limited) {
    lines.push(
      "The latest snapshot has limited topology evidence, so absence from the latest graph is not meaningful by itself.",
    );
  }
  return lines;
}

/** Human wording for backend passive-hint rule ids. */
export function passiveRuleReason(rule: string): string {
  switch (rule) {
    case "shared_instability_window":
      return "These devices repeatedly showed instability around the same time.";
    case "topology_neighbourhood_corroboration":
      return "Recent topology evidence also places these devices in a related router neighbourhood.";
    case "current_issue_relevance":
      return "One or more of these devices currently needs attention, and recent passive observations show related instability timing.";
    default:
      return rule;
  }
}

/* ------------------------------------------------------------------------ */
/* Forbidden phrase helpers (tests / audits)                                 */
/* ------------------------------------------------------------------------ */

/** Phrases that must not appear in user-facing graph UI text. */
export const FORBIDDEN_USER_FACING_PHRASES: readonly string[] = [
  "hidden for readability",
  "ignored",
  "discarded",
  "irrelevant",
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
  "broken link",
  "lost link",
  "inferred route",
  "derived route",
  "AI suggested",
  "AI detected",
  "confidence score",
  "semantic inference",
  "nothing to see",
  "no problems found",
  "drawer",
];

export function findForbiddenUserFacingPhrases(text: string): string[] {
  const lower = text.toLowerCase();
  return FORBIDDEN_USER_FACING_PHRASES.filter((phrase) => lower.includes(phrase.toLowerCase()));
}
