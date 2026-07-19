import type { BrowserSessionStatus } from "@zigbeelens/shared";

const AUTH_METHODS = new Set(["trusted_local", "bearer", "session", null]);

/** Core max session TTL is 604800s (7d); allow a small clock skew. */
const MAX_SESSION_TTL_MS = 604_800_000 + 5 * 60_000;
/** Align with Core MAX_CSRF_TOKEN_BYTES. */
const MAX_CSRF_BYTES = 4096;

export type ParsedSessionStatus =
  | { ok: true; status: BrowserSessionStatus }
  | {
      ok: false;
      reason: "malformed" | "unexpected_bearer" | "incomplete_session";
    };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseExpiresAt(value: unknown): string | null | undefined {
  if (value === null) return null;
  if (value === undefined) return undefined;
  if (typeof value !== "string") return undefined;
  if (value.trim() === "") return undefined;
  if (value !== value.trim()) return undefined;
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return undefined;
  return value;
}

function isSafeHeaderToken(value: string): boolean {
  // Reject control characters and DEL; CSRF must be header-safe.
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code < 0x20 || code === 0x7f) return false;
  }
  return true;
}

function parseCsrf(value: unknown): string | null | undefined {
  if (value === null) return null;
  if (value === undefined) return undefined;
  if (typeof value !== "string") return undefined;
  if (value.length === 0) return "";
  if (value !== value.trim()) return undefined;
  if (!isSafeHeaderToken(value)) return undefined;
  if (new TextEncoder().encode(value).length > MAX_CSRF_BYTES) return undefined;
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

  const csrf = parseCsrf(raw.csrf_token);
  if (csrf === undefined) return { ok: false, reason: "malformed" };

  const status: BrowserSessionStatus = {
    authenticated: raw.authenticated,
    auth_method: authMethod as BrowserSessionStatus["auth_method"],
    browser_session_enabled: raw.browser_session_enabled,
    expires_at: expiresAt,
    csrf_token: csrf,
  };

  if (!status.authenticated) {
    if (status.auth_method !== null) return { ok: false, reason: "malformed" };
    if (status.expires_at !== null) return { ok: false, reason: "malformed" };
    if (status.csrf_token !== null) return { ok: false, reason: "malformed" };
    return { ok: true, status };
  }

  if (status.auth_method === "bearer") {
    return { ok: false, reason: "unexpected_bearer" };
  }

  if (status.auth_method === "trusted_local") {
    if (status.expires_at !== null) return { ok: false, reason: "malformed" };
    if (status.csrf_token !== null) return { ok: false, reason: "malformed" };
    return { ok: true, status };
  }

  if (status.auth_method === "session") {
    if (!status.browser_session_enabled) {
      return { ok: false, reason: "incomplete_session" };
    }
    if (typeof status.csrf_token !== "string" || status.csrf_token.length === 0) {
      return { ok: false, reason: "incomplete_session" };
    }
    if (typeof status.expires_at !== "string" || status.expires_at.length === 0) {
      return { ok: false, reason: "incomplete_session" };
    }
    const ms = Date.parse(status.expires_at);
    if (Number.isNaN(ms) || ms <= Date.now()) {
      return { ok: false, reason: "incomplete_session" };
    }
    if (ms - Date.now() > MAX_SESSION_TTL_MS) {
      return { ok: false, reason: "incomplete_session" };
    }
    return { ok: true, status };
  }

  return { ok: false, reason: "malformed" };
}
