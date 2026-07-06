import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { MeshEvidenceDevice, MeshNodeFlag } from "@/lib/meshEvidence";
import { meshNodeFlagLabel, meshRoleLabel } from "@/lib/meshEvidence";
import { nodeBorderClass } from "@/components/meshGraph/evidenceStyles";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";

export type MeshDeviceFlowNode = Node<{ device: MeshEvidenceDevice }, "meshDevice">;

const FLAG_CHIP_CLASS: Record<MeshNodeFlag, string> = {
  unavailable: "border-zl-critical/40 bg-zl-critical/15 text-zl-critical",
  needs_attention: "border-zl-incident/40 bg-zl-incident/15 text-zl-incident",
  diagnostics_limited: "border-zl-watch/40 bg-zl-watch/15 text-zl-watch",
  interview_failure: "border-zl-incident/40 bg-zl-incident/15 text-zl-incident",
  weak_link_candidate: "border-zl-watch/40 bg-zl-watch/15 text-zl-watch",
  router_risk_candidate: "border-zl-incident/40 bg-zl-incident/15 text-zl-incident",
  battery_sleepy: "border-zl-border bg-zl-surface-2 text-zl-muted",
};

function roleGlyph(device: MeshEvidenceDevice): string {
  switch (device.role) {
    case "coordinator":
      return "C";
    case "router":
      return "R";
    case "end_device":
      return "E";
  }
}

/**
 * Compact node card: role, name and at most two status chips. Everything
 * else lives in the node drawer so the graph stays readable.
 */
export function MeshDeviceNode({ data, selected }: NodeProps<MeshDeviceFlowNode>) {
  const device = data.device;
  const chips = device.flags.slice(0, 2);
  const extraFlagCount = device.flags.length - chips.length;

  return (
    <div
      data-testid={`mesh-node-${device.ieee_address}`}
      style={{ width: MESH_NODE_WIDTH, height: MESH_NODE_HEIGHT }}
      className={`flex cursor-pointer flex-col justify-between rounded-lg border bg-zl-surface px-3 py-2 text-left shadow-sm transition-colors ${nodeBorderClass(
        device.health_bucket,
      )} ${selected ? "ring-2 ring-zl-accent/60" : "hover:border-zl-accent/40"}`}
    >
      <Handle type="target" position={Position.Top} className="!pointer-events-none !opacity-0" />
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border text-[10px] font-bold ${
            device.role === "coordinator"
              ? "border-zl-accent/50 bg-zl-accent/20 text-zl-accent"
              : device.role === "router"
                ? "border-zl-accent/30 bg-zl-accent/10 text-zl-accent"
                : "border-zl-border bg-zl-surface-2 text-zl-muted"
          }`}
        >
          {roleGlyph(device)}
        </span>
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-zl-text">{device.friendly_name}</div>
          <div className="text-[10px] text-zl-muted">{meshRoleLabel(device.role)}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {chips.length === 0 ? (
          <span className="rounded-full border border-zl-healthy/30 bg-zl-healthy/10 px-1.5 py-px text-[9px] font-medium text-zl-healthy">
            Healthy
          </span>
        ) : (
          chips.map((flag) => (
            <span
              key={flag}
              className={`rounded-full border px-1.5 py-px text-[9px] font-medium ${FLAG_CHIP_CLASS[flag]}`}
            >
              {meshNodeFlagLabel(flag)}
            </span>
          ))
        )}
        {extraFlagCount > 0 && (
          <span className="rounded-full border border-zl-border bg-zl-surface-2 px-1.5 py-px text-[9px] text-zl-muted">
            +{extraFlagCount}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!pointer-events-none !opacity-0" />
    </div>
  );
}
