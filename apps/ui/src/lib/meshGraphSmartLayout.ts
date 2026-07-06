import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { deviceHasIssue } from "@/lib/meshGraphDense";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";

/**
 * ZigbeeLens smart layout: a Zigbee-aware, deterministic layout pipeline.
 *
 * Layout is a product feature here, not a graph-library default. Every mode
 * places nodes with plain geometry driven by Zigbee roles and observed
 * evidence — coordinator anchored, routers as the backbone, end devices as
 * satellites, limited/unknown devices grouped — instead of a generic
 * auto-layout. All placement is synchronous, stable-sorted and free of
 * randomness, so the same snapshot always renders the same picture and
 * nothing ever moves on refetch, filter, selection or drawer changes.
 *
 * Grouping uses observed topology evidence only: attaching an end device
 * near a router means "strongest observed neighbour evidence", never a
 * claim of parentage or live routing.
 */

export type MeshLayoutMode = "smart" | "backbone" | "clusters" | "health" | "manual";

export interface MeshLayoutModeInfo {
  id: MeshLayoutMode;
  label: string;
  description: string;
}

export const MESH_LAYOUT_MODES: MeshLayoutModeInfo[] = [
  {
    id: "smart",
    label: "Smart layout",
    description:
      "ZigbeeLens arranges the coordinator, router backbone, end devices and limited-evidence devices into a readable mesh evidence view.",
  },
  {
    id: "backbone",
    label: "Router backbone",
    description:
      "Infrastructure first: the coordinator and routers form the primary band, with end devices grouped quietly below.",
  },
  {
    id: "clusters",
    label: "Router clusters",
    description:
      "Groups devices around observed router neighbourhoods where evidence is available. This does not prove current live routing.",
  },
  {
    id: "health",
    label: "Health focus",
    description:
      "Devices already flagged by ZigbeeLens are placed prominently and highlighted; healthy devices stay present but quieter.",
  },
  {
    id: "manual",
    label: "Manual layout",
    description:
      "Drag devices to arrange the graph. ZigbeeLens remembers your positions on this browser.",
  },
];

export const DEFAULT_LAYOUT_MODE: MeshLayoutMode = "smart";

export interface MeshPoint {
  x: number;
  y: number;
}

/* ------------------------------------------------------------------------ */
/* Classification                                                            */
/* ------------------------------------------------------------------------ */

export interface ClassifiedDevices {
  coordinators: MeshEvidenceDevice[];
  routers: MeshEvidenceDevice[];
  endDevices: MeshEvidenceDevice[];
  /** Unknown role or topology-only placeholders — the "limited" group. */
  limited: MeshEvidenceDevice[];
}

export function classifyDevices(devices: MeshEvidenceDevice[]): ClassifiedDevices {
  const result: ClassifiedDevices = {
    coordinators: [],
    routers: [],
    endDevices: [],
    limited: [],
  };
  for (const device of devices) {
    switch (device.role) {
      case "coordinator":
        result.coordinators.push(device);
        break;
      case "router":
        result.routers.push(device);
        break;
      case "end_device":
        result.endDevices.push(device);
        break;
      case "unknown":
        result.limited.push(device);
        break;
    }
  }
  return result;
}

/* ------------------------------------------------------------------------ */
/* Evidence-based grouping                                                   */
/* ------------------------------------------------------------------------ */

/**
 * For each end device, pick the router it has the strongest observed
 * neighbour evidence with (highest recorded LQI; links with recorded LQI
 * beat links without — missing LQI is unknown, never zero). Devices with no
 * router neighbour evidence are left unassigned and join the limited group
 * visually. This is observed-evidence grouping only, never a parent claim.
 */
export function assignEndDevicesToRouters(
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
): Map<string, string> {
  const roleById = new Map(devices.map((d) => [d.ieee_address, d.role]));
  const bestByEndDevice = new Map<string, { router: string; lqi: number | null }>();

  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
    const pairs: Array<[string, string]> = [
      [edge.source, edge.target],
      [edge.target, edge.source],
    ];
    for (const [device, other] of pairs) {
      if (roleById.get(device) !== "end_device") continue;
      if (roleById.get(other) !== "router" && roleById.get(other) !== "coordinator") continue;
      const lqi = edge.lqi_latest ?? null;
      const current = bestByEndDevice.get(device);
      const better =
        !current ||
        (lqi != null && (current.lqi == null || lqi > current.lqi)) ||
        (lqi == null && current.lqi == null && other < current.router);
      if (better) bestByEndDevice.set(device, { router: other, lqi });
    }
  }

  const assignment = new Map<string, string>();
  for (const [device, { router }] of bestByEndDevice) assignment.set(device, router);
  return assignment;
}

/** Neighbour-evidence degree per device, used for stable prominence sorting. */
export function neighbourDegrees(edges: MeshEvidenceEdge[]): Map<string, number> {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    if (edge.evidence_class !== "latest_snapshot_neighbor") continue;
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  return degree;
}

/* ------------------------------------------------------------------------ */
/* Geometry                                                                  */
/* ------------------------------------------------------------------------ */

const GAP_X = 42;
const GAP_Y = 52;
const CELL_W = MESH_NODE_WIDTH + GAP_X;
const CELL_H = MESH_NODE_HEIGHT + GAP_Y;
const BAND_GAP = 140;

function stableSort(
  devices: MeshEvidenceDevice[],
  degree: Map<string, number>,
): MeshEvidenceDevice[] {
  return [...devices].sort((a, b) => {
    const dg = (degree.get(b.ieee_address) ?? 0) - (degree.get(a.ieee_address) ?? 0);
    if (dg !== 0) return dg;
    const name = a.friendly_name.localeCompare(b.friendly_name);
    if (name !== 0) return name;
    return a.ieee_address.localeCompare(b.ieee_address);
  });
}

/** Place devices in a centred grid; returns bottom Y of the block. */
function placeGrid(
  positions: Map<string, MeshPoint>,
  devices: MeshEvidenceDevice[],
  centerX: number,
  topY: number,
  columns: number,
): number {
  if (devices.length === 0) return topY;
  const cols = Math.max(1, columns);
  const rows = Math.ceil(devices.length / cols);
  for (let i = 0; i < devices.length; i += 1) {
    const row = Math.floor(i / cols);
    const inRow = row === rows - 1 ? devices.length - row * cols : cols;
    const col = i % cols;
    const rowWidth = inRow * CELL_W;
    positions.set(devices[i].ieee_address, {
      x: centerX - rowWidth / 2 + col * CELL_W,
      y: topY + row * CELL_H,
    });
  }
  return topY + rows * CELL_H;
}

interface RouterCluster {
  router: MeshEvidenceDevice;
  members: MeshEvidenceDevice[];
}

function buildClusters(
  classified: ClassifiedDevices,
  assignment: Map<string, string>,
  degree: Map<string, number>,
): { clusters: RouterCluster[]; unassigned: MeshEvidenceDevice[] } {
  const membersByRouter = new Map<string, MeshEvidenceDevice[]>();
  const unassigned: MeshEvidenceDevice[] = [];
  const routerIds = new Set(classified.routers.map((r) => r.ieee_address));
  const coordinatorIds = new Set(classified.coordinators.map((c) => c.ieee_address));

  for (const endDevice of stableSort(classified.endDevices, degree)) {
    const target = assignment.get(endDevice.ieee_address);
    if (target && (routerIds.has(target) || coordinatorIds.has(target))) {
      // End devices whose strongest evidence is the coordinator hang off the
      // first router column visually only if a router exists; otherwise they
      // stay near the coordinator via the unassigned band fallback below.
      const key = routerIds.has(target) ? target : (classified.routers[0]?.ieee_address ?? target);
      if (routerIds.has(key)) {
        const list = membersByRouter.get(key);
        if (list) list.push(endDevice);
        else membersByRouter.set(key, [endDevice]);
        continue;
      }
    }
    unassigned.push(endDevice);
  }

  const clusters = stableSort(classified.routers, degree).map((router) => ({
    router,
    members: membersByRouter.get(router.ieee_address) ?? [],
  }));
  return { clusters, unassigned };
}

function clusterColumns(memberCount: number): number {
  return memberCount <= 2 ? 1 : 2;
}

/**
 * Shared hierarchy renderer for smart/backbone/health:
 * coordinator anchor → router band (each router heads a column with its
 * end-device satellites below) → unassigned/limited group at the bottom.
 */
function placeHierarchy(
  positions: Map<string, MeshPoint>,
  classified: ClassifiedDevices,
  clusters: RouterCluster[],
  unassigned: MeshEvidenceDevice[],
  degree: Map<string, number>,
  options: { satelliteColumns: (n: number) => number; routersPerRow: number },
): void {
  // Column width per cluster depends on its satellite grid width.
  const widths = clusters.map((c) =>
    Math.max(1, options.satelliteColumns(c.members.length)) * CELL_W,
  );

  const perRow = Math.max(1, options.routersPerRow);
  const rows: number[][] = [];
  for (let i = 0; i < clusters.length; i += perRow) {
    rows.push(clusters.slice(i, i + perRow).map((_, j) => i + j));
  }

  const coordinatorY = 0;
  let bandTop = coordinatorY + MESH_NODE_HEIGHT + BAND_GAP;
  for (const row of rows) {
    const rowWidth = row.reduce((sum, idx) => sum + widths[idx], 0);
    let cursorX = -rowWidth / 2;
    let rowBottom = bandTop;
    for (const idx of row) {
      const cluster = clusters[idx];
      const width = widths[idx];
      const centerX = cursorX + width / 2;
      positions.set(cluster.router.ieee_address, {
        x: centerX - MESH_NODE_WIDTH / 2,
        y: bandTop,
      });
      const satellitesTop = bandTop + CELL_H;
      const bottom = placeGrid(
        positions,
        cluster.members,
        centerX,
        satellitesTop,
        options.satelliteColumns(cluster.members.length),
      );
      rowBottom = Math.max(rowBottom, bottom === satellitesTop ? bandTop + CELL_H : bottom);
      cursorX += width;
    }
    bandTop = rowBottom + BAND_GAP / 2;
  }

  // Coordinator(s) centred above the router band.
  const coordinators = stableSort(classified.coordinators, degree);
  placeGrid(positions, coordinators, 0, coordinatorY, coordinators.length || 1);

  // Unassigned end devices, then limited/unknown devices, grouped at the
  // bottom so "no topology evidence" reads as its own area, not scatter.
  const groupCols = Math.max(2, Math.ceil(Math.sqrt(unassigned.length + 1)));
  let groupTop = bandTop + BAND_GAP;
  if (unassigned.length > 0) {
    groupTop = placeGrid(positions, unassigned, 0, groupTop, groupCols) + BAND_GAP / 2;
  }
  const limited = stableSort(classified.limited, degree);
  if (limited.length > 0) {
    placeGrid(
      positions,
      limited,
      0,
      groupTop,
      Math.max(2, Math.ceil(Math.sqrt(limited.length))),
    );
  }
}

/** Router clusters: routers as cluster centres with satellites around them. */
function placeClusters(
  positions: Map<string, MeshPoint>,
  classified: ClassifiedDevices,
  clusters: RouterCluster[],
  unassigned: MeshEvidenceDevice[],
  degree: Map<string, number>,
): void {
  const perRow = Math.max(1, Math.ceil(Math.sqrt(clusters.length)));
  const clusterSpan = 3 * CELL_W;

  const coordinators = stableSort(classified.coordinators, degree);
  placeGrid(positions, coordinators, 0, 0, coordinators.length || 1);

  const top = MESH_NODE_HEIGHT + BAND_GAP;
  clusters.forEach((cluster, index) => {
    const row = Math.floor(index / perRow);
    const col = index % perRow;
    const rowCount = Math.min(perRow, clusters.length - row * perRow);
    const centerX = (col - (rowCount - 1) / 2) * clusterSpan;
    // Height budget: assume up to 3 satellite rows per cluster row.
    const centerY = top + row * (5 * CELL_H);
    positions.set(cluster.router.ieee_address, {
      x: centerX - MESH_NODE_WIDTH / 2,
      y: centerY,
    });
    placeGrid(positions, cluster.members, centerX, centerY + CELL_H, 2);
  });

  const bottom = top + Math.ceil(clusters.length / perRow) * (5 * CELL_H) + BAND_GAP;
  let groupTop = bottom;
  if (unassigned.length > 0) {
    groupTop =
      placeGrid(
        positions,
        unassigned,
        0,
        groupTop,
        Math.max(2, Math.ceil(Math.sqrt(unassigned.length))),
      ) +
      BAND_GAP / 2;
  }
  const limited = stableSort(classified.limited, degree);
  if (limited.length > 0) {
    placeGrid(positions, limited, 0, groupTop, Math.max(2, Math.ceil(Math.sqrt(limited.length))));
  }
}

/**
 * Health focus: same hierarchy as smart, but devices already flagged by
 * ZigbeeLens are pulled into a prominent attention band directly under the
 * coordinator. Highlighting is handled by the renderer; this only affects
 * placement. Uses existing issue/health fields only.
 */
function placeHealthFocus(
  positions: Map<string, MeshPoint>,
  devices: MeshEvidenceDevice[],
  classified: ClassifiedDevices,
  clusters: RouterCluster[],
  unassigned: MeshEvidenceDevice[],
  degree: Map<string, number>,
): void {
  placeHierarchy(positions, classified, clusters, unassigned, degree, {
    satelliteColumns: clusterColumns,
    routersPerRow: 6,
  });

  const issueDevices = stableSort(devices.filter(deviceHasIssue), degree).filter(
    (d) => d.role !== "coordinator",
  );
  if (issueDevices.length === 0) return;

  // Attention band sits above the coordinator — the most prominent spot,
  // guaranteed clear of the hierarchy below. Remaining nodes keep their
  // hierarchy positions so the mesh shape stays recognisable.
  const cols = Math.min(issueDevices.length, 6);
  const rows = Math.ceil(issueDevices.length / cols);
  const bandTop = -(rows * CELL_H) - BAND_GAP;
  placeGrid(positions, issueDevices, 0, bandTop, cols);
}

/* ------------------------------------------------------------------------ */
/* Public layout API                                                         */
/* ------------------------------------------------------------------------ */

/**
 * Compute deterministic positions for every device under the given mode.
 * Manual mode uses the smart hierarchy as its base; saved user positions are
 * applied on top by {@link applySavedPositions}.
 */
export function computeMeshLayout(
  devices: MeshEvidenceDevice[],
  edges: MeshEvidenceEdge[],
  mode: MeshLayoutMode,
): Map<string, MeshPoint> {
  const positions = new Map<string, MeshPoint>();
  const classified = classifyDevices(devices);
  const degree = neighbourDegrees(edges);
  const assignment = assignEndDevicesToRouters(devices, edges);
  const { clusters, unassigned } = buildClusters(classified, assignment, degree);

  switch (mode) {
    case "clusters":
      placeClusters(positions, classified, clusters, unassigned, degree);
      break;
    case "health":
      placeHealthFocus(positions, devices, classified, clusters, unassigned, degree);
      break;
    case "backbone":
      // Infrastructure first: one wide router band, compact satellites.
      placeHierarchy(positions, classified, clusters, unassigned, degree, {
        satelliteColumns: () => 1,
        routersPerRow: 10,
      });
      break;
    case "smart":
    case "manual":
      placeHierarchy(positions, classified, clusters, unassigned, degree, {
        satelliteColumns: clusterColumns,
        routersPerRow: 6,
      });
      break;
  }

  // Safety net: every device must have a position.
  let fallbackIndex = 0;
  for (const device of devices) {
    if (!positions.has(device.ieee_address)) {
      positions.set(device.ieee_address, {
        x: (fallbackIndex % 8) * CELL_W,
        y: -2 * CELL_H - Math.floor(fallbackIndex / 8) * CELL_H,
      });
      fallbackIndex += 1;
    }
  }
  return positions;
}

/* ------------------------------------------------------------------------ */
/* Saved manual positions                                                    */
/* ------------------------------------------------------------------------ */

const POSITIONS_SCHEMA_VERSION = "v1";

/**
 * Storage key per network and layout mode. Keyed by stable device IDs (not
 * the full graph signature) so a new snapshot never discards a user's
 * arrangement while the same devices still exist.
 */
export function positionStorageKey(storageId: string, mode: MeshLayoutMode): string {
  return `zigbeelens.meshGraph.positions.${POSITIONS_SCHEMA_VERSION}.${storageId}.${mode}`;
}

export type SavedPositions = Record<string, MeshPoint>;

export function loadSavedPositions(storageId: string, mode: MeshLayoutMode): SavedPositions {
  try {
    const raw = localStorage.getItem(positionStorageKey(storageId, mode));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: SavedPositions = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (
        typeof value === "object" &&
        value !== null &&
        typeof (value as MeshPoint).x === "number" &&
        typeof (value as MeshPoint).y === "number"
      ) {
        result[id] = { x: (value as MeshPoint).x, y: (value as MeshPoint).y };
      }
    }
    return result;
  } catch {
    return {};
  }
}

export function saveNodePosition(
  storageId: string,
  mode: MeshLayoutMode,
  ieee: string,
  point: MeshPoint,
): SavedPositions {
  const current = loadSavedPositions(storageId, mode);
  const next = { ...current, [ieee]: point };
  try {
    localStorage.setItem(positionStorageKey(storageId, mode), JSON.stringify(next));
  } catch {
    // Storage full/unavailable: dragging still works for the session.
  }
  return next;
}

export function clearSavedPositions(storageId: string, mode: MeshLayoutMode): void {
  try {
    localStorage.removeItem(positionStorageKey(storageId, mode));
  } catch {
    // Ignore storage errors.
  }
}

/**
 * Overlay saved user positions on generated ones. Saved entries for devices
 * that no longer exist are ignored; new devices keep their generated spot.
 */
export function applySavedPositions(
  generated: Map<string, MeshPoint>,
  saved: SavedPositions,
): Map<string, MeshPoint> {
  const result = new Map(generated);
  for (const [ieee, point] of Object.entries(saved)) {
    if (result.has(ieee)) result.set(ieee, point);
  }
  return result;
}
