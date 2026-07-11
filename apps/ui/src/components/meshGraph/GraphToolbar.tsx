import { DeviceSearch } from "@/components/meshGraph/DeviceSearch";
import { EvidenceReportMenu } from "@/components/meshGraph/EvidenceReportMenu";
import type { InvestigationCard } from "@/lib/api";
import { buildMeshEvidenceReport } from "@/lib/meshEvidenceReport";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import { MESH_LAYOUT_MODES, type MeshLayoutMode } from "@/lib/meshGraphSmartLayout";

export function GraphToolbar({
  devices,
  edges,
  investigations,
  networkId,
  networkName,
  latestSnapshotCapturedAt,
  selectedNodeId,
  layoutMode,
  onLayoutModeChange,
  onResetLayout,
  onSelectDevice,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  investigations: InvestigationCard[];
  networkId: string;
  networkName?: string | null;
  latestSnapshotCapturedAt?: string | null;
  selectedNodeId: string | null;
  layoutMode: MeshLayoutMode;
  onLayoutModeChange: (mode: MeshLayoutMode) => void;
  onResetLayout: () => void;
  onSelectDevice: (device: MeshEvidenceDevice) => void;
}) {
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
        <EvidenceReportMenu
          buildReport={() =>
            buildMeshEvidenceReport({
              networkId,
              networkName,
              latestSnapshotCapturedAt,
              generatedAt: new Date(),
              devices,
              edges,
              investigations,
              // Snapshot compare is device-led (in the Device details
              // panel), so reports carry no whole-network compare section.
              compare: null,
              selectedDevice: selectedNodeId
                ? (devices.find((device) => device.ieee_address === selectedNodeId) ?? null)
                : null,
            })
          }
        />
      </div>
      {layoutModeInfo && (
        <p
          className="max-w-md text-[11px] leading-snug text-zl-muted"
          data-testid="layout-mode-description"
        >
          {layoutModeInfo.description}
        </p>
      )}
    </div>
  );
}
