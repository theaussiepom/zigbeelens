import type { BrowserSessionStatus } from "@zigbeelens/shared";

const AUTH_METHODS = new Set(["trusted_local", "bearer", "session", null]);

export type ParsedSessionStatus =
  | { ok: true; status: BrowserSessionStatus }
  | { ok: false; reason: "malformed" | "unexpected_bearer" | "incomplete_session" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parseExpiresAt(value: unknown): string | null | undefined {
  if (value === null || value === undefined) return value as null | undefined;
  if (typeof value !== "string" || value.trim() === "") return undefined;
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return undefined;
  return value;
}

/**
 * Strict runtime parser for public browser-session status.
 * Malformed required fields fail closed (do not unlock).
 */
export function parseBrowserSessionStatus(raw: unknown): ParsedSessionStatus {
  if (!isRecord(raw)) return { ok: false, reason: "malformed" };

  if (typeof raw.authenticated !== "boolean") return { ok: false, reason: "malformed" };
  if (typeof raw.browser_session_enabled !== "boolean") {
    return { ok: false, reason: "malformed" };
  }

  const authMethod = raw.auth_method ?? null;
  if (!AUTH_METHODS.has(authMethod as string | null)) {
    return { ok: false, reason: "malformed" };
  }

  const expiresAt = parseExpiresAt(raw.expires_at);
  if (expiresAt === undefined) return { ok: false, reason: "malformed" };

  const csrf =
    raw.csrf_token === null || raw.csrf_token === undefined
      ? null
      : typeof raw.csrf_token === "string"
        ? raw.csrf_token
        : undefined;
  if (csrf === undefined) return { ok: false, reason: "malformed" };

  const status: BrowserSessionStatus = {
    authenticated: raw.authenticated,
    auth_method: authMethod as BrowserSessionStatus["auth_method"],
    browser_session_enabled: raw.browser_session_enabled,
    expires_at: expiresAt,
    csrf_token: csrf,
  };

  // Standalone UI must not treat bearer as a durable unlocked state.
  if (status.authenticated && status.auth_method === "bearer") {
    return { ok: false, reason: "unexpected_bearer" };
  }

  if (status.authenticated && status.auth_method === "session") {
    if (!isNonEmptyString(status.csrf_token)) {
      return { ok: false, reason: "incomplete_session" };
    }
    if (!isNonEmptyString(status.expires_at)) {
      return { ok: false, reason: "incomplete_session" };
    }
    const ms = Date.parse(status.expires_at);
    if (Number.isNaN(ms) || ms <= Date.now()) {
      return { ok: false, reason: "incomplete_session" };
    }
  }

  if (status.authenticated && status.auth_method === "trusted_local") {
    // Trusted-open: do not require CSRF or expiry.
  }

  if (status.authenticated && status.auth_method == null) {
    return { ok: false, reason: "malformed" };
  }

  return { ok: true, status };
}
