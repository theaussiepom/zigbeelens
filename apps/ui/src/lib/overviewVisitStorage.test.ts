import { beforeEach, describe, expect, it } from "vitest";
import {
  OVERVIEW_LAST_VIEWED_STORAGE_KEY,
  OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY,
  OVERVIEW_NATIVE_VISIT_SCOPE,
  overviewVisitScope,
  readOverviewLastViewedAt,
  resolveOverviewPreviousLastViewedAt,
  writeOverviewLastViewedAt,
} from "./overviewVisitStorage";

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const store = { ...initial };
  return {
    get length() {
      return Object.keys(store).length;
    },
    clear() {
      for (const key of Object.keys(store)) delete store[key];
    },
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    key() {
      return null;
    },
    removeItem(key: string) {
      delete store[key];
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
  } as Storage;
}

describe("overviewVisitStorage", () => {
  const nativeScope = overviewVisitScope("");
  const scenarioAScope = overviewVisitScope("scenario-a");
  const scenarioBScope = overviewVisitScope("scenario-b");

  beforeEach(() => {
    localStorage.clear();
  });

  it("defines distinct stable scopes for native and named data sources", () => {
    expect(nativeScope).toBe(OVERVIEW_NATIVE_VISIT_SCOPE);
    expect(scenarioAScope).toBe("scenario:scenario-a");
    expect(scenarioBScope).not.toBe(scenarioAScope);
  });

  it("returns null when no previous timestamp exists", () => {
    expect(readOverviewLastViewedAt(nativeScope)).toBeNull();
    expect(readOverviewLastViewedAt(scenarioAScope)).toBeNull();
  });

  it("stores and reads boundaries independently by source scope", () => {
    writeOverviewLastViewedAt(nativeScope, "2026-07-10T12:00:00.000Z");
    writeOverviewLastViewedAt(scenarioAScope, "2026-07-11T08:00:00.000Z");

    expect(readOverviewLastViewedAt(nativeScope)).toBe("2026-07-10T12:00:00.000Z");
    expect(readOverviewLastViewedAt(scenarioAScope)).toBe("2026-07-11T08:00:00.000Z");
    expect(readOverviewLastViewedAt(scenarioBScope)).toBeNull();
  });

  it("treats invalid scoped timestamps as missing and removes them", () => {
    localStorage.setItem(
      OVERVIEW_LAST_VIEWED_STORAGE_KEY,
      JSON.stringify({ [nativeScope]: "not-a-date", [scenarioAScope]: "2026-07-11T08:00:00Z" }),
    );

    expect(readOverviewLastViewedAt(nativeScope)).toBeNull();
    expect(readOverviewLastViewedAt(scenarioAScope)).toBe("2026-07-11T08:00:00Z");
    expect(JSON.parse(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY) ?? "{}")).toEqual({
      [scenarioAScope]: "2026-07-11T08:00:00Z",
    });
  });

  it("supports an injected storage for tests", () => {
    const storage = memoryStorage();
    writeOverviewLastViewedAt(scenarioAScope, "2026-07-11T08:00:00.000Z", storage);
    expect(readOverviewLastViewedAt(scenarioAScope, storage)).toBe(
      "2026-07-11T08:00:00.000Z",
    );
  });

  it("migrates the old global v1 boundary only into native scope", () => {
    const legacy = "2026-07-09T12:00:00.000Z";
    const storage = memoryStorage({ [OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY]: legacy });

    expect(readOverviewLastViewedAt(scenarioAScope, storage)).toBeNull();
    expect(storage.getItem(OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY)).toBe(legacy);
    expect(readOverviewLastViewedAt(nativeScope, storage)).toBe(legacy);
    expect(storage.getItem(OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY)).toBeNull();
    expect(JSON.parse(storage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY) ?? "{}")).toEqual({
      [nativeScope]: legacy,
    });
  });

  it("keeps a stored boundary at or before Core's dashboard clock", () => {
    expect(
      resolveOverviewPreviousLastViewedAt(
        "2026-07-10T12:00:00.000Z",
        "2026-07-10T12:00:00.000Z",
      ),
    ).toBe("2026-07-10T12:00:00.000Z");
    expect(
      resolveOverviewPreviousLastViewedAt(
        "2026-07-09T12:00:00.000Z",
        "2026-07-10T12:00:00.000Z",
      ),
    ).toBe("2026-07-09T12:00:00.000Z");
  });

  it("discards a future browser-clock boundary instead of risking skipped evidence", () => {
    expect(
      resolveOverviewPreviousLastViewedAt(
        "2027-01-01T00:00:00.000Z",
        "2026-07-10T12:00:00.000Z",
      ),
    ).toBeNull();
  });
});
