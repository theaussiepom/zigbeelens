import { Position, type NodeHandle } from "@xyflow/react";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";
import type { MeshPoint } from "@/lib/meshGraphSmartLayout";

const HANDLE_SIZE = 6;

/**
 * Static handle geometry for all four sides so edges can render before (or
 * without) DOM measurement — required for deterministic first paint and jsdom
 * tests. Ids must match {@link MeshDeviceNode}.
 */
export function meshNodeStaticHandles(
  width: number = MESH_NODE_WIDTH,
  height: number = MESH_NODE_HEIGHT,
): NodeHandle[] {
  const cx = width / 2;
  const cy = height / 2;
  return [
    { id: "s-top", type: "source", position: Position.Top, x: cx, y: 0, width: HANDLE_SIZE, height: HANDLE_SIZE },
    { id: "t-top", type: "target", position: Position.Top, x: cx, y: 0, width: HANDLE_SIZE, height: HANDLE_SIZE },
    {
      id: "s-bottom",
      type: "source",
      position: Position.Bottom,
      x: cx,
      y: height,
      width: HANDLE_SIZE,
      height: HANDLE_SIZE,
    },
    {
      id: "t-bottom",
      type: "target",
      position: Position.Bottom,
      x: cx,
      y: height,
      width: HANDLE_SIZE,
      height: HANDLE_SIZE,
    },
    { id: "s-left", type: "source", position: Position.Left, x: 0, y: cy, width: HANDLE_SIZE, height: HANDLE_SIZE },
    { id: "t-left", type: "target", position: Position.Left, x: 0, y: cy, width: HANDLE_SIZE, height: HANDLE_SIZE },
    {
      id: "s-right",
      type: "source",
      position: Position.Right,
      x: width,
      y: cy,
      width: HANDLE_SIZE,
      height: HANDLE_SIZE,
    },
    {
      id: "t-right",
      type: "target",
      position: Position.Right,
      x: width,
      y: cy,
      width: HANDLE_SIZE,
      height: HANDLE_SIZE,
    },
  ];
}

export interface NodeBounds {
  x: number;
  y: number;
  width?: number;
  height?: number;
}

/** Map a border side to React Flow handle ids on {@link MeshDeviceNode}. */
export function handleIdsForPositions(positions: {
  sourcePosition: Position;
  targetPosition: Position;
}): { sourceHandle: string; targetHandle: string } {
  const id = (pos: Position) => {
    switch (pos) {
      case Position.Top:
        return "top";
      case Position.Bottom:
        return "bottom";
      case Position.Left:
        return "left";
      case Position.Right:
        return "right";
      default:
        return "bottom";
    }
  };
  return {
    sourceHandle: `s-${id(positions.sourcePosition)}`,
    targetHandle: `t-${id(positions.targetPosition)}`,
  };
}

/** Centre of a node card from its top-left layout position. */
export function nodeCenter(
  pos: MeshPoint,
  width: number = MESH_NODE_WIDTH,
  height: number = MESH_NODE_HEIGHT,
): { x: number; y: number } {
  return { x: pos.x + width / 2, y: pos.y + height / 2 };
}

/**
 * Pick which side of each node box an edge should attach to so the line
 * leaves toward its neighbour instead of always using top/bottom ports
 * (which forces 90°/180° bends for side-by-side or upward links).
 *
 * Uses the dominant axis between centres: mostly-vertical links use
 * top/bottom; mostly-horizontal links use left/right.
 */
export function borderPositionsForEdge(
  source: NodeBounds,
  target: NodeBounds,
): { sourcePosition: Position; targetPosition: Position } {
  const sw = source.width ?? MESH_NODE_WIDTH;
  const sh = source.height ?? MESH_NODE_HEIGHT;
  const tw = target.width ?? MESH_NODE_WIDTH;
  const th = target.height ?? MESH_NODE_HEIGHT;

  const sc = nodeCenter(source, sw, sh);
  const tc = nodeCenter(target, tw, th);
  const dx = tc.x - sc.x;
  const dy = tc.y - sc.y;

  if (dx === 0 && dy === 0) {
    return { sourcePosition: Position.Bottom, targetPosition: Position.Top };
  }

  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);

  if (absDy >= absDx) {
    return dy > 0
      ? { sourcePosition: Position.Bottom, targetPosition: Position.Top }
      : { sourcePosition: Position.Top, targetPosition: Position.Bottom };
  }

  return dx > 0
    ? { sourcePosition: Position.Right, targetPosition: Position.Left }
    : { sourcePosition: Position.Left, targetPosition: Position.Right };
}
