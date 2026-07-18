import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "@/context/BrowserAuthContext";

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zl-bg px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zl-accent/20 text-sm font-bold text-zl-accent">
            ZL
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight">ZigbeeLens</div>
            <div className="text-xs text-zl-muted">Read-only diagnostics</div>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

function CheckingState() {
  return (
    <Shell>
      <h1 className="text-xl font-semibold">Checking access…</h1>
      <p className="text-sm text-zl-muted" role="status" aria-live="polite">
        Verifying browser session with ZigbeeLens Core.
      </p>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-zl-surface-2"
        aria-hidden="true"
      >
        <div className="h-full w-1/3 animate-pulse rounded-full bg-zl-accent/60" />
      </div>
    </Shell>
  );
}

function UnreachableState({ onRetry }: { onRetry: () => void }) {
  return (
    <Shell>
      <h1 className="text-xl font-semibold">Core is not reachable</h1>
      <p className="text-sm text-zl-muted">
        ZigbeeLens UI could not reach the Core API. This is a connectivity problem, not an invalid
        token.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-11 w-full rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-zl-bg hover:opacity-90"
      >
        Retry
      </button>
    </Shell>
  );
}

function SetupRequiredState({ onRetry }: { onRetry: () => void }) {
  return (
    <Shell>
      <h1 className="text-xl font-semibold">Browser access setup required</h1>
      <p className="text-sm text-zl-muted">
        Core requires API authentication, but browser sessions are not configured. The standalone UI
        exchanges an API token once for an HttpOnly browser session and does not keep the token.
      </p>
      <div className="rounded-lg border border-zl-border bg-zl-surface p-4 text-sm">
        <p className="mb-2 text-zl-text">Configure both of these and restart Core:</p>
        <ul className="list-inside list-disc space-y-1 font-mono text-xs text-zl-accent">
          <li>security.api_token</li>
          <li>security.session_secret</li>
        </ul>
      </div>
      <p className="text-sm text-zl-muted">
        Bearer-only Core configurations still work for API clients. The UI intentionally stays locked
        until browser sessions are enabled.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-11 w-full rounded-lg border border-zl-border px-4 py-2 text-sm hover:bg-zl-surface-2"
      >
        Retry
      </button>
    </Shell>
  );
}

function LockedLoginState({
  reason,
  loginError,
  loginBusy,
  onLogin,
}: {
  reason: string;
  loginError: string | null;
  loginBusy: boolean;
  onLogin: (token: string) => Promise<void>;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [token, setToken] = useState("");

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (loginError) inputRef.current?.focus();
  }, [loginError]);

  const expired = reason === "expired";
  const cookieBlocked = reason === "cookie_blocked";
  const originRejected = reason === "origin_rejected";
  const protocolError = reason === "protocol_error";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const value = token;
    setToken("");
    await onLogin(value);
  }

  return (
    <Shell>
      <h1 className="text-xl font-semibold">
        {expired ? "Browser session expired" : "ZigbeeLens is locked"}
      </h1>
      <p className="text-sm text-zl-muted">
        {expired
          ? "Enter the API token again to create a new browser session. Sessions are not renewed automatically."
          : "Enter the Core API token. It is exchanged once for an HttpOnly browser session and is not stored by the UI."}
      </p>
      {cookieBlocked && (
        <p className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 p-3 text-sm text-zl-watch" role="alert">
          The browser did not retain the session cookie. Prefer HTTPS with Secure cookies, same-site
          deployment (Vite proxy in development), exact cors_allowed_origins for a cross-origin UI,
          and check privacy / third-party cookie blocking. Credentials are never placed in URLs.
        </p>
      )}
      {originRejected && (
        <p className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 p-3 text-sm text-zl-watch" role="alert">
          Browser origin was rejected. Configure exact cors_allowed_origins for the UI origin. This is
          a deployment configuration issue, not an invalid token.
        </p>
      )}
      {protocolError && (
        <p className="rounded-lg border border-zl-watch/40 bg-zl-watch/10 p-3 text-sm text-zl-watch" role="alert">
          Unexpected session response from Core. Check deployment configuration and retry.
        </p>
      )}
      <form className="space-y-4" onSubmit={handleSubmit} autoComplete="off">
        <div className="space-y-2">
          <label htmlFor={inputId} className="block text-sm font-medium text-zl-text">
            API token
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            spellCheck={false}
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="off"
            disabled={loginBusy}
            className="min-h-11 w-full rounded-lg border border-zl-border bg-zl-surface px-3 py-2 text-sm text-zl-text"
            required
          />
        </div>
        {loginError && (
          <p className="text-sm text-zl-critical" role="alert" aria-live="assertive">
            {loginError}
          </p>
        )}
        <button
          type="submit"
          disabled={loginBusy || token.length === 0}
          aria-busy={loginBusy}
          className="min-h-11 w-full rounded-lg bg-zl-accent px-4 py-2 text-sm font-medium text-zl-bg hover:opacity-90 disabled:opacity-50"
        >
          {loginBusy ? "Unlocking…" : "Unlock"}
        </button>
      </form>
    </Shell>
  );
}

/**
 * Renders locked/setup/unreachable shells, or children only after authentication
 * is known and granted. Protected providers must be children of this gate.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (auth.phase === "checking") {
    return <CheckingState />;
  }
  if (auth.phase === "unreachable") {
    return <UnreachableState onRetry={() => void auth.retry()} />;
  }
  if (auth.phase === "setup_required") {
    return <SetupRequiredState onRetry={() => void auth.retry()} />;
  }
  if (auth.phase === "locked") {
    return (
      <LockedLoginState
        reason={auth.reason}
        loginError={auth.loginError}
        loginBusy={auth.loginBusy}
        onLogin={auth.login}
      />
    );
  }

  return <>{children}</>;
}
