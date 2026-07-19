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
  /** Protected-access generation (remount / stale-work boundary). */
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
  | "csrf_refresh"
  | "sse_error";

type ProbeHandle = {
  sequence: number;
  identityGeneration: number;
  accessGeneration: number;
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
  // CSRF grammar already enforced by parseBrowserSessionStatus before this runs.
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
    setAuthEpoch(authRuntime.getAccessGeneration());
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
    if (logoutInFlight.current && handle.kind !== "logout") return false;

    const identityStableKinds: ProbeKind[] = [
      "focus",
      "csrf_refresh",
      "sse_error",
    ];
    if (identityStableKinds.includes(handle.kind)) {
      if (handle.identityGeneration !== authRuntime.getIdentityGeneration()) return false;
      if (handle.accessGeneration !== authRuntime.getAccessGeneration()) return false;
    } else if (handle.kind === "login") {
      if (bfcacheSuspended.current) return false;
      if (handle.accessGeneration !== authRuntime.getAccessGeneration()) return false;
    } else if (handle.kind === "logout") {
      if (handle.accessGeneration !== authRuntime.getAccessGeneration()) return false;
    } else {
      // Transition-owning probes: sequence ownership is primary; access may change
      // only via this probe's own apply/lock path after acceptance.
      if (handle.accessGeneration !== authRuntime.getAccessGeneration()) {
        // Allow when this probe is still the active owner (same sequence).
        if (activeProbe.current?.sequence !== handle.sequence) return false;
      }
    }
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
      liveConnection.clearPendingSessionProbe();
      liveConnection.setAccessEnabled(false);
      const accessBefore = authRuntime.getAccessGeneration();
      clearAuthenticatedIdentity();
      if (authRuntime.getAccessGeneration() === accessBefore) {
        authRuntime.advanceAccessGeneration();
      }
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
        // Keep logoutError sticky across CSRF/focus refresh so CSRF-403 logout
        // can still tell the user to retry after ownership release.
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
        kind === "focus" || kind === "csrf_refresh" || kind === "sse_error";

      if (
        kind === "focus" &&
        focusProbePromise.current &&
        activeProbe.current?.kind === "focus" &&
        activeProbe.current.accessGeneration === authRuntime.getAccessGeneration()
      ) {
        return focusProbePromise.current;
      }

      if (kind !== "focus" && kind !== "csrf_refresh" && kind !== "sse_error") {
        invalidateProbes();
      } else if (
        activeProbe.current &&
        activeProbe.current.kind !== "focus" &&
        activeProbe.current.kind !== "csrf_refresh" &&
        activeProbe.current.kind !== "sse_error" &&
        activeProbe.current.sequence === probeSequence.current
      ) {
        return;
      }

      const sequence = (probeSequence.current += 1);
      const handle: ProbeHandle = {
        sequence,
        identityGeneration: authRuntime.getIdentityGeneration(),
        accessGeneration: authRuntime.getAccessGeneration(),
        kind,
      };
      activeProbe.current = handle;

      let run!: Promise<void>;
      run = (async () => {
        try {
          const status = await fetchSessionStatus();
          if (!isProbeCurrent(handle)) return;
          if (logoutInFlight.current && kind !== "logout") return;

          if (kind === "login") {
            if (bfcacheSuspended.current) return;
            if (!status.authenticated || status.auth_method !== "session") {
              lockUi("locked", "cookie_blocked");
              return;
            }
            applyStatus(status, "initial");
            return;
          }

          if (kind === "logout") {
            if (!status.authenticated) {
              if (!status.browser_session_enabled) {
                lockUi("setup_required", "configuration");
              } else {
                lockUi("locked", "logged_out");
              }
              setLogoutError(null);
              return;
            }
            setLogoutError("Sign out could not be confirmed. Retry or clear site cookies.");
            if (phaseRef.current === "authenticated" || authRuntime.getAuthMethod()) {
              liveConnection.setAccessEnabled(true);
              const exp = authRuntime.getExpiresAt();
              if (exp) scheduleExpiry(exp);
              setPhase("authenticated");
            }
            return;
          }

          applyStatus(status, probeReason);
        } catch (error) {
          if (!isProbeCurrent(handle)) return;
          if (logoutInFlight.current && kind !== "logout") return;
          if (error instanceof ApiError) {
            if (error.detail === "unexpected_bearer") {
              lockUi("setup_required", "configuration");
              return;
            }
            if (kind === "login") {
              if (error.kind === "unreachable") {
                lockUi("unreachable", "network");
                return;
              }
              if (error.kind === "protocol" || error.detail === "malformed") {
                lockUi("locked", "protocol_error");
                return;
              }
              if (error.detail === "incomplete_session") {
                lockUi("locked", "cookie_blocked");
                return;
              }
              lockUi("locked", "cookie_blocked");
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
              if (kind === "logout") {
                setLogoutError(
                  "Could not reach Core to sign out. Your session may still be active.",
                );
                if (authRuntime.getAuthMethod()) {
                  liveConnection.setAccessEnabled(true);
                  const exp = authRuntime.getExpiresAt();
                  if (exp) scheduleExpiry(exp);
                  setPhase("authenticated");
                }
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
    [applyStatus, invalidateProbes, isProbeCurrent, lockUi, scheduleExpiry],
  );
  startProbeRef.current = startProbe;

  const handleUnauthorized = useCallback(() => {
    if (logoutInFlight.current) return;
    clearFocusTimer();
    clearRevalidateTimer();
    liveConnection.clearPendingSessionProbe();
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

  // Initial probe + auth listeners + SSE probe ownership
  useEffect(() => {
    mounted.current = true;
    liveConnection.setSessionProbeRequester(() => {
      if (logoutInFlight.current || bfcacheSuspended.current) return;
      if (phaseRef.current !== "authenticated") return;
      void startProbeRef.current("sse_error", "unauthorized");
    });
    void startProbe("initial", "initial");
    const offUnauthorized = authRuntime.onUnauthorized(handleUnauthorized);
    const offRevalidate = authRuntime.onRevalidate(handleRevalidate);
    return () => {
      mounted.current = false;
      offUnauthorized();
      offRevalidate();
      liveConnection.setSessionProbeRequester(null);
      clearExpiryTimer();
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      liveConnection.clearPendingSessionProbe();
      liveConnection.setStatusProbesSuppressed(false);
      liveConnection.setAccessEnabled(false);
      authRuntime.advanceAccessGeneration();
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
      clearExpiryTimer();
      clearFocusTimer();
      clearRevalidateTimer();
      invalidateProbes();
      liveConnection.clearPendingSessionProbe();
      bfcacheSuspended.current = true;
      // Keep identity; advance access so in-flight protected work becomes stale.
      authRuntime.advanceAccessGeneration();
      flushSync(() => {
        syncFromRuntime();
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
    clearExpiryTimer,
    clearFocusTimer,
    clearRevalidateTimer,
    invalidateProbes,
    lockUi,
    syncFromRuntime,
  ]);

  const login = useCallback(
    (apiToken: string): Promise<void> => {
      if (loginInFlight.current) return Promise.resolve();
      loginInFlight.current = true;
      setLoginBusy(true);
      setLoginError(null);
      setLogoutError(null);
      invalidateProbes();

      let tokenRef: string | undefined = apiToken;
      const bootstrapPromise = createBrowserSession(tokenRef);
      tokenRef = undefined;

      return (async () => {
        try {
          await bootstrapPromise;
          await startProbe("login", "initial");
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
    [invalidateProbes, lockUi, startProbe],
  );

  const logout = useCallback(async () => {
    if (logoutInFlight.current) return;
    logoutInFlight.current = true;
    setLogoutBusy(true);
    setLogoutError(null);
    clearFocusTimer();
    clearRevalidateTimer();
    clearExpiryTimer();
    liveConnection.clearPendingSessionProbe();
    // Invalidate already-running protected work; keep identity until confirmed.
    authRuntime.advanceAccessGeneration();
    syncFromRuntime();
    invalidateProbes();
    liveConnection.setStatusProbesSuppressed(true);
    const expiryAtStart = authRuntime.getExpiresAt();
    let csrfRefreshAfter = false;
    try {
      await deleteBrowserSession();
      await startProbe("logout", "logged_out");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await startProbe("logout", "logged_out");
        return;
      }
      if (error instanceof ApiError && error.kind === "csrf") {
        setLogoutError("Session security check failed. Retry sign out.");
        csrfRefreshAfter = true;
        if (phaseRef.current === "authenticated" || authRuntime.getAuthMethod()) {
          liveConnection.setAccessEnabled(true);
          if (expiryAtStart) scheduleExpiry(expiryAtStart);
        }
        return;
      }
      if (error instanceof ApiError && error.kind === "unreachable") {
        setLogoutError("Could not reach Core to sign out. Your session may still be active.");
        if (phaseRef.current === "authenticated" || authRuntime.getAuthMethod()) {
          liveConnection.setAccessEnabled(true);
          if (expiryAtStart) scheduleExpiry(expiryAtStart);
          setPhase("authenticated");
        }
        return;
      }
      if (error instanceof ApiError && error.kind === "stale_auth_context") {
        // Access already advanced; confirmation/lock may still proceed via probe.
        await startProbe("logout", "logged_out");
        return;
      }
      setLogoutError("Sign out failed. Retry.");
      if (phaseRef.current === "authenticated" || authRuntime.getAuthMethod()) {
        liveConnection.setAccessEnabled(true);
        if (expiryAtStart) scheduleExpiry(expiryAtStart);
      }
    } finally {
      logoutInFlight.current = false;
      setLogoutBusy(false);
      liveConnection.setStatusProbesSuppressed(false);
      if (csrfRefreshAfter) {
        // Ownership released — run exactly one sequenced CSRF refresh; never replay DELETE.
        void startProbe("csrf_refresh", "initial");
      }
    }
  }, [
    clearExpiryTimer,
    clearFocusTimer,
    clearRevalidateTimer,
    invalidateProbes,
    scheduleExpiry,
    startProbe,
    syncFromRuntime,
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
