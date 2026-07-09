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
  | "last_known_link"
  | "passive_derived_association"
  | "stale_low_confidence";

/**
 * The evidence classes live data can actually produce today: snapshot
 * evidence, recent-missing historical evidence, and passive-derived
 * investigation hints. The stale class stays in the model (types, styles
 * and drawer wording) but is not drawn or listed in the legend until a
 * live source exists for it.
 */
export const LIVE_EVIDENCE_CLASSES: EvidenceClass[] = [
  "latest_snapshot_neighbor",
  "latest_snapshot_route",
  "historical_neighbor",
  "historical_route",
  "last_known_link",
  "passive_derived_association",
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
  /** Named rules a passive-derived hint matched (backend rule ids). */
  rules_matched?: string[] | null;
  /** Concise backend-supplied facts supporting a passive-derived hint. */
  supporting_observations?: string[] | null;
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

/**
 * One repeatable diagnostic stat for the node drawer: a recorded value with
 * an optional secondary detail (e.g. the exact timestamp behind a relative
 * time). Stats are only produced for values that were actually recorded.
 */
export interface MeshDiagnosticStat {
  label: string;
  value: string;
  detail?: string;
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
  /** Recorded diagnostic stats (last seen, link presence, offline events). */
  diagnostic_stats: MeshDiagnosticStat[];
  /**
   * Summary of previously-seen topology links touching this device within
   * the history window. Undefined when historical data was not evaluated.
   */
  historical_topology_summary?: string | null;
  /**
   * Summary of passive-derived investigation hints touching this device.
   * Undefined when passive hints were not evaluated.
   */
  passive_hint_summary?: string | null;
}

/* ------------------------------------------------------------------------ */
/* Labels and safe wording                                                   */
/* ------------------------------------------------------------------------ */

// Human-facing copy lives in meshGraphCopy.ts (see docs/ubiquitous-language.md).
// Re-export here so existing imports keep working.
export {
  GRAPH_SAFETY_COPY_LIVE,
  confidenceExplanation,
  confidenceStrengthCopy as confidenceLabel,
  evidenceClassDescription,
  evidenceClassLabel,
  evidenceClassShortLabel,
  evidenceClassTooltip,
  formatEvidenceCount,
  formatLqi,
  latestSnapshotStatusCopy,
  meshHealthBucketLabel,
  meshNodeFlagLabel,
  meshRoleLabel,
} from "@/lib/meshGraphCopy";
