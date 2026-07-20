import { useEffect, useId, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/BrowserAuthContext";
import { useScenario } from "@/context/ScenarioContext";
import { useConnection } from "@/hooks/useConnection";
import { scenariosEnabled } from "@/lib/flags";
import {
  ADVANCED_NAVIGATION,
  PRIMARY_NAVIGATION,
  isAdvancedRoute,
} from "@/navigation/model";

function formatSessionExpiry(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const ms = Date.parse(expiresAt);
  if (Number.isNaN(ms)) return null;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return expiresAt;
  }
}

function navClass(isActive: boolean): string {
  return `block rounded-lg px-3 py-2.5 min-h-11 text-sm font-medium transition-colors ${
    isActive
      ? "bg-zl-accent/15 text-zl-accent"
      : "text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text active:bg-zl-surface-2"
  }`;
}

function mobileNavClass(isActive: boolean): string {
  return `whitespace-nowrap rounded-lg px-3 py-2 min-h-11 text-sm font-medium transition-colors ${
    isActive
      ? "bg-zl-accent/15 text-zl-accent"
      : "text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text active:bg-zl-surface-2"
  }`;
}

function ConnectionDot() {
  const state = useConnection();
  const { dataMode } = useScenario();
  if (dataMode !== "live") return null;
  const map = {
    open: { color: "bg-zl-healthy", label: "Live" },
    connecting: { color: "bg-zl-watch animate-pulse", label: "Connecting" },
    disconnected: { color: "bg-zl-critical", label: "Reconnecting" },
  } as const;
  const { color, label } = map[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-zl-muted" title={`Event stream: ${label}`} aria-label={`Event stream: ${label}`}>
      <span className={`h-2 w-2 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  );
}

function ModeBanner() {
  const { isScenarioMode, dataMode, mqttConnected, scenario, scenarios } = useScenario();

  if (isScenarioMode) {
    const label = scenario ? scenarios.find((s) => s.id === scenario)?.label ?? scenario : null;
    return (
      <div className="border-b border-zl-border bg-zl-accent/10 px-4 py-2 text-sm text-zl-accent break-words sm:px-6">
        Scenario mode: showing fixture data{label ? ` — ${label}` : ""}
      </div>
    );
  }

  if (dataMode === "live" && !mqttConnected) {
    return (
      <div className="border-b border-zl-watch/40 bg-zl-watch/10 px-4 py-2 text-sm text-zl-watch break-words sm:px-6">
        Live mode: Core is running, but the MQTT collector is not connected.
      </div>
    );
  }

  return (
    <div className="border-b border-zl-healthy/30 bg-zl-healthy/10 px-4 py-2 text-sm text-zl-healthy break-words sm:px-6">
      Live mode: connected to ZigbeeLens Core
    </div>
  );
}

function AdvancedNavLinks({
  pathname,
  onNavigate,
  linkClass,
}: {
  pathname: string;
  onNavigate?: () => void;
  linkClass: (isActive: boolean) => string;
}) {
  return (
    <ul className="space-y-1">
      {ADVANCED_NAVIGATION.map((item) => {
        const active = item.isActive(pathname);
        return (
          <li key={item.to}>
            <NavLink
              to={item.to}
              aria-current={active ? "page" : undefined}
              className={linkClass(active)}
              onClick={onNavigate}
            >
              {item.label}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

function DesktopAdvancedNav({ pathname }: { pathname: string }) {
  const panelId = useId();
  const onAdvanced = isAdvancedRoute(pathname);
  const [open, setOpen] = useState(onAdvanced);

  useEffect(() => {
    if (onAdvanced) {
      setOpen(true);
    }
  }, [onAdvanced]);

  return (
    <div className="mt-4 border-t border-zl-border pt-3">
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        Advanced &amp; support
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div id={panelId} className="mt-1">
          <AdvancedNavLinks pathname={pathname} linkClass={navClass} />
        </div>
      )}
    </div>
  );
}

function MobileAdvancedNav({ pathname }: { pathname: string }) {
  const panelId = useId();
  const onAdvanced = isAdvancedRoute(pathname);
  const [open, setOpen] = useState(onAdvanced);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (onAdvanced) {
      setOpen(true);
    }
  }, [onAdvanced]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    function onPointer(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        className={`whitespace-nowrap rounded-lg px-3 py-2 min-h-11 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zl-accent/50 ${
          onAdvanced || open
            ? "bg-zl-accent/15 text-zl-accent"
            : "text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text"
        }`}
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="true"
        aria-label="Advanced and support navigation"
        onClick={() => setOpen((value) => !value)}
      >
        Advanced
      </button>
      {open && (
        <div
          id={panelId}
          className="absolute right-0 z-20 mt-1 min-w-56 rounded-xl border border-zl-border bg-zl-surface p-2 shadow-lg"
        >
          <p className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zl-muted">
            Advanced &amp; support
          </p>
          <AdvancedNavLinks
            pathname={pathname}
            linkClass={navClass}
            onNavigate={() => setOpen(false)}
          />
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const { scenario, setScenario, scenarios, status } = useScenario();
  const auth = useAuth();
  const location = useLocation();
  const sessionExpiryLabel = formatSessionExpiry(auth.expiresAt);
  const pathname = location.pathname;

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-zl-border bg-zl-surface lg:flex">
        <div className="border-b border-zl-border p-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zl-accent/20 text-sm font-bold text-zl-accent">
              ZL
            </div>
            <div>
              <div className="font-semibold tracking-tight">ZigbeeLens</div>
              <div className="text-xs text-zl-muted">Read-only diagnostics</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
          {PRIMARY_NAVIGATION.map((item) => {
            const active = item.isActive(pathname);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                aria-current={active ? "page" : undefined}
                className={navClass(active)}
              >
                {item.label}
              </NavLink>
            );
          })}
          <DesktopAdvancedNav pathname={pathname} />
        </nav>
        <div className="border-t border-zl-border p-4 text-xs text-zl-muted space-y-1">
          <div>Mode: {status?.data_mode ?? "—"}</div>
          <div>v{status?.version ?? "0.1.0"}</div>
          {auth.authMethod === "trusted_local" && <div>Trusted local access</div>}
          {auth.authMethod === "home_assistant_ingress" && <div>Home Assistant ingress</div>}
          {auth.authMethod === "session" && sessionExpiryLabel && (
            <div title={sessionExpiryLabel}>Session expires {sessionExpiryLabel}</div>
          )}
          {auth.authMethod === "session" && (
            <button
              type="button"
              onClick={() => void auth.logout()}
              disabled={auth.logoutBusy}
              aria-busy={auth.logoutBusy}
              className="mt-2 min-h-11 w-full rounded-lg border border-zl-border px-3 py-2 text-left text-xs text-zl-text hover:bg-zl-surface-2 disabled:opacity-50"
            >
              {auth.logoutBusy ? "Signing out…" : "Sign out"}
            </button>
          )}
          {auth.logoutError && (
            <p className="text-zl-critical" role="alert">
              {auth.logoutError}
            </p>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-x-hidden">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zl-border bg-zl-surface/80 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <span className="font-semibold tracking-tight lg:hidden">ZigbeeLens</span>
            <h1 className="hidden text-sm font-medium text-zl-muted sm:block">
              Zigbee2MQTT observability
            </h1>
            <ConnectionDot />
            {auth.authMethod === "session" && (
              <span className="hidden text-xs text-zl-muted sm:inline" title={sessionExpiryLabel ?? undefined}>
                Browser session
              </span>
            )}
            {auth.authMethod === "trusted_local" && (
              <span className="hidden text-xs text-zl-muted sm:inline">Trusted local</span>
            )}
            {auth.authMethod === "home_assistant_ingress" && (
              <span className="hidden text-xs text-zl-muted sm:inline">Home Assistant ingress</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {auth.authMethod === "session" && (
              <button
                type="button"
                onClick={() => void auth.logout()}
                disabled={auth.logoutBusy}
                aria-busy={auth.logoutBusy}
                className="min-h-11 rounded-lg border border-zl-border px-3 py-2 text-sm hover:bg-zl-surface-2 disabled:opacity-50 lg:hidden"
              >
                {auth.logoutBusy ? "Signing out…" : "Sign out"}
              </button>
            )}
            {scenariosEnabled() && (
              <label className="flex items-center gap-2 text-sm">
                <span className="text-zl-muted" id="scenario-label">Scenario</span>
                <select
                  className="rounded-lg border border-zl-border bg-zl-bg px-3 py-2 text-sm text-zl-text w-full sm:w-auto"
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                  aria-labelledby="scenario-label"
                >
                  <option value="">Live / Core default</option>
                  {scenarios.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        </header>

        <div
          className="flex items-stretch gap-1 border-b border-zl-border bg-zl-surface px-3 py-2 lg:hidden"
          data-testid="mobile-nav-shell"
        >
          <nav
            className="flex min-w-0 flex-1 gap-1 overflow-x-auto scroll-px-3"
            aria-label="Main navigation"
            data-testid="mobile-primary-nav-scroller"
          >
            {PRIMARY_NAVIGATION.map((item) => {
              const active = item.isActive(pathname);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  aria-current={active ? "page" : undefined}
                  className={mobileNavClass(active)}
                >
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
          <MobileAdvancedNav pathname={pathname} />
        </div>

        <ModeBanner />

        <main className="flex-1 overflow-auto p-4 sm:p-6 pb-[max(1rem,env(safe-area-inset-bottom))]" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
