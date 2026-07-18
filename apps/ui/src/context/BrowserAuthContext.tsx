import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  createBrowserSession,
  deleteBrowserSession,
  fetchSessionStatus,
  ApiError,
} from "@/lib/api";
import {
  authRuntime,
  type AuthMethod,
  type AuthPhase,
  type AuthReason,
} from "@/lib/authRuntime";
import { liveConnection } from "@/lib/events";

export type BrowserAuthContextValue = {
  phase: AuthPhase;
  reason: AuthReason;
  authMethod: AuthMethod | null;
  expiresAt: string | null;
  browserSessionEnabled: boolean;
  authEpoch: number;
  loginError: string | null;
  logoutError: string | null;
  loginBusy: boolean;
  login: (apiToken: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => Promise<void>;
};

const BrowserAuthContext = createContext<BrowserAuthContextValue | null>(null);

const REVALIDATE_DEBOUNCE_MS = 800;

function applyAuthenticatedStatus(status: {
  auth_method: "trusted_local" | "session";
  expires_at: string | null;
  csrf_token: string | null;
  browser_session_enabled: boolean;
}): void {
  if (status.auth_method === "trusted_local") {
    authRuntime.setTrustedLocal(status.browser_session_enabled);
    return;
  }
  authRuntime.setSession({
    csrfToken: status.csrf_token!,
    expiresAt: status.expires_at!,
    browserSessionEnabled: status.browser_session_enabled,
  });
}

export function BrowserAuthProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<AuthPhase>("checking");
  const [reason, setReason] = useState<AuthReason>("initial");
  const [authMethod, setAuthMethod] = useState<AuthMethod | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [browserSessionEnabled, setBrowserSessionEnabled] = useState(false);
  const [authEpoch, setAuthEpoch] = useState(0);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);

  const probeInFlight = useRef<Promise<void> | null>(null);
  const loginInFlight = useRef(false);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const revalidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const syncFromRuntime = useCallback(() => {
    setAuthMethod(authRuntime.getAuthMethod());
    setExpiresAt(authRuntime.getExpiresAt());
    setBrowserSessionEnabled(authRuntime.getBrowserSessionEnabled());
    setAuthEpoch(authRuntime.getEpoch());
  }, []);

  const clearExpiryTimer = useCallback(() => {
    if (expiryTimer.current) {
      clearTimeout(expiryTimer.current);
      expiryTimer.current = null;
    }
  }, []);

  const lockUi = useCallback(
    (next: AuthPhase, nextReason: AuthReason) => {
      clearExpiryTimer();
      liveConnection.setAccessEnabled(false);
      authRuntime.clear();
      syncFromRuntime();
      setPhase(next);
      setReason(nextReason);
      setLoginError(null);
    },
    [clearExpiryTimer, syncFromRuntime],
  );

  const scheduleExpiry = useCallback(
    (iso: string) => {
      clearExpiryTimer();
      const ms = Date.parse(iso) - Date.now();
      if (!Number.isFinite(ms) || ms <= 0) {
        lockUi("locked", "expired");
        void probeSession("expired");
        return;
      }
      expiryTimer.current = setTimeout(() => {
        lockUi("locked", "expired");
        void probeSession("expired");
      }, ms);
    },
    // probeSession defined below — intentional late binding via ref pattern
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clearExpiryTimer, lockUi],
  );

  const unlockFromStatus = useCallback(
    (status: {
      authenticated: boolean;
      auth_method: "trusted_local" | "bearer" | "session" | null;
      browser_session_enabled: boolean;
      expires_at: string | null;
      csrf_token: string | null;
    }) => {
      if (!status.authenticated) {
        liveConnection.setAccessEnabled(false);
        authRuntime.clear();
        syncFromRuntime();
        if (!status.browser_session_enabled) {
          setPhase("setup_required");
          setReason("configuration");
        } else {
          setPhase("locked");
        }
        return;
      }

      if (status.auth_method === "trusted_local") {
        applyAuthenticatedStatus({
          auth_method: "trusted_local",
          expires_at: null,
          csrf_token: null,
          browser_session_enabled: status.browser_session_enabled,
        });
        syncFromRuntime();
        clearExpiryTimer();
        liveConnection.setAccessEnabled(true);
        setPhase("authenticated");
        setReason("initial");
        setLoginError(null);
        setLogoutError(null);
        return;
      }

      if (status.auth_method === "session") {
        applyAuthenticatedStatus({
          auth_method: "session",
          expires_at: status.expires_at,
          csrf_token: status.csrf_token,
          browser_session_enabled: status.browser_session_enabled,
        });
        syncFromRuntime();
        scheduleExpiry(status.expires_at!);
        liveConnection.setAccessEnabled(true);
        setPhase("authenticated");
        setReason("initial");
        setLoginError(null);
        setLogoutError(null);
        return;
      }

      // bearer or unknown — fail closed
      lockUi("locked", "unauthorized");
    },
    [clearExpiryTimer, lockUi, scheduleExpiry, syncFromRuntime],
  );

  const probeSession = useCallback(
    async (probeReason: AuthReason = "initial") => {
      if (probeInFlight.current) return probeInFlight.current;

      const run = (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!mounted.current) return;
          setReason(probeReason);
          unlockFromStatus(status);
        } catch (error) {
          if (!mounted.current) return;
          if (error instanceof ApiError) {
            if (error.detail === "unexpected_bearer") {
              lockUi("setup_required", "configuration");
              return;
            }
            if (error.detail === "incomplete_session") {
              lockUi("locked", "expired");
              return;
            }
            if (error.kind === "unreachable") {
              lockUi("unreachable", "network");
              return;
            }
          }
          lockUi("unreachable", "network");
        } finally {
          probeInFlight.current = null;
        }
      })();

      probeInFlight.current = run;
      return run;
    },
    [lockUi, unlockFromStatus],
  );

  const handleUnauthorized = useCallback(() => {
    setPhase("checking");
    setReason("unauthorized");
    liveConnection.setAccessEnabled(false);
    authRuntime.clear();
    syncFromRuntime();
    void probeSession("unauthorized");
  }, [probeSession, syncFromRuntime]);

  const handleRevalidate = useCallback(() => {
    if (revalidateTimer.current) clearTimeout(revalidateTimer.current);
    revalidateTimer.current = setTimeout(() => {
      void (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!status.authenticated) {
            handleUnauthorized();
            return;
          }
          if (status.auth_method === "session" && status.csrf_token) {
            authRuntime.updateCsrfToken(status.csrf_token);
            syncFromRuntime();
          }
        } catch {
          // retain current authenticated state on network failure during CSRF refresh
        }
      })();
    }, REVALIDATE_DEBOUNCE_MS);
  }, [handleUnauthorized, syncFromRuntime]);

  useEffect(() => {
    mounted.current = true;
    void probeSession("initial");
    const offUnauthorized = authRuntime.onUnauthorized(handleUnauthorized);
    const offRevalidate = authRuntime.onRevalidate(handleRevalidate);
    return () => {
      mounted.current = false;
      offUnauthorized();
      offRevalidate();
      clearExpiryTimer();
      if (revalidateTimer.current) clearTimeout(revalidateTimer.current);
      liveConnection.setAccessEnabled(false);
    };
  }, [clearExpiryTimer, handleRevalidate, handleUnauthorized, probeSession]);

  // Focus / visibility / pageshow revalidation (debounced)
  useEffect(() => {
    if (phase !== "authenticated") return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        void probeSession("initial");
      }, REVALIDATE_DEBOUNCE_MS);
    };

    const onFocus = () => schedule();
    const onVisibility = () => {
      if (document.visibilityState === "visible") schedule();
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        // Fail closed through checking before exposing bfcache content.
        setPhase("checking");
        liveConnection.setAccessEnabled(false);
      }
      schedule();
    };

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [phase, probeSession]);

  const login = useCallback(
    async (apiToken: string) => {
      if (loginInFlight.current) return;
      loginInFlight.current = true;
      setLoginBusy(true);
      setLoginError(null);
      try {
        await createBrowserSession(apiToken);
        // Cookie round-trip — no Authorization.
        let confirmed;
        try {
          confirmed = await fetchSessionStatus();
        } catch {
          setPhase("locked");
          setReason("cookie_blocked");
          setLoginError(null);
          liveConnection.setAccessEnabled(false);
          authRuntime.clear();
          syncFromRuntime();
          return;
        }
        if (!confirmed.authenticated || confirmed.auth_method !== "session") {
          setPhase("locked");
          setReason("cookie_blocked");
          setLoginError(null);
          liveConnection.setAccessEnabled(false);
          authRuntime.clear();
          syncFromRuntime();
          return;
        }
        unlockFromStatus(confirmed);
      } catch (error) {
        if (error instanceof ApiError) {
          if (error.status === 401) {
            setPhase("locked");
            setReason("unauthorized");
            setLoginError("Token was not accepted.");
            return;
          }
          if (error.status === 409 || error.kind === "session_unavailable") {
            setPhase("setup_required");
            setReason("configuration");
            setLoginError(null);
            return;
          }
          if (error.kind === "unreachable") {
            setPhase("unreachable");
            setReason("network");
            return;
          }
        }
        setPhase("locked");
        setReason("unauthorized");
        setLoginError("Token was not accepted.");
      } finally {
        loginInFlight.current = false;
        setLoginBusy(false);
      }
    },
    [syncFromRuntime, unlockFromStatus],
  );

  const logout = useCallback(async () => {
    setLogoutError(null);
    try {
      await deleteBrowserSession();
      const confirmed = await fetchSessionStatus();
      if (confirmed.authenticated) {
        setLogoutError("Sign out could not be confirmed. Retry or clear site cookies.");
        return;
      }
      lockUi("locked", "logged_out");
      setLogoutError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await probeSession("logged_out");
        return;
      }
      if (error instanceof ApiError && error.kind === "unreachable") {
        setLogoutError("Could not reach Core to sign out. Your session may still be active.");
        return;
      }
      setLogoutError("Sign out failed. Retry.");
    }
  }, [lockUi, probeSession]);

  const retry = useCallback(async () => {
    setPhase("checking");
    setLoginError(null);
    setLogoutError(null);
    await probeSession("initial");
  }, [probeSession]);

  const value = useMemo<BrowserAuthContextValue>(
    () => ({
      phase,
      reason,
      authMethod,
      expiresAt,
      browserSessionEnabled,
      authEpoch,
      loginError,
      logoutError,
      loginBusy,
      login,
      logout,
      retry,
    }),
    [
      phase,
      reason,
      authMethod,
      expiresAt,
      browserSessionEnabled,
      authEpoch,
      loginError,
      logoutError,
      loginBusy,
      login,
      logout,
      retry,
    ],
  );

  return (
    <BrowserAuthContext.Provider value={value}>{children}</BrowserAuthContext.Provider>
  );
}

export function useAuth(): BrowserAuthContextValue {
  const ctx = useContext(BrowserAuthContext);
  if (!ctx) throw new Error("useAuth must be used within BrowserAuthProvider");
  return ctx;
}
