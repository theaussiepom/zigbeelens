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
import {
  clearSessionTransportCredentials,
  installSessionTransportCredentials,
} from "@/lib/sessionTransport";
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

type ProbeKind =
  | "focus"
  | "forced"
  | "initial"
  | "unauthorized"
  | "logout"
  | "login"
  | "bfcache"
  | "csrf_refresh";

type ProbeHandle = {
  sequence: number;
  authGeneration: number;
  kind: ProbeKind;
};

type SessionStatus = {
  authenticated: boolean;
  auth_method: "trusted_local" | "bearer" | "session" | null;
  browser_session_enabled: boolean;
  expires_at: string | null;
  csrf_token: string | null;
};

function installAuthenticatedIdentity(status: SessionStatus): void {
  if (status.auth_method === "trusted_local") {
    clearSessionTransportCredentials();
    authRuntime.setTrustedLocal(status.browser_session_enabled);
    return;
  }
  const { revision } = installSessionTransportCredentials(status.csrf_token!);
  authRuntime.setSession({
    expiresAt: status.expires_at!,
    browserSessionEnabled: status.browser_session_enabled,
    credentialRevision: revision,
  });
}

function clearAuthenticatedIdentity(): void {
  clearSessionTransportCredentials();
  authRuntime.clear();
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
  const bfcacheSuspended = useRef(false);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const revalidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  const phaseRef = useRef<AuthPhase>(phase);
  phaseRef.current = phase;
  const startProbeRef = useRef<(kind: ProbeKind, probeReason?: AuthReason) => Promise<void>>(
    async () => {},
  );

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
    if (!mounted.current) return false;
    if (activeProbe.current?.sequence !== handle.sequence) return false;
    if (handle.sequence !== probeSequence.current) return false;
    // Focus/CSRF refresh must still match the generation they observed.
    // Transition-owning probes may clear/replace identity mid-flight.
    if (handle.kind === "focus" || handle.kind === "csrf_refresh") {
      if (handle.authGeneration !== authRuntime.getGeneration()) return false;
    }
    if (logoutInFlight.current && handle.kind !== "logout") return false;
    return true;
  }, []);

  const lockUi = useCallback(
    (next: AuthPhase, nextReason: AuthReason) => {
      clearExpiryTimer();
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      bfcacheSuspended.current = false;
      liveConnection.setStatusProbesSuppressed(false);
      liveConnection.setAccessEnabled(false);
      clearAuthenticatedIdentity();
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

  const applyStatus = useCallback(
    (status: SessionStatus, probeReason: AuthReason) => {
      if (!status.authenticated) {
        if (!status.browser_session_enabled) {
          lockUi("setup_required", "configuration");
          return;
        }
        const lockReason =
          probeReason === "logged_out" ||
          probeReason === "expired" ||
          probeReason === "unauthorized"
            ? probeReason
            : "unauthorized";
        lockUi("locked", lockReason);
        return;
      }
      setReason(probeReason);
      if (status.auth_method === "trusted_local" || status.auth_method === "session") {
        installAuthenticatedIdentity(status);
        syncFromRuntime();
        if (status.auth_method === "session") {
          scheduleExpiry(status.expires_at!);
        } else {
          clearExpiryTimer();
        }
        bfcacheSuspended.current = false;
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
      if (logoutInFlight.current && kind !== "logout") {
        return;
      }

      const retainOnNetwork =
        kind === "focus" || kind === "csrf_refresh";

      if (
        kind === "focus" &&
        focusProbePromise.current &&
        activeProbe.current?.kind === "focus" &&
        activeProbe.current.authGeneration === authRuntime.getGeneration()
      ) {
        return focusProbePromise.current;
      }

      if (kind !== "focus" && kind !== "csrf_refresh") {
        invalidateProbes();
      } else if (
        activeProbe.current &&
        activeProbe.current.kind !== "focus" &&
        activeProbe.current.kind !== "csrf_refresh" &&
        activeProbe.current.sequence === probeSequence.current
      ) {
        return;
      }

      const sequence = (probeSequence.current += 1);
      const handle: ProbeHandle = {
        sequence,
        authGeneration: authRuntime.getGeneration(),
        kind,
      };
      activeProbe.current = handle;

      let run!: Promise<void>;
      run = (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!isProbeCurrent(handle)) return;
          if (logoutInFlight.current && kind !== "logout") return;
          applyStatus(status, probeReason);
        } catch (error) {
          if (!isProbeCurrent(handle)) return;
          if (logoutInFlight.current && kind !== "logout") return;
          if (error instanceof ApiError) {
            if (error.detail === "unexpected_bearer") {
              lockUi("setup_required", "configuration");
              return;
            }
            if (error.detail === "incomplete_session") {
              lockUi("locked", "unauthorized");
              return;
            }
            if (error.kind === "protocol" || error.detail === "malformed") {
              lockUi("locked", "protocol_error");
              return;
            }
            if (error.kind === "unreachable") {
              if (retainOnNetwork && phaseRef.current === "authenticated") {
                return;
              }
              lockUi("unreachable", "network");
              return;
            }
            if (error.kind === "stale_auth_context") {
              return;
            }
          }
          if (retainOnNetwork && phaseRef.current === "authenticated") {
            return;
          }
          lockUi("unreachable", "network");
        } finally {
          if (activeProbe.current?.sequence === handle.sequence) {
            activeProbe.current = null;
          }
          if (kind === "focus" && focusProbePromise.current === run) {
            focusProbePromise.current = null;
          }
        }
      })();

      if (kind === "focus") {
        focusProbePromise.current = run;
      }
      return run;
    },
    [applyStatus, invalidateProbes, isProbeCurrent, lockUi],
  );
  startProbeRef.current = startProbe;

  const handleUnauthorized = useCallback(() => {
    if (logoutInFlight.current) return;
    clearFocusTimer();
    clearRevalidateTimer();
    flushSync(() => {
      setPhase("checking");
      setReason("unauthorized");
      liveConnection.setAccessEnabled(false);
      clearAuthenticatedIdentity();
      syncFromRuntime();
    });
    void startProbe("unauthorized", "unauthorized");
  }, [clearFocusTimer, clearRevalidateTimer, startProbe, syncFromRuntime]);

  const handleRevalidate = useCallback(() => {
    if (logoutInFlight.current) return;
    clearRevalidateTimer();
    revalidateTimer.current = setTimeout(() => {
      if (logoutInFlight.current) return;
      void startProbe("csrf_refresh", "initial");
    }, REVALIDATE_DEBOUNCE_MS);
  }, [clearRevalidateTimer, startProbe]);

  // Initial probe + auth listeners
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
      liveConnection.setStatusProbesSuppressed(false);
      liveConnection.setAccessEnabled(false);
      clearSessionTransportCredentials();
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

  // Always-mounted pagehide/pageshow; focus/visibility only when authenticated.
  useEffect(() => {
    const scheduleDebouncedFocus = () => {
      if (phaseRef.current !== "authenticated") return;
      if (logoutInFlight.current || bfcacheSuspended.current) return;
      clearFocusTimer();
      focusTimer.current = setTimeout(() => {
        if (phaseRef.current !== "authenticated") return;
        if (logoutInFlight.current || bfcacheSuspended.current) return;
        void startProbeRef.current("focus", "initial");
      }, REVALIDATE_DEBOUNCE_MS);
    };

    const suspendIfExpired = (): boolean => {
      if (phaseRef.current !== "authenticated") return false;
      const exp = authRuntime.getExpiresAt();
      if (!exp) return false;
      const ms = Date.parse(exp);
      if (Number.isNaN(ms) || ms > Date.now()) return false;
      flushSync(() => {
        lockUi("locked", "expired");
      });
      void startProbeRef.current("forced", "expired");
      return true;
    };

    const onFocus = () => {
      if (suspendIfExpired()) return;
      scheduleDebouncedFocus();
    };
    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (suspendIfExpired()) return;
      scheduleDebouncedFocus();
    };
    const onPageHide = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      bfcacheSuspended.current = true;
      flushSync(() => {
        setPhase("checking");
        setReason("initial");
        liveConnection.setAccessEnabled(false);
      });
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        clearFocusTimer();
        clearRevalidateTimer();
        bfcacheSuspended.current = true;
        flushSync(() => {
          setPhase("checking");
          setReason("initial");
          liveConnection.setAccessEnabled(false);
        });
        void startProbeRef.current("bfcache", "initial");
        return;
      }
      if (suspendIfExpired()) return;
      scheduleDebouncedFocus();
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
  }, [
    clearFocusTimer,
    clearRevalidateTimer,
    invalidateProbes,
    lockUi,
  ]);

  const login = useCallback(
    (apiToken: string): Promise<void> => {
      if (loginInFlight.current) return Promise.resolve();
      loginInFlight.current = true;
      setLoginBusy(true);
      setLoginError(null);
      invalidateProbes();

      // Start bootstrap synchronously; release local token before awaiting.
      let tokenRef: string | undefined = apiToken;
      const bootstrapPromise = createBrowserSession(tokenRef);
      tokenRef = undefined;

      return (async () => {
        try {
          await bootstrapPromise;

          let confirmed;
          try {
            confirmed = await fetchSessionStatus();
          } catch (error) {
            if (error instanceof ApiError && error.kind === "unreachable") {
              lockUi("unreachable", "network");
              return;
            }
            if (error instanceof ApiError && error.kind === "protocol") {
              lockUi("locked", "protocol_error");
              return;
            }
            if (error instanceof ApiError && error.detail === "incomplete_session") {
              lockUi("locked", "cookie_blocked");
              return;
            }
            lockUi("locked", "cookie_blocked");
            return;
          }

          if (!confirmed.authenticated || confirmed.auth_method !== "session") {
            lockUi("locked", "cookie_blocked");
            return;
          }
          applyStatus(confirmed, "initial");
        } catch (error) {
          if (error instanceof ApiError) {
            if (error.status === 401) {
              setPhase("locked");
              setReason("unauthorized");
              setLoginError("Token was not accepted.");
              return;
            }
            if (error.status === 409 || error.kind === "session_unavailable") {
              lockUi("setup_required", "configuration");
              return;
            }
            if (error.kind === "origin") {
              setPhase("locked");
              setReason("origin_rejected");
              setLoginError(null);
              return;
            }
            if (error.kind === "unreachable") {
              lockUi("unreachable", "network");
              return;
            }
            if (error.kind === "protocol") {
              lockUi("locked", "protocol_error");
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
      })();
    },
    [applyStatus, invalidateProbes, lockUi],
  );

  const logout = useCallback(async () => {
    if (logoutInFlight.current) return;
    logoutInFlight.current = true;
    setLogoutBusy(true);
    setLogoutError(null);
    clearFocusTimer();
    clearRevalidateTimer();
    invalidateProbes();
    liveConnection.setStatusProbesSuppressed(true);
    const logoutSequence = probeSequence.current;
    const expiryAtStart = authRuntime.getExpiresAt();
    try {
      await deleteBrowserSession();
      const confirmed = await fetchSessionStatus();
      if (logoutSequence !== probeSequence.current) return;
      if (confirmed.authenticated) {
        setLogoutError("Sign out could not be confirmed. Retry or clear site cookies.");
        liveConnection.setStatusProbesSuppressed(false);
        if (phaseRef.current === "authenticated") {
          liveConnection.setAccessEnabled(true);
          if (expiryAtStart) scheduleExpiry(expiryAtStart);
        }
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
        liveConnection.setStatusProbesSuppressed(false);
        if (phaseRef.current === "authenticated") {
          liveConnection.setAccessEnabled(true);
        }
        void startProbe("csrf_refresh", "initial");
        return;
      }
      if (error instanceof ApiError && error.kind === "unreachable") {
        setLogoutError("Could not reach Core to sign out. Your session may still be active.");
        liveConnection.setStatusProbesSuppressed(false);
        if (phaseRef.current === "authenticated") {
          liveConnection.setAccessEnabled(true);
          if (expiryAtStart) scheduleExpiry(expiryAtStart);
        }
        return;
      }
      setLogoutError("Sign out failed. Retry.");
      liveConnection.setStatusProbesSuppressed(false);
      if (phaseRef.current === "authenticated") {
        liveConnection.setAccessEnabled(true);
        if (expiryAtStart) scheduleExpiry(expiryAtStart);
      }
    } finally {
      logoutInFlight.current = false;
      setLogoutBusy(false);
      if (phaseRef.current === "authenticated") {
        liveConnection.setStatusProbesSuppressed(false);
      }
    }
  }, [
    clearFocusTimer,
    clearRevalidateTimer,
    invalidateProbes,
    lockUi,
    scheduleExpiry,
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
