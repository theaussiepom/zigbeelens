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
import { flushSync } from "react-dom";
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
  logoutBusy: boolean;
  login: (apiToken: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => Promise<void>;
};

const BrowserAuthContext = createContext<BrowserAuthContextValue | null>(null);

const REVALIDATE_DEBOUNCE_MS = 800;

type ProbeKind = "focus" | "forced" | "initial" | "unauthorized" | "logout" | "login" | "bfcache";

type ProbeHandle = {
  sequence: number;
  authGeneration: number;
  kind: ProbeKind;
};

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
  const [logoutBusy, setLogoutBusy] = useState(false);

  const probeSequence = useRef(0);
  const activeProbe = useRef<ProbeHandle | null>(null);
  const focusProbePromise = useRef<Promise<void> | null>(null);
  const loginInFlight = useRef(false);
  const logoutInFlight = useRef(false);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const revalidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  const phaseRef = useRef<AuthPhase>(phase);
  phaseRef.current = phase;
  const startProbeRef = useRef<
    (kind: ProbeKind, probeReason?: AuthReason) => Promise<void>
  >(async () => {});

  const syncFromRuntime = useCallback(() => {
    setAuthMethod(authRuntime.getAuthMethod());
    setExpiresAt(authRuntime.getExpiresAt());
    setBrowserSessionEnabled(authRuntime.getBrowserSessionEnabled());
    setAuthEpoch(authRuntime.getGeneration());
  }, []);

  const clearExpiryTimer = useCallback(() => {
    if (expiryTimer.current) {
      clearTimeout(expiryTimer.current);
      expiryTimer.current = null;
    }
  }, []);

  const clearFocusTimer = useCallback(() => {
    if (focusTimer.current) {
      clearTimeout(focusTimer.current);
      focusTimer.current = null;
    }
  }, []);

  const clearRevalidateTimer = useCallback(() => {
    if (revalidateTimer.current) {
      clearTimeout(revalidateTimer.current);
      revalidateTimer.current = null;
    }
  }, []);

  const invalidateProbes = useCallback(() => {
    probeSequence.current += 1;
    activeProbe.current = null;
    focusProbePromise.current = null;
  }, []);

  const isProbeCurrent = useCallback((handle: ProbeHandle): boolean => {
    return (
      mounted.current &&
      activeProbe.current?.sequence === handle.sequence &&
      handle.sequence === probeSequence.current
    );
  }, []);

  const lockUi = useCallback(
    (next: AuthPhase, nextReason: AuthReason) => {
      clearExpiryTimer();
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      liveConnection.setAccessEnabled(false);
      authRuntime.clear();
      syncFromRuntime();
      setPhase(next);
      setReason(nextReason);
      setLoginError(null);
    },
    [clearExpiryTimer, clearFocusTimer, clearRevalidateTimer, invalidateProbes, syncFromRuntime],
  );

  const scheduleExpiry = useCallback(
    (iso: string) => {
      clearExpiryTimer();
      const ms = Date.parse(iso) - Date.now();
      if (!Number.isFinite(ms) || ms <= 0) {
        flushSync(() => {
          lockUi("locked", "expired");
        });
        void startProbeRef.current("forced", "expired");
        return;
      }
      expiryTimer.current = setTimeout(() => {
        flushSync(() => {
          lockUi("locked", "expired");
        });
        void startProbeRef.current("forced", "expired");
      }, ms);
    },
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

      lockUi("locked", "unauthorized");
    },
    [clearExpiryTimer, lockUi, scheduleExpiry, syncFromRuntime],
  );

  const startProbe = useCallback(
    async (kind: ProbeKind, probeReason: AuthReason = "initial"): Promise<void> => {
      // Focus probes for the same auth generation may share one in-flight probe.
      if (
        kind === "focus" &&
        focusProbePromise.current &&
        activeProbe.current?.kind === "focus" &&
        activeProbe.current.authGeneration === authRuntime.getGeneration()
      ) {
        return focusProbePromise.current;
      }

      // Forced probes (401/logout/bfcache/login) invalidate earlier probes.
      if (kind !== "focus") {
        invalidateProbes();
      } else if (
        activeProbe.current &&
        activeProbe.current.kind !== "focus" &&
        activeProbe.current.sequence === probeSequence.current
      ) {
        // A forced probe is already running — do not start a focus probe.
        return;
      }

      const sequence = (probeSequence.current += 1);
      const handle: ProbeHandle = {
        sequence,
        authGeneration: authRuntime.getGeneration(),
        kind,
      };
      activeProbe.current = handle;

      const run = (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!isProbeCurrent(handle)) return;
          setReason(probeReason);
          unlockFromStatus(status);
        } catch (error) {
          if (!isProbeCurrent(handle)) return;
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
              // Stale network failures must not overwrite a newer authenticated state.
              if (phaseRef.current === "authenticated" && kind === "focus") {
                return;
              }
              lockUi("unreachable", "network");
              return;
            }
            if (error.kind === "stale_auth_context") {
              return;
            }
          }
          if (phaseRef.current === "authenticated" && kind === "focus") {
            return;
          }
          lockUi("unreachable", "network");
        } finally {
          if (activeProbe.current?.sequence === handle.sequence) {
            activeProbe.current = null;
          }
          if (focusProbePromise.current && kind === "focus") {
            focusProbePromise.current = null;
          }
        }
      })();

      if (kind === "focus") {
        focusProbePromise.current = run;
      }
      return run;
    },
    [invalidateProbes, isProbeCurrent, lockUi, unlockFromStatus],
  );
  startProbeRef.current = startProbe;

  const handleUnauthorized = useCallback(() => {
    clearFocusTimer();
    clearRevalidateTimer();
    flushSync(() => {
      setPhase("checking");
      setReason("unauthorized");
      liveConnection.setAccessEnabled(false);
      authRuntime.clear();
      syncFromRuntime();
    });
    void startProbe("unauthorized", "unauthorized");
  }, [clearFocusTimer, clearRevalidateTimer, startProbe, syncFromRuntime]);

  const handleRevalidate = useCallback(() => {
    clearRevalidateTimer();
    revalidateTimer.current = setTimeout(() => {
      void (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!status.authenticated) {
            handleUnauthorized();
            return;
          }
          if (
            status.auth_method === "session" &&
            status.csrf_token &&
            status.expires_at
          ) {
            authRuntime.updateSessionCredentials({
              csrfToken: status.csrf_token,
              expiresAt: status.expires_at,
              browserSessionEnabled: status.browser_session_enabled,
            });
            syncFromRuntime();
          }
        } catch {
          // retain current authenticated state on network failure during CSRF refresh
        }
      })();
    }, REVALIDATE_DEBOUNCE_MS);
  }, [clearRevalidateTimer, handleUnauthorized, syncFromRuntime]);

  useEffect(() => {
    mounted.current = true;
    void startProbe("initial", "initial");
    const offUnauthorized = authRuntime.onUnauthorized(handleUnauthorized);
    const offRevalidate = authRuntime.onRevalidate(handleRevalidate);
    return () => {
      mounted.current = false;
      offUnauthorized();
      offRevalidate();
      clearExpiryTimer();
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      liveConnection.setAccessEnabled(false);
    };
  }, [
    clearExpiryTimer,
    clearFocusTimer,
    clearRevalidateTimer,
    handleRevalidate,
    handleUnauthorized,
    invalidateProbes,
    startProbe,
  ]);

  // Focus / visibility / pageshow / pagehide
  useEffect(() => {
    if (phase !== "authenticated") return;

    const scheduleDebounced = () => {
      clearFocusTimer();
      focusTimer.current = setTimeout(() => {
        void startProbe("focus", "initial");
      }, REVALIDATE_DEBOUNCE_MS);
    };

    const suspendIfExpired = (): boolean => {
      const exp = authRuntime.getExpiresAt();
      if (!exp) return false;
      const ms = Date.parse(exp);
      if (Number.isNaN(ms) || ms > Date.now()) return false;
      flushSync(() => {
        lockUi("locked", "expired");
      });
      void startProbe("forced", "expired");
      return true;
    };

    const onFocus = () => {
      if (suspendIfExpired()) return;
      scheduleDebounced();
    };
    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (suspendIfExpired()) return;
      scheduleDebounced();
    };
    const onPageHide = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      clearFocusTimer();
      invalidateProbes();
      flushSync(() => {
        setPhase("checking");
        setReason("initial");
        liveConnection.setAccessEnabled(false);
      });
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        clearFocusTimer();
        flushSync(() => {
          setPhase("checking");
          setReason("initial");
          liveConnection.setAccessEnabled(false);
        });
        void startProbe("bfcache", "initial");
        return;
      }
      if (suspendIfExpired()) return;
      scheduleDebounced();
    };

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      clearFocusTimer();
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [clearFocusTimer, invalidateProbes, lockUi, phase, startProbe]);

  const login = useCallback(
    async (apiToken: string) => {
      if (loginInFlight.current) return;
      loginInFlight.current = true;
      setLoginBusy(true);
      setLoginError(null);
      invalidateProbes();
      try {
        // Construct bootstrap; do not retain the token through the round-trip.
        let tokenForBootstrap: string | undefined = apiToken;
        await createBrowserSession(tokenForBootstrap);
        tokenForBootstrap = undefined;

        let confirmed;
        try {
          confirmed = await fetchSessionStatus();
        } catch (error) {
          if (error instanceof ApiError && error.kind === "unreachable") {
            setPhase("unreachable");
            setReason("network");
            setLoginError(null);
            liveConnection.setAccessEnabled(false);
            authRuntime.clear();
            syncFromRuntime();
            return;
          }
          if (
            error instanceof ApiError &&
            (error.detail === "incomplete_session" || error.detail === "malformed")
          ) {
            setPhase("locked");
            setReason(error.detail === "incomplete_session" ? "cookie_blocked" : "protocol_error");
            setLoginError(null);
            liveConnection.setAccessEnabled(false);
            authRuntime.clear();
            syncFromRuntime();
            return;
          }
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
          if (error.kind === "origin") {
            setPhase("locked");
            setReason("origin_rejected");
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
    [invalidateProbes, syncFromRuntime, unlockFromStatus],
  );

  const logout = useCallback(async () => {
    if (logoutInFlight.current) return;
    logoutInFlight.current = true;
    setLogoutBusy(true);
    setLogoutError(null);
    clearFocusTimer();
    clearRevalidateTimer();
    invalidateProbes();
    const logoutSequence = probeSequence.current;
    try {
      await deleteBrowserSession();
      const confirmed = await fetchSessionStatus();
      if (logoutSequence !== probeSequence.current) return;
      if (confirmed.authenticated) {
        setLogoutError("Sign out could not be confirmed. Retry or clear site cookies.");
        return;
      }
      lockUi("locked", "logged_out");
      setLogoutError(null);
    } catch (error) {
      if (logoutSequence !== probeSequence.current) return;
      if (error instanceof ApiError && error.status === 401) {
        await startProbe("logout", "logged_out");
        return;
      }
      if (error instanceof ApiError && error.kind === "csrf") {
        setLogoutError("Session security check failed. Retry sign out.");
        return;
      }
      if (error instanceof ApiError && error.kind === "unreachable") {
        setLogoutError("Could not reach Core to sign out. Your session may still be active.");
        return;
      }
      setLogoutError("Sign out failed. Retry.");
    } finally {
      logoutInFlight.current = false;
      setLogoutBusy(false);
    }
  }, [
    clearFocusTimer,
    clearRevalidateTimer,
    invalidateProbes,
    lockUi,
    startProbe,
  ]);

  const retry = useCallback(async () => {
    setPhase("checking");
    setLoginError(null);
    setLogoutError(null);
    await startProbe("forced", "initial");
  }, [startProbe]);

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
      logoutBusy,
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
      logoutBusy,
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
