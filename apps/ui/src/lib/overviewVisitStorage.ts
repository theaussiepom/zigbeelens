/** Browser-local, Core-clock Overview visit boundaries. */

export const OVERVIEW_LAST_VIEWED_STORAGE_KEY = "zigbeelens.overview.lastViewedAt.v2";
export const OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY = "zigbeelens.overview.lastViewedAt.v1";
export const OVERVIEW_NATIVE_VISIT_SCOPE = "native";

type OverviewVisitStorage = Pick<Storage, "getItem" | "removeItem" | "setItem">;
type OverviewVisitBoundaries = Record<string, string>;

export function overviewVisitScope(scenario: string | null | undefined): string {
  return scenario ? `scenario:${scenario}` : OVERVIEW_NATIVE_VISIT_SCOPE;
}

export function isValidOverviewVisitTimestamp(value: string): boolean {
  const ms = Date.parse(value);
  return Number.isFinite(ms);
}

/**
 * A stored boundary later than Core's accepted dashboard clock is unsafe: it
 * could skip incident changes. Treat it as a first visit so duplicate display
 * is possible but evidence is never filtered behind a future browser clock.
 */
export function resolveOverviewPreviousLastViewedAt(
  storedBoundary: string | null,
  coreGeneratedAt: string,
): string | null {
  if (
    !storedBoundary ||
    !isValidOverviewVisitTimestamp(storedBoundary) ||
    !isValidOverviewVisitTimestamp(coreGeneratedAt)
  ) {
    return null;
  }
  return Date.parse(storedBoundary) <= Date.parse(coreGeneratedAt) ? storedBoundary : null;
}

function readBoundaries(storage: OverviewVisitStorage): OverviewVisitBoundaries {
  const raw = storage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
  if (raw === null) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      storage.removeItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
      return {};
    }
    const boundaries: OverviewVisitBoundaries = {};
    let discardedInvalidEntry = false;
    for (const [scope, value] of Object.entries(parsed)) {
      if (typeof value === "string" && isValidOverviewVisitTimestamp(value)) {
        boundaries[scope] = value;
      } else {
        discardedInvalidEntry = true;
      }
    }
    if (discardedInvalidEntry) {
      storage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, JSON.stringify(boundaries));
    }
    return boundaries;
  } catch {
    storage.removeItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
    return {};
  }
}

export function readOverviewLastViewedAt(
  scope: string,
  storage: OverviewVisitStorage = localStorage,
): string | null {
  try {
    const boundaries = readBoundaries(storage);

    // The v1 boundary was shared by native and named scenarios, so its source
    // cannot be identified safely. Discard it instead of assigning it to any
    // v2 scope and risking skipped incident evidence.
    storage.removeItem(OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY);
    return boundaries[scope] ?? null;
  } catch {
    return null;
  }
}

export function writeOverviewLastViewedAt(
  scope: string,
  iso: string,
  storage: OverviewVisitStorage = localStorage,
): void {
  if (!isValidOverviewVisitTimestamp(iso)) {
    return;
  }
  try {
    const boundaries = readBoundaries(storage);
    boundaries[scope] = iso;
    storage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, JSON.stringify(boundaries));
    storage.removeItem(OVERVIEW_LAST_VIEWED_V1_STORAGE_KEY);
  } catch {
    // Ignore quota / private-mode failures.
  }
}
