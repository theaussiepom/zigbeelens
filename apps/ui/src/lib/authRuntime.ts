/**
 * Narrow in-memory browser-auth transport ownership.
 *
 * Owns CSRF and auth method only. Never stores API tokens, cookies, or secrets.
 * CSRF is held in ECMAScript #private fields and is never returned to callers.
 */

export type AuthMethod = "trusted_local" | "session";

export type AuthPhase =
  | "checking"
  | "authenticated"
  | "locked"
  | "setup_required"
  | "unreachable";

export type AuthReason =
  | "initial"
  | "expired"
  | "logged_out"
  | "unauthorized"
  | "cookie_blocked"
  | "configuration"
  | "network"
  | "origin_rejected"
  | "protocol_error";

export type ApplyCsrfResult = "applied" | "not_session" | "missing";

export const CSRF_HEADER_NAME = "X-ZigbeeLens-CSRF-Token";

type UnauthorizedListener = () => void;
type RevalidateListener = () => void;
type ChangeListener = () => void;

type IdentityTuple = {
  authMethod: AuthMethod | null;
  expiresAt: string | null;
  csrfToken: string | null;
  browserSessionEnabled: boolean;
};

function identityEqual(a: IdentityTuple, b: IdentityTuple): boolean {
  return (
    a.authMethod === b.authMethod &&
    a.expiresAt === b.expiresAt &&
    a.csrfToken === b.csrfToken &&
    a.browserSessionEnabled === b.browserSessionEnabled
  );
}

class AuthRuntime {
  #csrfToken: string | null = null;
  #authMethod: AuthMethod | null = null;
  #expiresAt: string | null = null;
  #browserSessionEnabled = false;
  #generation = 0;
  #unauthorizedListeners = new Set<UnauthorizedListener>();
  #revalidateListeners = new Set<RevalidateListener>();
  #changeListeners = new Set<ChangeListener>();
  #unauthorizedNotifiedForGeneration = -1;
  #revalidateNotifiedAt = 0;

  /** Public alias kept for compatibility with authEpoch consumers. */
  getEpoch(): number {
    return this.#generation;
  }

  getGeneration(): number {
    return this.#generation;
  }

  getAuthMethod(): AuthMethod | null {
    return this.#authMethod;
  }

  getExpiresAt(): string | null {
    return this.#expiresAt;
  }

  getBrowserSessionEnabled(): boolean {
    return this.#browserSessionEnabled;
  }

  isSessionAuth(): boolean {
    return this.#authMethod === "session";
  }

  isTrustedLocal(): boolean {
    return this.#authMethod === "trusted_local";
  }

  /**
   * Apply the in-memory CSRF token to headers without exposing the value.
   */
  applySessionCsrf(headers: Headers): ApplyCsrfResult {
    if (this.#authMethod !== "session") return "not_session";
    if (!this.#csrfToken) return "missing";
    headers.set(CSRF_HEADER_NAME, this.#csrfToken);
    return "applied";
  }

  setTrustedLocal(browserSessionEnabled = false): void {
    const next: IdentityTuple = {
      authMethod: "trusted_local",
      expiresAt: null,
      csrfToken: null,
      browserSessionEnabled,
    };
    if (identityEqual(this.#currentIdentity(), next)) return;
    this.#csrfToken = null;
    this.#authMethod = "trusted_local";
    this.#expiresAt = null;
    this.#browserSessionEnabled = browserSessionEnabled;
    this.#bumpGeneration();
    this.#emitChange();
  }

  setSession(opts: {
    csrfToken: string;
    expiresAt: string;
    browserSessionEnabled: boolean;
  }): void {
    const next: IdentityTuple = {
      authMethod: "session",
      expiresAt: opts.expiresAt,
      csrfToken: opts.csrfToken,
      browserSessionEnabled: opts.browserSessionEnabled,
    };
    if (identityEqual(this.#currentIdentity(), next)) return;
    this.#csrfToken = opts.csrfToken;
    this.#authMethod = "session";
    this.#expiresAt = opts.expiresAt;
    this.#browserSessionEnabled = opts.browserSessionEnabled;
    this.#bumpGeneration();
    this.#emitChange();
  }

  /** Update session credentials; advances generation when the identity tuple changes. */
  updateSessionCredentials(opts: {
    csrfToken: string;
    expiresAt: string;
    browserSessionEnabled: boolean;
  }): void {
    this.setSession(opts);
  }

  clear(): void {
    if (this.#authMethod === null && this.#csrfToken === null && !this.#browserSessionEnabled) {
      return;
    }
    this.#csrfToken = null;
    this.#authMethod = null;
    this.#expiresAt = null;
    this.#browserSessionEnabled = false;
    this.#bumpGeneration();
    this.#emitChange();
  }

  onUnauthorized(listener: UnauthorizedListener): () => void {
    this.#unauthorizedListeners.add(listener);
    return () => {
      this.#unauthorizedListeners.delete(listener);
    };
  }

  onRevalidate(listener: RevalidateListener): () => void {
    this.#revalidateListeners.add(listener);
    return () => {
      this.#revalidateListeners.delete(listener);
    };
  }

  onChange(listener: ChangeListener): () => void {
    this.#changeListeners.add(listener);
    return () => {
      this.#changeListeners.delete(listener);
    };
  }

  /** One bounded notification per auth generation for protected 401s. */
  notifyUnauthorized(): void {
    if (this.#unauthorizedNotifiedForGeneration === this.#generation) return;
    this.#unauthorizedNotifiedForGeneration = this.#generation;
    for (const listener of [...this.#unauthorizedListeners]) {
      listener();
    }
  }

  /** Debounced session-status refresh (CSRF miss / CSRF 403). */
  notifyRevalidate(): void {
    const now = Date.now();
    if (now - this.#revalidateNotifiedAt < 750) return;
    this.#revalidateNotifiedAt = now;
    for (const listener of [...this.#revalidateListeners]) {
      listener();
    }
  }

  resetForTests(): void {
    this.#csrfToken = null;
    this.#authMethod = null;
    this.#expiresAt = null;
    this.#browserSessionEnabled = false;
    this.#generation = 0;
    this.#unauthorizedNotifiedForGeneration = -1;
    this.#revalidateNotifiedAt = 0;
    this.#unauthorizedListeners.clear();
    this.#revalidateListeners.clear();
    this.#changeListeners.clear();
  }

  toJSON(): Record<string, unknown> {
    return {
      authMethod: this.#authMethod,
      expiresAt: this.#expiresAt,
      browserSessionEnabled: this.#browserSessionEnabled,
      generation: this.#generation,
    };
  }

  toString(): string {
    return `AuthRuntime(method=${this.#authMethod ?? "none"}, generation=${this.#generation})`;
  }

  #currentIdentity(): IdentityTuple {
    return {
      authMethod: this.#authMethod,
      expiresAt: this.#expiresAt,
      csrfToken: this.#csrfToken,
      browserSessionEnabled: this.#browserSessionEnabled,
    };
  }

  #bumpGeneration(): void {
    this.#generation += 1;
    this.#unauthorizedNotifiedForGeneration = -1;
    this.#revalidateNotifiedAt = 0;
  }

  #emitChange(): void {
    for (const listener of [...this.#changeListeners]) {
      listener();
    }
  }
}

export const authRuntime = new AuthRuntime();
