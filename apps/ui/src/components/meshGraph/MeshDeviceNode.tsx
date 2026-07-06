import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { MeshEvidenceDevice, MeshNodeFlag } from "@/lib/meshEvidence";
import { meshHealthBucketLabel, meshNodeFlagLabel, meshRoleLabel } from "@/lib/meshEvidence";
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
    case "unknown":
      return "?";
  }
}

const SIDE_HANDLES: Array<{ id: string; type: "source" | "target"; position: Position }> = [
  { id: "s-top", type: "source", position: Position.Top },
  { id: "t-top", type: "target", position: Position.Top },
  { id: "s-bottom", type: "source", position: Position.Bottom },
  { id: "t-bottom", type: "target", position: Position.Bottom },
  { id: "s-left", type: "source", position: Position.Left },
  { id: "t-left", type: "target", position: Position.Left },
  { id: "s-right", type: "source", position: Position.Right },
  { id: "t-right", type: "target", position: Position.Right },
];

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
      {SIDE_HANDLES.map((handle) => (
        <Handle
          key={handle.id}
          id={handle.id}
          type={handle.type}
          position={handle.position}
          className="!pointer-events-none !h-2 !w-2 !border-0 !bg-transparent !opacity-0"
        />
      ))}
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
          device.health_bucket === "healthy" ? (
            <span className="rounded-full border border-zl-healthy/30 bg-zl-healthy/10 px-1.5 py-px text-[9px] font-medium text-zl-healthy">
              Healthy
            </span>
          ) : (
            // Never claim health for devices without passive observations
            // (e.g. topology-only placeholder endpoints).
            <span className="rounded-full border border-zl-border bg-zl-surface-2 px-1.5 py-px text-[9px] font-medium text-zl-muted">
              {meshHealthBucketLabel(device.health_bucket)}
            </span>
          )
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
    </div>
  );
}
