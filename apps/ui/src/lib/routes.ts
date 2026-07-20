/** Canonical UI route helpers for Mesh / Investigate and supporting topology. */

export function investigatePath(networkId: string): string {
  return `/investigate/${networkId}`;
}

export function topologySnapshotPath(networkId: string): string {
  return `/topology/${networkId}`;
}

/** Legacy evidence-graph deep link retained only for redirect compatibility. */
export function legacyTopologyGraphPath(networkId: string): string {
  return `/topology/${networkId}/graph`;
}
