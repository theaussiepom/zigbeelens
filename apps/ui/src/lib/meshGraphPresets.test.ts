import { describe, expect, it } from "vitest";
import {
  DEFAULT_CONNECTION_CONTROLS,
  type ConnectionControls,
} from "@/lib/meshGraphDense";
import {
  GRAPH_VIEW_PRESET_CONTROLS,
  GRAPH_VIEW_PRESET_IDS,
  controlsMatchPreset,
  derivePresetFromControls,
} from "@/lib/meshGraphPresets";

describe("meshGraphPresets", () => {
  it("defines a control mapping for each named preset", () => {
    for (const preset of GRAPH_VIEW_PRESET_IDS) {
      const controls = GRAPH_VIEW_PRESET_CONTROLS[preset];
      expect(Object.keys(controls).sort()).toEqual(
        Object.keys(DEFAULT_CONNECTION_CONTROLS).sort(),
      );
    }
  });

  it("maps troubleshooting to investigation-focused defaults", () => {
    expect(GRAPH_VIEW_PRESET_CONTROLS.troubleshooting).toEqual({
      routeHints: true,
      bestNeighbourLinks: true,
      allNeighbourLinks: false,
      oldUncertainLinks: false,
      recentMissingLinks: true,
      lastKnownLinks: true,
      suggestedInvestigationLinks: true,
    });
  });

  it("maps quiet view to minimal neighbour links only", () => {
    expect(GRAPH_VIEW_PRESET_CONTROLS.quiet_view).toEqual({
      routeHints: false,
      bestNeighbourLinks: true,
      allNeighbourLinks: false,
      oldUncertainLinks: false,
      recentMissingLinks: false,
      lastKnownLinks: false,
      suggestedInvestigationLinks: false,
    });
  });

  it("maps full snapshot links to all snapshot neighbour and route layers", () => {
    expect(GRAPH_VIEW_PRESET_CONTROLS.full_snapshot_links.allNeighbourLinks).toBe(true);
    expect(GRAPH_VIEW_PRESET_CONTROLS.full_snapshot_links.routeHints).toBe(true);
    expect(GRAPH_VIEW_PRESET_CONTROLS.full_snapshot_links.oldUncertainLinks).toBe(true);
  });

  it("derives custom when controls differ from every preset", () => {
    const custom: ConnectionControls = {
      ...GRAPH_VIEW_PRESET_CONTROLS.troubleshooting,
      routeHints: false,
    };
    expect(derivePresetFromControls(custom)).toBe("custom");
    expect(controlsMatchPreset(custom, "troubleshooting")).toBe(false);
  });

  it("derives the matching preset for exact control sets", () => {
    for (const preset of GRAPH_VIEW_PRESET_IDS) {
      expect(derivePresetFromControls(GRAPH_VIEW_PRESET_CONTROLS[preset])).toBe(preset);
      expect(controlsMatchPreset(GRAPH_VIEW_PRESET_CONTROLS[preset], preset)).toBe(true);
    }
  });
});
