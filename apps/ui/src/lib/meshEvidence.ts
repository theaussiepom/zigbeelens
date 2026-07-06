/**
 * Mesh Evidence Graph data model.
 *
 * Every edge in the graph is an evidence claim, never a fact of live routing.
 * The types and wording helpers here enforce that framing: evidence classes
 * are explicit, unknown values stay unknown (never rendered as zero), and all
 * user-facing copy avoids claiming current connectivity or failure.
 */

/** The classes of relationship evidence ZigbeeLens can present. */
export type EvidenceClass =
  | "latest_snapshot_neighbor"
  | "latest_snapshot_route"
  | "historical_neighbor"
  | "historical_route"
  | "passive_derived_association"
  | "stale_low_confidence";

export const EVIDENCE_CLASSES: EvidenceClass[] = [
  "latest_snapshot_neighbor",
  "latest_snapshot_route",
  "historical_neighbor",
  "historical_route",
  "passive_derived_association",
  "stale_low_confidence",
];

export type EvidenceConfidence = "high" | "medium" | "low";

/** Passive observations that corroborate (or fail to corroborate) an edge. */
export interface PassiveCorroboration {
  /** Number of availability flaps that correlated in time across the pair. */
  correlated_availability_flaps?: number | null;
  /** Human description of reporting cadence evidence, if any. */
  reporting_cadence?: string | null;
  /** Human description of overlapping stale windows, if any. */
  stale_window_overlap?: string | null;
  /** Human description of a same-area hint, if any. */
  same_area_hint?: string | null;
  /** Friendly names of nearby devices affected in the same window. */
  nearby_affected_devices?: string[] | null;
}

/**
 * One evidence claim about a relationship between two devices.
 * Unknown metadata is represented as null/undefined — never zero.
 */
export interface MeshEvidenceEdge {
  id: string;
  network_id: string;
  /** IEEE address of the source device. */
  source: string;
  /** IEEE address of the target device. */
  target: string;
  evidence_class: EvidenceClass;
  confidence: EvidenceConfidence;
  /** Route/next-hop evidence is directional; adjacency evidence is not. */
  directional: boolean;
  /** Whether this edge relates to an open issue / investigation. */
  issue_related?: boolean;
  /** Whether this relationship appeared in the latest topology snapshot. */
  in_latest_snapshot: boolean;
  /** When the snapshot supplying this evidence was captured, if known. */
  captured_at?: string | null;
  /** Neighbour-table relationship reported by Zigbee2MQTT (e.g. Child). */
  observed_relationship?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  observed_count?: number | null;
  snapshot_count?: number | null;
  lqi_latest?: number | null;
  lqi_min?: number | null;
  lqi_median?: number | null;
  lqi_max?: number | null;
  route_table_evidence?: boolean | null;
  next_hop_evidence?: boolean | null;
  route_observed_count?: number | null;
  /** Route-table entry count in the most recent observation, if recorded. */
  last_route_count?: number | null;
  /**
   * True when the latest snapshot layout was limited, so absence from the
   * latest snapshot cannot be treated as meaningful.
   */
  latest_layout_limited?: boolean | null;
  passive_corroboration?: PassiveCorroboration | null;
  limitations: string[];
  suggested_investigation: string[];
}

export type MeshRole = "coordinator" | "router" | "end_device" | "unknown";

export type MeshNodeFlag =
  | "unavailable"
  | "needs_attention"
  | "diagnostics_limited"
  | "interview_failure"
  | "weak_link_candidate"
  | "router_risk_candidate"
  | "battery_sleepy";

export type MeshHealthBucket =
  | "healthy"
  | "needs_attention"
  | "unavailable"
  | "diagnostics_limited"
  | "recently_unstable"
  | "informational"
  | "unknown";

export interface MeshOpenIssue {
  title: string;
  summary: string;
}

/** One device in the mesh evidence graph. */
export interface MeshEvidenceDevice {
  /** IEEE address; also the graph node id. */
  ieee_address: string;
  network_id: string;
  friendly_name: string;
  role: MeshRole;
  power: "mains" | "battery" | "unknown";
  availability: "online" | "offline" | "unknown";
  last_seen_at?: string | null;
  health_bucket: MeshHealthBucket;
  flags: MeshNodeFlag[];
  /** Inventory status, e.g. "In Zigbee2MQTT device inventory". */
  inventory_status: string;
  topology_evidence_summary: string;
  passive_observation_summary: string;
  open_issue?: MeshOpenIssue | null;
  /** Why ZigbeeLens thinks this is OK / needs attention (safe wording). */
  interpretation: string;
  /**
   * Summary of previously-seen topology links touching this device within
   * the history window. Undefined when historical data was not evaluated
   * (e.g. prototype sample fixtures).
   */
  historical_topology_summary?: string | null;
}

export interface MeshEvidenceGraphFixture {
  network_id: string;
  network_name: string;
  latest_snapshot_captured_at: string;
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
}

/* ------------------------------------------------------------------------ */
/* Labels and safe wording                                                   */
/* ------------------------------------------------------------------------ */

export function evidenceClassLabel(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Latest snapshot neighbour evidence";
    case "latest_snapshot_route":
      return "Latest route-table / next-hop evidence";
    case "historical_neighbor":
      return "Previously seen neighbour link";
    case "historical_route":
      return "Previously seen route hint";
    case "passive_derived_association":
      return "Passive-derived association";
    case "stale_low_confidence":
      return "Stale / low-confidence evidence";
  }
}

/**
 * Careful, evidence-first description of what each class does and does not
 * claim. None of these may imply live routing or device failure.
 */
export function evidenceClassDescription(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Neighbour-table entry from the most recent topology snapshot. A snapshot is point-in-time evidence; it does not prove current live routing.";
    case "latest_snapshot_route":
      return "Route-table / next-hop entry from the most recent topology snapshot. Zigbee routes change over time; this does not prove current live routing.";
    case "historical_neighbor":
      return "Link observed in previous topology snapshots but not observed in the latest snapshot. This does not prove current live routing, and its absence from the latest snapshot does not prove a failure.";
    case "historical_route":
      return "Route-table evidence observed in previous topology snapshots but not observed in the latest snapshot. This does not prove current live routing.";
    case "passive_derived_association":
      return "Investigation hint derived from passive observations over time, such as correlated availability changes or overlapping stale windows. This is not topology evidence and is not a route.";
    case "stale_low_confidence":
      return "Old or weakly supported evidence. Treat this as background context, not as a description of the current mesh.";
  }
}

/** Short badge label for an edge drawer header. */
export function evidenceClassShortLabel(cls: EvidenceClass): string {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return "Snapshot neighbour";
    case "latest_snapshot_route":
      return "Snapshot route";
    case "historical_neighbor":
      return "Previously seen link";
    case "historical_route":
      return "Previously seen route";
    case "passive_derived_association":
      return "Investigation hint";
    case "stale_low_confidence":
      return "Stale / low confidence";
  }
}

export function confidenceLabel(confidence: EvidenceConfidence): string {
  switch (confidence) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
  }
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
      return "Diagnostics limited";
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
      return "Diagnostics limited";
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

/**
 * Format a possibly-unknown count for display. Unknown or unreported values
 * must never be shown as zero — that would present missing evidence as
 * measured evidence.
 */
export function formatEvidenceCount(value: number | null | undefined): string {
  if (value == null) return "Not recorded";
  return String(value);
}

/** Format a possibly-unknown LQI value. */
export function formatLqi(value: number | null | undefined): string {
  if (value == null) return "No data";
  return String(value);
}

/** The safety copy shown above the graph. */
export const GRAPH_SAFETY_COPY =
  "This graph combines topology snapshots with historical and passive observations. " +
  "Solid links are direct snapshot evidence. Dotted or faint links are historical or derived " +
  "and should be treated as investigation hints, not proof of current live routing.";

/** Copy describing missing latest-snapshot presence for an edge. */
export function latestSnapshotStatusCopy(edge: MeshEvidenceEdge): string {
  if (edge.evidence_class === "passive_derived_association") {
    return "Not applicable — this association is derived from passive observations, not from a topology snapshot.";
  }
  if (edge.in_latest_snapshot) {
    return "Present in the latest topology snapshot.";
  }
  if (edge.latest_layout_limited) {
    return "Latest snapshot layout is limited, so absence from the latest snapshot cannot be treated as meaningful.";
  }
  return "Not observed in the latest topology snapshot. This alone does not prove the link is gone or that a device has failed.";
}
