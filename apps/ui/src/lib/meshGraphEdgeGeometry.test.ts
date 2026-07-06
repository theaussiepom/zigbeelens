import { Position } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { MESH_NODE_HEIGHT, MESH_NODE_WIDTH } from "@/lib/meshGraphLayout";
import { borderPositionsForEdge, handleIdsForPositions } from "@/lib/meshGraphEdgeGeometry";

describe("borderPositionsForEdge", () => {
  const box = (x: number, y: number) => ({
    x,
    y,
    width: MESH_NODE_WIDTH,
    height: MESH_NODE_HEIGHT,
  });

  it("uses top/bottom ports for mostly-vertical links", () => {
    expect(borderPositionsForEdge(box(0, 0), box(0, 200))).toEqual({
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
    expect(borderPositionsForEdge(box(0, 200), box(0, 0))).toEqual({
      sourcePosition: Position.Top,
      targetPosition: Position.Bottom,
    });
  });

  it("uses left/right ports for mostly-horizontal links", () => {
    expect(borderPositionsForEdge(box(0, 0), box(400, 0))).toEqual({
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
    expect(borderPositionsForEdge(box(400, 0), box(0, 0))).toEqual({
      sourcePosition: Position.Left,
      targetPosition: Position.Right,
    });
  });

  it("prefers vertical ports when dy dominates dx", () => {
    expect(borderPositionsForEdge(box(0, 0), box(80, 200))).toEqual({
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
  });

  it("prefers horizontal ports when dx dominates dy", () => {
    expect(borderPositionsForEdge(box(0, 0), box(400, 80))).toEqual({
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
  });
});

describe("handleIdsForPositions", () => {
  it("maps border sides to mesh node handle ids", () => {
    expect(
      handleIdsForPositions({
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      }),
    ).toEqual({ sourceHandle: "s-right", targetHandle: "t-left" });
  });
});
