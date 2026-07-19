/**
 * Safe browser-auth identity and access generations.
 *
 * Does not store API tokens, cookies, session secrets, or CSRF tokens.
 * CSRF lives only in sessionTransport (transport-private).
 *
 * identityGeneration — changes only when the effective identity tuple changes.
 * accessGeneration — advances whenever protected work must become stale
 *   (identity change, 401, logout, expiry, protocol/auth locks, bfcache, unmount).
 */

export type AuthMethod = "trusted_local" | "session";

export type AuthPhase =
  | "checking"
  | "signing_out"
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

type UnauthorizedListener = () => void;
type RevalidateListener = () => void;
type ChangeListener = () => void;

type IdentityTuple = {
  authMethod: AuthMethod | null;
  expiresAt: string | null;
  credentialRevision: number;
  browserSessionEnabled: boolean;
};

function identityEqual(a: IdentityTuple, b: IdentityTuple): boolean {
  return (
    a.authMethod === b.authMethod &&
    a.expiresAt === b.expiresAt &&
    a.credentialRevision === b.credentialRevision &&
    a.browserSessionEnabled === b.browserSessionEnabled
  );
}

class AuthRuntime {
  #authMethod: AuthMethod | null = null;
  #expiresAt: string | null = null;
  #browserSessionEnabled = false;
  #credentialRevision = 0;
  #identityGeneration = 0;
  #accessGeneration = 0;
  #unauthorizedListeners = new Set<UnauthorizedListener>();
  #revalidateListeners = new Set<RevalidateListener>();
  #changeListeners = new Set<ChangeListener>();
  #unauthorizedNotifiedForAccess = -1;
  #revalidateNotifiedAt = 0;

  getIdentityGeneration(): number {
    return this.#identityGeneration;
  }

  getAccessGeneration(): number {
    return this.#accessGeneration;
  }

  /**
   * Access generation — used by authEpoch / stale protected work.
   * @deprecated Prefer getAccessGeneration(); retained for existing callers.
   */
  getEpoch(): number {
    return this.#accessGeneration;
  }

  /**
   * Access generation alias for existing fetch/download callers.
   * @deprecated Prefer getAccessGeneration().
   */
  getGeneration(): number {
    return this.#accessGeneration;
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

  getCredentialRevision(): number {
    return this.#credentialRevision;
  }

  isSessionAuth(): boolean {
    return this.#authMethod === "session";
  }

  isTrustedLocal(): boolean {
    return this.#authMethod === "trusted_local";
  }

  setTrustedLocal(browserSessionEnabled = false): void {
    const next: IdentityTuple = {
      authMethod: "trusted_local",
      expiresAt: null,
      credentialRevision: 0,
      browserSessionEnabled,
    };
    if (identityEqual(this.#currentIdentity(), next)) return;
    this.#authMethod = "trusted_local";
    this.#expiresAt = null;
    this.#credentialRevision = 0;
    this.#browserSessionEnabled = browserSessionEnabled;
    this.#bumpIdentityChange();
    this.#emitChange();
  }

  setSession(opts: {
    expiresAt: string;
    browserSessionEnabled: boolean;
    credentialRevision: number;
  }): void {
    const next: IdentityTuple = {
      authMethod: "session",
      expiresAt: opts.expiresAt,
      credentialRevision: opts.credentialRevision,
      browserSessionEnabled: opts.browserSessionEnabled,
    };
    if (identityEqual(this.#currentIdentity(), next)) return;
    this.#authMethod = "session";
    this.#expiresAt = opts.expiresAt;
    this.#credentialRevision = opts.credentialRevision;
    this.#browserSessionEnabled = opts.browserSessionEnabled;
    this.#bumpIdentityChange();
    this.#emitChange();
  }

  clear(): void {
    if (
      this.#authMethod === null &&
      this.#credentialRevision === 0 &&
      !this.#browserSessionEnabled
    ) {
      return;
    }
    this.#authMethod = null;
    this.#expiresAt = null;
    this.#credentialRevision = 0;
    this.#browserSessionEnabled = false;
    this.#bumpIdentityChange();
    this.#emitChange();
  }

  /**
   * Advance protected-access generation without changing the identity tuple.
   * Used for bfcache suspension, logout start, provider unmount, and locks
   * that do not already change identity.
   */
  advanceAccessGeneration(): void {
    this.#accessGeneration += 1;
    this.#unauthorizedNotifiedForAccess = -1;
    this.#revalidateNotifiedAt = 0;
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

  /** One bounded notification per access generation for protected 401s. */
  notifyUnauthorized(): void {
    if (this.#unauthorizedNotifiedForAccess === this.#accessGeneration) return;
    this.#unauthorizedNotifiedForAccess = this.#accessGeneration;
    for (const listener of [...this.#unauthorizedListeners]) {
      listener();
    }
  }

  /**
   * Allow another unauthorized notification for the current access generation.
   * Used when the provider defers handling (e.g. unauthorized during logout)
   * so a later protected 401 is not lost to dedupe.
   */
  releaseUnauthorizedDedupe(): void {
    this.#unauthorizedNotifiedForAccess = -1;
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
    this.#authMethod = null;
    this.#expiresAt = null;
    this.#browserSessionEnabled = false;
    this.#credentialRevision = 0;
    this.#identityGeneration = 0;
    this.#accessGeneration = 0;
    this.#unauthorizedNotifiedForAccess = -1;
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
      credentialRevision: this.#credentialRevision,
      identityGeneration: this.#identityGeneration,
      accessGeneration: this.#accessGeneration,
    };
  }

  toString(): string {
    return `AuthRuntime(method=${this.#authMethod ?? "none"}, identity=${this.#identityGeneration}, access=${this.#accessGeneration})`;
  }

  #currentIdentity(): IdentityTuple {
    return {
      authMethod: this.#authMethod,
      expiresAt: this.#expiresAt,
      credentialRevision: this.#credentialRevision,
      browserSessionEnabled: this.#browserSessionEnabled,
    };
  }

  #bumpIdentityChange(): void {
    this.#identityGeneration += 1;
    this.#accessGeneration += 1;
    this.#unauthorizedNotifiedForAccess = -1;
    this.#revalidateNotifiedAt = 0;
  }

  #emitChange(): void {
    for (const listener of [...this.#changeListeners]) {
      listener();
    }
  }
}

export const authRuntime = new AuthRuntime();
