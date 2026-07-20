import { NavLink } from "react-router-dom";
import { investigatePath, topologySnapshotPath } from "@/lib/routes";

/** Per-network Investigate / Raw snapshot navigation links. */
export function TopologyViewTabs({ networkId }: { networkId: string }) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50 ${
      isActive
        ? "border-zl-accent/40 bg-zl-accent/15 text-zl-accent"
        : "border-zl-border text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
    }`;
  return (
    <nav className="flex gap-2" aria-label="Network investigation views">
      <NavLink to={investigatePath(networkId)} className={linkClass}>
        Investigate
      </NavLink>
      <NavLink end to={topologySnapshotPath(networkId)} className={linkClass}>
        Raw snapshot
      </NavLink>
    </nav>
  );
}
