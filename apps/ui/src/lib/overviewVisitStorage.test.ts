import { beforeEach, describe, expect, it } from "vitest";
import {
  OVERVIEW_LAST_VIEWED_STORAGE_KEY,
  readOverviewLastViewedAt,
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
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when no previous timestamp exists", () => {
    expect(readOverviewLastViewedAt()).toBeNull();
  });

  it("treats invalid timestamps as missing and clears them", () => {
    localStorage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, "not-a-date");
    expect(readOverviewLastViewedAt()).toBeNull();
    expect(localStorage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY)).toBeNull();
  });

  it("reads a previously written visit timestamp", () => {
    writeOverviewLastViewedAt("2026-07-10T12:00:00.000Z");
    expect(readOverviewLastViewedAt()).toBe("2026-07-10T12:00:00.000Z");
  });

  it("supports an injected storage for tests", () => {
    const storage = memoryStorage();
    writeOverviewLastViewedAt("2026-07-11T08:00:00.000Z", storage);
    expect(readOverviewLastViewedAt(storage)).toBe("2026-07-11T08:00:00.000Z");
  });
});
