import { NavLink } from "react-router-dom";

/** Secondary [Snapshot] [Evidence graph] tabs within one topology network. */
export function TopologyViewTabs({ networkId }: { networkId: string }) {
  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50 ${
      isActive
        ? "border-zl-accent/40 bg-zl-accent/15 text-zl-accent"
        : "border-zl-border text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
    }`;
  return (
    <div className="flex gap-2" role="tablist" aria-label="Topology views">
      <NavLink end to={`/topology/${networkId}`} role="tab" className={tabClass}>
        Snapshot
      </NavLink>
      <NavLink to={`/topology/${networkId}/graph`} role="tab" className={tabClass}>
        Evidence graph
      </NavLink>
    </div>
  );
}
