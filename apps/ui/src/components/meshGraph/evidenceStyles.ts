import type { EvidenceClass, MeshHealthBucket } from "@/lib/meshEvidence";

/**
 * Strict visual grammar for evidence edges.
 *
 * Solid      → latest topology neighbour evidence
 * Dashed     → latest route-table / next-hop evidence
 * Dotted     → historical topology evidence not seen in latest snapshot
 * Ghost/faint→ passive-derived association / investigation hint
 * Muted      → stale or low-confidence evidence
 *
 * Arrowheads are added only for directional (route/next-hop) evidence; a
 * passive-derived association must never look like a route.
 */
export interface EvidenceEdgeStyle {
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
  opacity: number;
  strokeLinecap?: "butt" | "round" | "square";
}

const ZL_ACCENT = "#5b9fd4";
const ZL_MUTED = "#8b98a8";
const ZL_WATCH = "#e6b84a";

export function evidenceEdgeStyle(cls: EvidenceClass): EvidenceEdgeStyle {
  switch (cls) {
    case "latest_snapshot_neighbor":
      return { stroke: ZL_ACCENT, strokeWidth: 2, opacity: 0.9 };
    case "latest_snapshot_route":
      return { stroke: ZL_ACCENT, strokeWidth: 1.8, strokeDasharray: "8 6", opacity: 0.85 };
    case "historical_neighbor":
      return {
        stroke: ZL_MUTED,
        strokeWidth: 1.6,
        strokeDasharray: "2 6",
        opacity: 0.75,
        strokeLinecap: "round",
      };
    case "historical_route":
      return {
        stroke: ZL_MUTED,
        strokeWidth: 1.6,
        strokeDasharray: "2 6",
        opacity: 0.7,
        strokeLinecap: "round",
      };
    case "passive_derived_association":
      return {
        stroke: ZL_WATCH,
        strokeWidth: 1.4,
        strokeDasharray: "1 8",
        opacity: 0.45,
        strokeLinecap: "round",
      };
    case "stale_low_confidence":
      return { stroke: ZL_MUTED, strokeWidth: 1.2, opacity: 0.3 };
  }
}

/** SVG dash preview used by the legend so it matches the graph exactly. */
export function legendDashArray(cls: EvidenceClass): string | undefined {
  return evidenceEdgeStyle(cls).strokeDasharray;
}

/** Border treatment for a node card by health bucket. */
export function nodeBorderClass(bucket: MeshHealthBucket): string {
  switch (bucket) {
    case "healthy":
      return "border-zl-border";
    case "needs_attention":
      return "border-zl-incident/60";
    case "unavailable":
      return "border-zl-critical/60 border-dashed";
    case "diagnostics_limited":
      return "border-zl-watch/50 border-dashed";
    case "recently_unstable":
      return "border-zl-watch/60";
    case "informational":
      return "border-zl-watch/40";
    case "unknown":
      return "border-zl-border";
  }
}
