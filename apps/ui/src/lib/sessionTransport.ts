/**
 * Transport-private session credentials and credentialed fetch.
 *
 * The CSRF token never leaves this module except inside Request headers that are
 * handed directly to fetch(). No exported API returns the token or writes it into
 * caller-owned Headers objects.
 */

import { authRuntime } from "@/lib/authRuntime";

export const CSRF_HEADER_NAME = "X-ZigbeeLens-CSRF-Token";

type SessionTransportState = {
  csrfToken: string | null;
  revision: number;
  sessionActive: boolean;
};

const state: SessionTransportState = {
  csrfToken: null,
  revision: 0,
  sessionActive: false,
};

export type TransportCredentialResult = {
  revision: number;
  changed: boolean;
};

export type RequestIntent =
  | "protected"
  | "public_session_status"
  | "session_bootstrap"
  | "session_logout";

/** Install CSRF for session auth. Returns an opaque revision for identity compares. */
export function installSessionTransportCredentials(
  csrfToken: string,
): TransportCredentialResult {
  if (state.sessionActive && state.csrfToken === csrfToken) {
    return { revision: state.revision, changed: false };
  }
  state.csrfToken = csrfToken;
  state.sessionActive = true;
  state.revision += 1;
  return { revision: state.revision, changed: true };
}

/** Clear transport-private CSRF. */
export function clearSessionTransportCredentials(): TransportCredentialResult {
  if (!state.sessionActive && state.csrfToken === null) {
    return { revision: state.revision, changed: false };
  }
  state.csrfToken = null;
  state.sessionActive = false;
  state.revision += 1;
  return { revision: state.revision, changed: true };
}

export function getSessionTransportRevision(): number {
  return state.revision;
}

export function isSessionTransportActive(): boolean {
  return state.sessionActive;
}

export type CredentialedFetchOptions = {
  intent: RequestIntent;
  /** Consumed synchronously into the Request; cleared before returning. */
  bearer?: string;
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  cache?: RequestCache;
};

export type StartCredentialedFetchResult =
  | { ok: true; promise: Promise<Response> }
  | { ok: false; reason: "csrf_missing" };

/**
 * Build a credentialed Request and start fetch. CSRF is applied only onto the
 * Request constructed here — callers never receive a Headers object containing it.
 *
 * For session_bootstrap, Authorization is copied into the Request immediately,
 * then the local bearer reference is released before the promise is returned.
 */
export function startCredentialedFetch(
  url: string,
  options: CredentialedFetchOptions,
): StartCredentialedFetchResult {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  const unsafe = method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE";

  let bearer: string | undefined = options.bearer;
  if (options.intent === "session_bootstrap" && bearer) {
    headers.set("Authorization", `Bearer ${bearer}`);
  }

  if (unsafe && (options.intent === "protected" || options.intent === "session_logout")) {
    // Session auth requires the transport-private CSRF; never skip when identity is session.
    if (authRuntime.isSessionAuth()) {
      if (!state.csrfToken) {
        bearer = undefined;
        return { ok: false, reason: "csrf_missing" };
      }
      headers.set(CSRF_HEADER_NAME, state.csrfToken);
    }
  }

  const noStore =
    options.intent === "public_session_status" ||
    options.intent === "session_bootstrap" ||
    options.intent === "session_logout";

  const request = new Request(url, {
    method,
    headers,
    body: options.body,
    credentials: "include",
    cache: noStore ? "no-store" : options.cache,
  });

  // Release deliberate token copies now that the Request owns the Authorization header.
  bearer = undefined;
  options.bearer = undefined;

  return { ok: true, promise: fetch(request) };
}

/** Test reset — clears private CSRF without exposing it. */
export function resetSessionTransportForTests(): void {
  state.csrfToken = null;
  state.revision = 0;
  state.sessionActive = false;
}
