/**
 * Narrow in-memory browser-auth transport ownership.
 *
 * Owns CSRF and auth method only. Never stores API tokens, cookies, or secrets.
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
  | "network";

type UnauthorizedListener = () => void;
type RevalidateListener = () => void;
type ChangeListener = () => void;

class AuthRuntime {
  private csrfToken: string | null = null;
  private authMethod: AuthMethod | null = null;
  private expiresAt: string | null = null;
  private browserSessionEnabled = false;
  private epoch = 0;
  private unauthorizedListeners = new Set<UnauthorizedListener>();
  private revalidateListeners = new Set<RevalidateListener>();
  private changeListeners = new Set<ChangeListener>();
  private unauthorizedNotifiedForEpoch = -1;
  private revalidateNotifiedAt = 0;

  getEpoch(): number {
    return this.epoch;
  }

  getCsrfToken(): string | null {
    return this.csrfToken;
  }

  getAuthMethod(): AuthMethod | null {
    return this.authMethod;
  }

  getExpiresAt(): string | null {
    return this.expiresAt;
  }

  getBrowserSessionEnabled(): boolean {
    return this.browserSessionEnabled;
  }

  isSessionAuth(): boolean {
    return this.authMethod === "session";
  }

  isTrustedLocal(): boolean {
    return this.authMethod === "trusted_local";
  }

  setTrustedLocal(browserSessionEnabled = false): void {
    this.csrfToken = null;
    this.authMethod = "trusted_local";
    this.expiresAt = null;
    this.browserSessionEnabled = browserSessionEnabled;
    this.bumpEpoch();
    this.emitChange();
  }

  setSession(opts: {
    csrfToken: string;
    expiresAt: string;
    browserSessionEnabled: boolean;
  }): void {
    this.csrfToken = opts.csrfToken;
    this.authMethod = "session";
    this.expiresAt = opts.expiresAt;
    this.browserSessionEnabled = opts.browserSessionEnabled;
    this.bumpEpoch();
    this.emitChange();
  }

  updateCsrfToken(token: string): void {
    if (this.authMethod !== "session") return;
    this.csrfToken = token;
    this.emitChange();
  }

  clear(): void {
    this.csrfToken = null;
    this.authMethod = null;
    this.expiresAt = null;
    this.browserSessionEnabled = false;
    this.bumpEpoch();
    this.emitChange();
  }

  onUnauthorized(listener: UnauthorizedListener): () => void {
    this.unauthorizedListeners.add(listener);
    return () => {
      this.unauthorizedListeners.delete(listener);
    };
  }

  onRevalidate(listener: RevalidateListener): () => void {
    this.revalidateListeners.add(listener);
    return () => {
      this.revalidateListeners.delete(listener);
    };
  }

  onChange(listener: ChangeListener): () => void {
    this.changeListeners.add(listener);
    return () => {
      this.changeListeners.delete(listener);
    };
  }

  /** One bounded notification per auth epoch for protected 401s. */
  notifyUnauthorized(): void {
    if (this.unauthorizedNotifiedForEpoch === this.epoch) return;
    this.unauthorizedNotifiedForEpoch = this.epoch;
    for (const listener of [...this.unauthorizedListeners]) {
      listener();
    }
  }

  /** Debounced session-status refresh (CSRF miss / CSRF 403). */
  notifyRevalidate(): void {
    const now = Date.now();
    if (now - this.revalidateNotifiedAt < 750) return;
    this.revalidateNotifiedAt = now;
    for (const listener of [...this.revalidateListeners]) {
      listener();
    }
  }

  resetForTests(): void {
    this.csrfToken = null;
    this.authMethod = null;
    this.expiresAt = null;
    this.browserSessionEnabled = false;
    this.epoch = 0;
    this.unauthorizedNotifiedForEpoch = -1;
    this.revalidateNotifiedAt = 0;
    this.unauthorizedListeners.clear();
    this.revalidateListeners.clear();
    this.changeListeners.clear();
  }

  private bumpEpoch(): void {
    this.epoch += 1;
    this.unauthorizedNotifiedForEpoch = -1;
  }

  private emitChange(): void {
    for (const listener of [...this.changeListeners]) {
      listener();
    }
  }
}

export const authRuntime = new AuthRuntime();

export const CSRF_HEADER_NAME = "X-ZigbeeLens-CSRF-Token";
