import { useRef, useState } from "react";
import { DeviceSearch } from "@/components/meshGraph/DeviceSearch";
import { ContextualReportDialog } from "@/components/reports/ContextualReportDialog";
import { useScenario } from "@/context/ScenarioContext";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { MESH_CREATE_NETWORK_REPORT_LABEL } from "@/lib/meshGraphCopy";
import { MESH_LAYOUT_MODES, type MeshLayoutMode } from "@/lib/meshGraphSmartLayout";

export function GraphToolbar({
  devices,
  edges,
  networkId,
  networkName,
  layoutMode,
  onLayoutModeChange,
  onResetLayout,
  onSelectDevice,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  networkId: string;
  networkName?: string | null;
  layoutMode: MeshLayoutMode;
  onLayoutModeChange: (mode: MeshLayoutMode) => void;
  onResetLayout: () => void;
  onSelectDevice: (device: MeshEvidenceDevice) => void;
}) {
  const { scenario } = useScenario();
  const [reportOpen, setReportOpen] = useState(false);
  const reportButtonRef = useRef<HTMLButtonElement>(null);
  const layoutModeInfo = MESH_LAYOUT_MODES.find((mode) => mode.id === layoutMode);

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <DeviceSearch devices={devices} edges={edges} onSelectDevice={onSelectDevice} />
        <label className="flex items-center gap-2 text-sm">
          <span className="text-zl-muted" id="graph-layout-mode-label">
            Layout
          </span>
          <select
            value={layoutMode}
            onChange={(event) => onLayoutModeChange(event.target.value as MeshLayoutMode)}
            aria-labelledby="graph-layout-mode-label"
            className="rounded-lg border border-zl-border bg-zl-surface-2 px-2 py-1.5 text-sm"
          >
            {MESH_LAYOUT_MODES.map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.label} — {mode.hint}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onResetLayout}
          className="rounded-lg border border-zl-border bg-zl-surface-2 px-3 py-1.5 text-sm text-zl-text hover:border-zl-accent/40"
        >
          Reset layout
        </button>
        <button
          ref={reportButtonRef}
          type="button"
          onClick={() => setReportOpen(true)}
          className="rounded-lg border border-zl-border bg-zl-surface-2 px-3 py-1.5 text-sm text-zl-text hover:border-zl-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        >
          {MESH_CREATE_NETWORK_REPORT_LABEL}
        </button>
      </div>
      {layoutModeInfo && (
        <p
          className="max-w-md text-[11px] leading-snug text-zl-muted"
          data-testid="layout-mode-description"
        >
          {layoutModeInfo.description}
        </p>
      )}
      <ContextualReportDialog
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        scenario={scenario || undefined}
        returnFocusRef={reportButtonRef}
        target={{
          scope: "network",
          networkId,
          subjectLabel: networkName?.trim() || networkId,
        }}
      />
    </div>
  );
}
