/**
 * Browser-local Overview visit timestamp helpers (Phase 5A-3).
 */

export const OVERVIEW_LAST_VIEWED_STORAGE_KEY = "zigbeelens.overview.lastViewedAt.v1";

function isValidIsoTimestamp(value: string): boolean {
  const ms = Date.parse(value);
  return Number.isFinite(ms);
}

export function readOverviewLastViewedAt(
  storage: Pick<Storage, "getItem" | "removeItem"> = localStorage,
): string | null {
  try {
    const raw = storage.getItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY);
    if (!raw || !isValidIsoTimestamp(raw)) {
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
  if (!isValidIsoTimestamp(iso)) {
    return;
  }
  try {
    storage.setItem(OVERVIEW_LAST_VIEWED_STORAGE_KEY, iso);
  } catch {
    // Ignore quota / private-mode failures.
  }
}
