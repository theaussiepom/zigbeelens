import {
  connectionControlsStorageKey,
  DEFAULT_CONNECTION_CONTROLS,
  loadConnectionControls,
  type ConnectionControls,
} from "@/lib/meshGraphDense";

export type GraphViewPresetId =
  | "troubleshooting"
  | "router_review"
  | "battery_devices"
  | "quiet_view"
  | "full_snapshot_links"
  | "custom";

export const GRAPH_VIEW_PRESET_IDS = [
  "troubleshooting",
  "router_review",
  "battery_devices",
  "quiet_view",
  "full_snapshot_links",
] as const;

export type NamedGraphViewPresetId = (typeof GRAPH_VIEW_PRESET_IDS)[number];

export const DEFAULT_GRAPH_VIEW_PRESET: NamedGraphViewPresetId = "troubleshooting";

export const GRAPH_VIEW_PRESET_CONTROLS: Record<NamedGraphViewPresetId, ConnectionControls> = {
  troubleshooting: {
    routeHints: true,
    bestNeighbourLinks: true,
    allNeighbourLinks: false,
    oldUncertainLinks: false,
    recentMissingLinks: true,
    lastKnownLinks: true,
    suggestedInvestigationLinks: true,
  },
  router_review: {
    routeHints: true,
    bestNeighbourLinks: true,
    allNeighbourLinks: false,
    oldUncertainLinks: false,
    recentMissingLinks: true,
    lastKnownLinks: true,
    suggestedInvestigationLinks: false,
  },
  battery_devices: {
    routeHints: false,
    bestNeighbourLinks: true,
    allNeighbourLinks: false,
    oldUncertainLinks: false,
    recentMissingLinks: false,
    lastKnownLinks: true,
    suggestedInvestigationLinks: false,
  },
  quiet_view: {
    routeHints: false,
    bestNeighbourLinks: true,
    allNeighbourLinks: false,
    oldUncertainLinks: false,
    recentMissingLinks: false,
    lastKnownLinks: false,
    suggestedInvestigationLinks: false,
  },
  full_snapshot_links: {
    routeHints: true,
    bestNeighbourLinks: true,
    allNeighbourLinks: true,
    oldUncertainLinks: true,
    recentMissingLinks: false,
    lastKnownLinks: true,
    suggestedInvestigationLinks: false,
  },
};

export function viewPresetStorageKey(networkId: string): string {
  return `zigbeelens.meshGraph.viewPreset.v1.${networkId}`;
}

export function isNamedGraphViewPresetId(value: string): value is NamedGraphViewPresetId {
  return (GRAPH_VIEW_PRESET_IDS as readonly string[]).includes(value);
}

export function controlsMatchPreset(
  controls: ConnectionControls,
  preset: NamedGraphViewPresetId,
): boolean {
  const expected = GRAPH_VIEW_PRESET_CONTROLS[preset];
  return (Object.keys(expected) as (keyof ConnectionControls)[]).every(
    (key) => controls[key] === expected[key],
  );
}

export function derivePresetFromControls(controls: ConnectionControls): GraphViewPresetId {
  for (const preset of GRAPH_VIEW_PRESET_IDS) {
    if (controlsMatchPreset(controls, preset)) return preset;
  }
  return "custom";
}

export function loadViewPreset(networkId: string): GraphViewPresetId | null {
  try {
    const raw = localStorage.getItem(viewPresetStorageKey(networkId));
    if (!raw) return null;
    if (raw === "custom" || isNamedGraphViewPresetId(raw)) return raw;
    return null;
  } catch {
    return null;
  }
}

export function saveViewPreset(networkId: string, preset: GraphViewPresetId): void {
  try {
    localStorage.setItem(viewPresetStorageKey(networkId), preset);
  } catch {
    // Storage unavailable.
  }
}

export function clearViewPreset(networkId: string): void {
  try {
    localStorage.removeItem(viewPresetStorageKey(networkId));
  } catch {
    // Nothing to clear.
  }
}

/** Initial controls for a network: honour saved state, default new users to Troubleshooting. */
export function loadInitialGraphViewState(networkId: string): {
  controls: ConnectionControls;
  preset: GraphViewPresetId;
} {
  const savedPreset = loadViewPreset(networkId);
  if (savedPreset && savedPreset !== "custom" && isNamedGraphViewPresetId(savedPreset)) {
    return {
      controls: { ...GRAPH_VIEW_PRESET_CONTROLS[savedPreset] },
      preset: savedPreset,
    };
  }

  const hasSavedControls = localStorage.getItem(connectionControlsStorageKey(networkId)) !== null;
  if (hasSavedControls || savedPreset === "custom") {
    const controls = loadConnectionControls(networkId);
    return {
      controls,
      preset: savedPreset === "custom" ? "custom" : derivePresetFromControls(controls),
    };
  }

  return {
    controls: { ...GRAPH_VIEW_PRESET_CONTROLS[DEFAULT_GRAPH_VIEW_PRESET] },
    preset: DEFAULT_GRAPH_VIEW_PRESET,
  };
}

export function resetGraphViewToDefaultPreset(): {
  controls: ConnectionControls;
  preset: NamedGraphViewPresetId;
} {
  return {
    controls: { ...GRAPH_VIEW_PRESET_CONTROLS[DEFAULT_GRAPH_VIEW_PRESET] },
    preset: DEFAULT_GRAPH_VIEW_PRESET,
  };
}

/** Legacy default controls preserved for tests and migration comparisons. */
export const LEGACY_DEFAULT_CONNECTION_CONTROLS = { ...DEFAULT_CONNECTION_CONTROLS };
