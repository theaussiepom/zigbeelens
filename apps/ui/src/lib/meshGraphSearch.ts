/**
 * Device search for the Mesh Evidence Graph.
 *
 * Frontend-only search over the devices the graph already knows about:
 * inventory devices, latest-snapshot nodes, topology-only placeholders and
 * edge endpoints. Ranking is deterministic — the same query over the same
 * devices always yields the same order regardless of input order.
 */

import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { meshRoleLabel } from "@/lib/meshGraphCopy";

/** Deterministic result cap: enough to scan, never a full device dump. */
export const MAX_DEVICE_SEARCH_RESULTS = 12;

/**
 * Match tiers, lower is better. Ordering within a tier is deterministic:
 * needs-attention/issue first, unavailable before available, latest topology
 * evidence before limited-only, then friendly name, then IEEE.
 */
export const SEARCH_RANK = {
  exactName: 1,
  namePrefix: 2,
  nameSubstring: 3,
  ieee: 4,
  manufacturerModel: 5,
  statusOrType: 6,
} as const;

/** Badges a search result can carry. All approved product language. */
export type DeviceSearchBadge =
  | "Coordinator"
  | "Router"
  | "End device"
  | "Unavailable"
  | "Needs attention"
  | "Limited topology evidence"
  | "Recent missing evidence"
  | "Suggested investigation link";

export interface DeviceSearchResult {
  device: MeshEvidenceDevice;
  rank: number;
  badges: DeviceSearchBadge[];
  /**
   * Human note explaining why an inventory-known device may not be visible
   * in the current graph. Null when the device has latest snapshot evidence.
   */
  limitedTopologyNote: string | null;
}

export const LIMITED_TOPOLOGY_SEARCH_NOTE =
  "Known device. Limited topology evidence in the latest snapshot.";

function hasNeedsAttention(device: MeshEvidenceDevice): boolean {
  return (
    device.flags.includes("needs_attention") ||
    device.health_bucket === "needs_attention" ||
    Boolean(device.open_issue)
  );
}

function isUnavailable(device: MeshEvidenceDevice): boolean {
  return device.availability === "offline" || device.flags.includes("unavailable");
}

/** Whether the device has latest-snapshot topology evidence. */
function hasLatestTopologyEvidence(device: MeshEvidenceDevice): boolean {
  return device.in_latest_snapshot === true;
}

/** Evidence-derived context per device: recent missing / passive hints. */
export interface DeviceEvidenceContext {
  recentMissing: Set<string>;
  suggestedInvestigation: Set<string>;
}

export function collectDeviceEvidenceContext(
  edges: MeshEvidenceEdge[],
): DeviceEvidenceContext {
  const recentMissing = new Set<string>();
  const suggestedInvestigation = new Set<string>();
  for (const edge of edges) {
    if (
      edge.evidence_class === "historical_neighbor" ||
      edge.evidence_class === "historical_route"
    ) {
      recentMissing.add(edge.source);
      recentMissing.add(edge.target);
    } else if (edge.evidence_class === "passive_derived_association") {
      suggestedInvestigation.add(edge.source);
      suggestedInvestigation.add(edge.target);
    }
  }
  return { recentMissing, suggestedInvestigation };
}

export function deviceSearchBadges(
  device: MeshEvidenceDevice,
  context: DeviceEvidenceContext,
): DeviceSearchBadge[] {
  const badges: DeviceSearchBadge[] = [];
  if (isUnavailable(device)) badges.push("Unavailable");
  if (hasNeedsAttention(device)) badges.push("Needs attention");
  if (!hasLatestTopologyEvidence(device)) badges.push("Limited topology evidence");
  if (context.recentMissing.has(device.ieee_address)) badges.push("Recent missing evidence");
  if (context.suggestedInvestigation.has(device.ieee_address)) {
    badges.push("Suggested investigation link");
  }
  if (device.role === "coordinator") badges.push("Coordinator");
  else if (device.role === "router") badges.push("Router");
  else if (device.role === "end_device") badges.push("End device");
  return badges;
}

/**
 * Searchable status/type terms for one device. All lowercase; a status query
 * matches when it is a substring of any term.
 */
function statusTerms(device: MeshEvidenceDevice, context: DeviceEvidenceContext): string[] {
  const terms: string[] = [meshRoleLabel(device.role).toLowerCase()];
  if (device.power === "battery") terms.push("battery");
  if (device.power === "mains") terms.push("mains");
  if (device.availability === "online") terms.push("available", "online");
  if (isUnavailable(device)) terms.push("unavailable", "offline");
  if (hasNeedsAttention(device)) terms.push("needs attention");
  if (!hasLatestTopologyEvidence(device)) {
    terms.push("limited topology", "limited topology evidence");
  }
  if (context.recentMissing.has(device.ieee_address)) terms.push("recent missing");
  if (context.suggestedInvestigation.has(device.ieee_address)) {
    terms.push("suggested investigation");
  }
  if (device.flags.includes("battery_sleepy")) terms.push("sleepy");
  return terms;
}

/** Rank one device against a normalized query. Null when it does not match. */
function rankDevice(
  device: MeshEvidenceDevice,
  query: string,
  context: DeviceEvidenceContext,
): number | null {
  const name = device.friendly_name.toLowerCase();
  if (name === query) return SEARCH_RANK.exactName;
  if (name.startsWith(query)) return SEARCH_RANK.namePrefix;
  if (name.includes(query)) return SEARCH_RANK.nameSubstring;
  const ieee = device.ieee_address.toLowerCase();
  if (ieee.includes(query) || ieee.replace(/^0x/, "").includes(query.replace(/^0x/, ""))) {
    return SEARCH_RANK.ieee;
  }
  const manufacturer = device.manufacturer?.toLowerCase() ?? "";
  const model = device.model?.toLowerCase() ?? "";
  if (
    (manufacturer && manufacturer.includes(query)) ||
    (model && model.includes(query))
  ) {
    return SEARCH_RANK.manufacturerModel;
  }
  if (statusTerms(device, context).some((term) => term.includes(query))) {
    return SEARCH_RANK.statusOrType;
  }
  return null;
}

function compareResults(a: DeviceSearchResult, b: DeviceSearchResult): number {
  if (a.rank !== b.rank) return a.rank - b.rank;
  const aAttention = hasNeedsAttention(a.device) ? 0 : 1;
  const bAttention = hasNeedsAttention(b.device) ? 0 : 1;
  if (aAttention !== bAttention) return aAttention - bAttention;
  const aUnavailable = isUnavailable(a.device) ? 0 : 1;
  const bUnavailable = isUnavailable(b.device) ? 0 : 1;
  if (aUnavailable !== bUnavailable) return aUnavailable - bUnavailable;
  const aTopology = hasLatestTopologyEvidence(a.device) ? 0 : 1;
  const bTopology = hasLatestTopologyEvidence(b.device) ? 0 : 1;
  if (aTopology !== bTopology) return aTopology - bTopology;
  const byName = a.device.friendly_name.localeCompare(b.device.friendly_name);
  if (byName !== 0) return byName;
  return a.device.ieee_address.localeCompare(b.device.ieee_address);
}

/**
 * Search all known devices. Returns deterministic, ranked results capped at
 * MAX_DEVICE_SEARCH_RESULTS. An empty/whitespace query returns no results —
 * the search UI shows nothing until the user has typed.
 */
export function searchDevices(
  query: string,
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
): DeviceSearchResult[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  const context = collectDeviceEvidenceContext(edges);
  const results: DeviceSearchResult[] = [];
  for (const device of devices) {
    const rank = rankDevice(device, normalized, context);
    if (rank == null) continue;
    results.push({
      device,
      rank,
      badges: deviceSearchBadges(device, context),
      limitedTopologyNote:
        device.in_inventory && !hasLatestTopologyEvidence(device)
          ? LIMITED_TOPOLOGY_SEARCH_NOTE
          : null,
    });
  }
  results.sort(compareResults);
  return results.slice(0, MAX_DEVICE_SEARCH_RESULTS);
}
