/** Canonical UI route helpers for Mesh / Investigate and supporting topology. */

/** Encode a network ID for use as a single path segment (not double-encoded). */
export function encodeRouteSegment(segment: string): string {
  return encodeURIComponent(segment);
}

export function investigatePath(networkId: string): string {
  return `/investigate/${encodeRouteSegment(networkId)}`;
}

export function topologySnapshotPath(networkId: string): string {
  return `/topology/${encodeRouteSegment(networkId)}`;
}

/** Legacy evidence-graph deep link retained only for redirect compatibility. */
export function legacyTopologyGraphPath(networkId: string): string {
  return `/topology/${encodeRouteSegment(networkId)}/graph`;
}

/** Compatibility bookmark for the removed standalone routers page. */
export function legacyRoutersPath(): string {
  return "/routers";
}
