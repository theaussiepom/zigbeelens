import { describe, expect, it } from "vitest";
import { LIVE_EVIDENCE_CLASSES } from "@/lib/meshEvidence";
import {
  FORBIDDEN_USER_FACING_PHRASES,
  GRAPH_SAFETY_COPY_LIVE,
  CONNECTION_CONTROL_COPY,
  CONNECTIONS_EXPLAINER,
  DEVICE_DETAILS_PANEL_LABEL,
  DEVICE_SECTION_RECENT_MISSING,
  DEVICE_SECTION_STATUS,
  DEVICE_SECTION_SUMMARY,
  DEVICE_SECTION_TOPOLOGY,
  INVESTIGATION_EMPTY_COPY,
  INVESTIGATION_PANEL_SUBTITLE,
  INVESTIGATION_SECTION_DOES_NOT_PROVE,
  INVESTIGATION_SECTION_WHY,
  LINK_DETAILS_PANEL_LABEL,
  LINK_SECTION_DOES_NOT_PROVE,
  LINK_SECTION_SUPPORTING,
  LINK_SECTION_WHAT_IT_MEANS,
  LINK_SECTION_WHY_DRAWN,
  evidenceClassDescription,
  evidenceClassLabel,
  evidenceClassShortLabel,
  evidenceClassTooltip,
  findForbiddenUserFacingPhrases,
  linkDoesNotProveCopy,
  linkNeedsDoesNotProve,
} from "@/lib/meshGraphCopy";
import type { MeshEvidenceEdge } from "@/lib/meshEvidence";
import { MESH_LAYOUT_MODES } from "@/lib/meshGraphSmartLayout";

function sampleEdge(cls: MeshEvidenceEdge["evidence_class"]): MeshEvidenceEdge {
  return {
    id: "e1",
    network_id: "home",
    source: "0xa",
    target: "0xb",
    evidence_class: cls,
    confidence: "medium",
    directional: cls.includes("route"),
    in_latest_snapshot: cls.startsWith("latest_"),
    limitations: [],
    suggested_investigation: [],
  };
}

describe("meshGraphCopy ubiquitous language", () => {
  it("uses approved labels for every live evidence class", () => {
    expect(evidenceClassLabel("latest_snapshot_neighbor")).toBe(
      "Latest snapshot neighbour link",
    );
    expect(evidenceClassLabel("latest_snapshot_route")).toBe("Route hint");
    expect(evidenceClassLabel("historical_neighbor")).toBe("Recent missing link");
    expect(evidenceClassLabel("historical_route")).toBe("Recent missing route hint");
    expect(evidenceClassLabel("last_known_link")).toBe("Last known link");
    expect(evidenceClassLabel("passive_derived_association")).toBe(
      "Suggested investigation link",
    );
    for (const cls of LIVE_EVIDENCE_CLASSES) {
      expect(evidenceClassLabel(cls).length).toBeGreaterThan(0);
      expect(evidenceClassDescription(cls).length).toBeGreaterThan(0);
      expect(evidenceClassShortLabel(cls).length).toBeGreaterThan(0);
      expect(evidenceClassTooltip(cls).length).toBeGreaterThan(0);
    }
  });

  it("uses details-panel section labels, never drawer", () => {
    const labels = [
      DEVICE_DETAILS_PANEL_LABEL,
      LINK_DETAILS_PANEL_LABEL,
      LINK_SECTION_WHAT_IT_MEANS,
      LINK_SECTION_WHY_DRAWN,
      LINK_SECTION_SUPPORTING,
      LINK_SECTION_DOES_NOT_PROVE,
      DEVICE_SECTION_SUMMARY,
      DEVICE_SECTION_STATUS,
      DEVICE_SECTION_TOPOLOGY,
      DEVICE_SECTION_RECENT_MISSING,
      INVESTIGATION_SECTION_WHY,
      INVESTIGATION_SECTION_DOES_NOT_PROVE,
    ];
    for (const label of labels) {
      expect(label.toLowerCase()).not.toContain("drawer");
    }
  });

  it("frames the safety banner as an evidence view, not a live routing map", () => {
    expect(GRAPH_SAFETY_COPY_LIVE).toMatch(/evidence view/i);
    expect(GRAPH_SAFETY_COPY_LIVE).toMatch(/not a live routing map/i);
    expect(findForbiddenUserFacingPhrases(GRAPH_SAFETY_COPY_LIVE)).toEqual([]);
  });

  it("keeps connection-control and layout copy free of forbidden phrases", () => {
    const blobs = [
      JSON.stringify(CONNECTION_CONTROL_COPY),
      JSON.stringify(CONNECTIONS_EXPLAINER),
      INVESTIGATION_PANEL_SUBTITLE,
      INVESTIGATION_EMPTY_COPY,
      ...MESH_LAYOUT_MODES.map((mode) => `${mode.label} ${mode.hint} ${mode.description}`),
    ];
    for (const blob of blobs) {
      expect(findForbiddenUserFacingPhrases(blob)).toEqual([]);
    }
  });

  it("shows What this does not prove only for evidence that can be misread", () => {
    expect(linkNeedsDoesNotProve(sampleEdge("latest_snapshot_neighbor"))).toBe(false);
    expect(linkNeedsDoesNotProve(sampleEdge("latest_snapshot_route"))).toBe(true);
    expect(linkNeedsDoesNotProve(sampleEdge("historical_neighbor"))).toBe(true);
    expect(linkNeedsDoesNotProve(sampleEdge("passive_derived_association"))).toBe(true);
    expect(
      linkNeedsDoesNotProve({
        ...sampleEdge("latest_snapshot_neighbor"),
        issue_related: true,
      }),
    ).toBe(true);
  });

  it("adds limited-layout practical limitation when relevant", () => {
    const lines = linkDoesNotProveCopy({
      ...sampleEdge("historical_neighbor"),
      latest_layout_limited: true,
    });
    expect(lines.some((line) => /limited topology evidence/i.test(line))).toBe(true);
  });

  it("exports the forbidden-phrase list used by UI wording sweeps", () => {
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("drawer");
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("root cause");
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("parent router");
    expect(FORBIDDEN_USER_FACING_PHRASES).toContain("nothing to see");
  });
});
