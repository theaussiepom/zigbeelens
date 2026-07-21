import { describe, expect, it } from "vitest";
import { ReportRowOperationRegistry } from "./reportRowOperations";

describe("ReportRowOperationRegistry", () => {
  it("allows concurrent operations on different report IDs", () => {
    const registry = new ReportRowOperationRegistry();
    expect(registry.begin("a", "download")).toBe(true);
    expect(registry.begin("b", "copy")).toBe(true);
    expect(registry.isBusy("a")).toBe(true);
    expect(registry.isBusy("b")).toBe(true);
    registry.end("a");
    expect(registry.isBusy("a")).toBe(false);
    expect(registry.isBusy("b")).toBe(true);
    expect(registry.snapshot()).toEqual(new Set(["b"]));
  });

  it("refuses a second operation on the same report ID across actions", () => {
    const registry = new ReportRowOperationRegistry();
    expect(registry.begin("a", "copy")).toBe(true);
    expect(registry.begin("a", "download")).toBe(false);
    expect(registry.begin("a", "delete")).toBe(false);
    expect(registry.operation("a")).toBe("copy");
    registry.end("a");
    expect(registry.begin("a", "download")).toBe(true);
  });

  it("out-of-order completion only clears the owned report", () => {
    const registry = new ReportRowOperationRegistry();
    registry.begin("a", "download");
    registry.begin("b", "copy");
    registry.end("b");
    expect(registry.isBusy("a")).toBe(true);
    expect(registry.isBusy("b")).toBe(false);
    registry.end("a");
    expect(registry.snapshot().size).toBe(0);
  });

  it("rapid double begin yields one owner", () => {
    const registry = new ReportRowOperationRegistry();
    expect(registry.begin("a", "download")).toBe(true);
    expect(registry.begin("a", "download")).toBe(false);
  });

  it("clear empties the registry for a later mount", () => {
    const registry = new ReportRowOperationRegistry();
    registry.begin("a", "delete");
    registry.clear();
    expect(registry.snapshot().size).toBe(0);
    expect(registry.begin("a", "download")).toBe(true);
  });
});
