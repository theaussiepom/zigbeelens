/**
 * Browser-local Overview visit timestamp helpers (Phase 5A-3).
 */

export const OVERVIEW_LAST_VIEWED_STORAGE_KEY = "zigbeelens.overview.lastViewedAt.v1";

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

export function readOverviewLastViewedAt(
  storage: Pick<Storage, "getItem" | "removeItem"> = localStorage,
): string | null {
  try {
    const raw = storage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
    if (!raw || !isValidOverviewVisitTimestamp(raw)) {
      if (raw) {
        storage.removeItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
      }
      return null;
    }
    return raw;
  } catch {
    return null;
  }
}

export function writeOverviewLastViewedAt(
  iso: string,
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  if (!isValidOverviewVisitTimestamp(iso)) {
    return;
  }
  try {
    storage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, iso);
  } catch {
    // Ignore quota / private-mode failures.
  }
}
