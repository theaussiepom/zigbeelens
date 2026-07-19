import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/BrowserAuthContext";
import { useScenario } from "@/context/ScenarioContext";
import { useConnection } from "@/hooks/useConnection";
import { scenariosEnabled } from "@/lib/flags";

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

const nav = [
  { to: "/", label: "Overview", end: true },
  { to: "/incidents", label: "Incidents" },
  { to: "/monitoring", label: "How it works" },
  { to: "/networks", label: "Networks" },
  { to: "/routers", label: "Routers" },
  { to: "/topology", label: "Topology" },
  { to: "/devices", label: "Devices" },
  { to: "/timeline", label: "Timeline" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

function navClass(isActive: boolean): string {
  return `block rounded-lg px-3 py-2.5 min-h-11 text-sm font-medium transition-colors ${
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

export function AppShell() {
  const { scenario, setScenario, scenarios, status } = useScenario();
  const auth = useAuth();
  const sessionExpiryLabel = formatSessionExpiry(auth.expiresAt);

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
          {nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => navClass(isActive)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-zl-border p-4 text-xs text-zl-muted space-y-1">
          <div>Mode: {status?.data_mode ?? "—"}</div>
          <div>v{status?.version ?? "0.1.0"}</div>
          {auth.authMethod === "trusted_local" && <div>Trusted local access</div>}
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

        <nav className="flex gap-1 overflow-x-auto scroll-px-3 border-b border-zl-border bg-zl-surface px-3 py-2 lg:hidden" aria-label="Main navigation">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-2 min-h-11 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-zl-accent/15 text-zl-accent"
                    : "text-zl-muted hover:bg-zl-surface-2 hover:text-zl-text active:bg-zl-surface-2"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <ModeBanner />

        <main className="flex-1 overflow-auto p-4 sm:p-6 pb-[max(1rem,env(safe-area-inset-bottom))]" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
