import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { AuthGate } from "@/components/AuthGate";
import { BrowserAuthProvider, useAuth } from "@/context/BrowserAuthContext";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { api } from "@/lib/api";
import { authRuntime } from "@/lib/authRuntime";
import { liveConnection } from "@/lib/events";
import { eventSourceTestState } from "@/test/setup";
import {
  futureExpiry,
  jsonResponse,
  renderWithAuth,
  SENTINEL_TOKEN,
  sessionStatus,
} from "@/test/authTestUtils";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";

function ProtectedMarker() {
  return (
    <div>
      <nav aria-label="Main navigation">Protected nav</nav>
      <div data-testid="protected-data">secret-dashboard</div>
    </div>
  );
}

function AuthProbe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="phase">{auth.phase}</span>
      <span data-testid="method">{auth.authMethod ?? "none"}</span>
      <span data-testid="epoch">{auth.authEpoch}</span>
    </div>
  );
}

describe("BrowserAuthGate", () => {
  beforeEach(() => {
    authRuntime.resetForTests();
    liveConnection.resetForTests();
    eventSourceTestState.reset();
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(console, "log").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    liveConnection.resetForTests();
  });

  it("first request is credentialed GET /api/auth/session before protected UI", async () => {
    const order: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      order.push(url.includes("auth/session") ? "session" : "other");
      if (url.includes("auth/session")) {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "trusted_local",
          }),
        );
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(<ProtectedMarker />);

    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    expect(order[0]).toBe("session");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      credentials: "include",
      cache: "no-store",
    });
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.has("Authorization")).toBe(false);
    expect(eventSourceTestState.constructs).toHaveLength(0);
  });

  it("trusted_local unlocks without Sign out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({ authenticated: true, auth_method: "trusted_local" }),
        ),
      ),
    );
    renderWithAuth(
      <>
        <AuthProbe />
        <ProtectedMarker />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("method")).toHaveTextContent("trusted_local");
    expect(screen.getByTestId("protected-data")).toBeInTheDocument();
    const headers = new Headers();
    expect(authRuntime.applySessionCsrf(headers)).toBe("not_session");
  });

  it("valid session unlocks and retains CSRF in memory only", async () => {
    const expiry = futureExpiry();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "csrf-mem",
          }),
        ),
      ),
    );
    renderWithAuth(
      <>
        <AuthProbe />
        <ProtectedMarker />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    const headers = new Headers();
    expect(authRuntime.applySessionCsrf(headers)).toBe("applied");
    expect(headers.get("X-ZigbeeLens-CSRF-Token")).toBe("csrf-mem");
    expect(screen.queryByText("csrf-mem")).not.toBeInTheDocument();
    expect(JSON.stringify(authRuntime)).not.toContain("csrf-mem");
  });

  it("unauthenticated with sessions enabled shows login and no protected data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(sessionStatus({ authenticated: false }))),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument());
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Main navigation")).not.toBeInTheDocument();
    const input = screen.getByLabelText(/API token/i);
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).not.toHaveAttribute("name");
    expect(input.getAttribute("autocomplete")).not.toMatch(/password/i);
  });

  it("sessions disabled shows setup without token input", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: false,
            browser_session_enabled: false,
          }),
        ),
      ),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /setup required/i })).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText(/API token/i)).not.toBeInTheDocument();
    expect(screen.getByText(/security.api_token/)).toBeInTheDocument();
    expect(screen.getByText(/security.session_secret/)).toBeInTheDocument();
  });

  it("network error shows unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /not reachable/i })).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("unexpected bearer status does not unlock", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          authenticated: true,
          auth_method: "bearer",
          browser_session_enabled: false,
          expires_at: null,
          csrf_token: null,
        }),
      ),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /setup required/i })).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("login exchanges token once, clears input, verifies cookie round-trip", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("auth/session") && method === "GET") {
        // After POST, cookie round-trip succeeds.
        if (fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")) {
          return jsonResponse(
            sessionStatus({
              authenticated: true,
              auth_method: "session",
              browser_session_enabled: true,
              expires_at: futureExpiry(),
              csrf_token: "csrf-after-login",
            }),
          );
        }
        return jsonResponse(sessionStatus({ authenticated: false }));
      }
      if (url.includes("auth/session") && method === "POST") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: futureExpiry(),
            csrf_token: "csrf-post",
          }),
        );
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(
      <>
        <AuthProbe />
        <ProtectedMarker />
      </>,
    );
    await waitFor(() => screen.getByLabelText(/API token/i));

    const input = screen.getByLabelText(/API token/i) as HTMLInputElement;
    await user.type(input, SENTINEL_TOKEN);
    await user.click(screen.getByRole("button", { name: /Unlock/i }));

    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("protected-data")).toBeInTheDocument();

    const postCall = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === "POST");
    expect(postCall).toBeTruthy();
    const postHeaders = new Headers(postCall?.[1]?.headers);
    expect(postHeaders.get("Authorization")).toBe(`Bearer ${SENTINEL_TOKEN}`);
    expect(postHeaders.has("X-ZigbeeLens-CSRF-Token")).toBe(false);

    expect(input.value).toBe("");
    expect(document.body.textContent).not.toContain(SENTINEL_TOKEN);
    expect(localStorage.getItem("zigbeelens-scenario") === SENTINEL_TOKEN).toBe(false);
    expect(sessionStorage.length === 0 || !sessionStorage.getItem(SENTINEL_TOKEN)).toBe(true);
    for (const key of Object.keys(localStorage)) {
      expect(localStorage.getItem(key)).not.toContain(SENTINEL_TOKEN);
    }
    const csrfHeaders = new Headers();
    expect(authRuntime.applySessionCsrf(csrfHeaders)).toBe("applied");
    expect(csrfHeaders.get("X-ZigbeeLens-CSRF-Token")).toBe("csrf-after-login");
    expect(document.body.textContent).not.toContain("csrf-after-login");
  });

  it("POST 200 without cookie round-trip stays locked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: futureExpiry(),
            csrf_token: "csrf-post",
          }),
        );
      }
      return jsonResponse(sessionStatus({ authenticated: false }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => screen.getByLabelText(/API token/i));
    await user.type(screen.getByLabelText(/API token/i), SENTINEL_TOKEN);
    await user.click(screen.getByRole("button", { name: /Unlock/i }));

    await waitFor(() =>
      expect(screen.getByText(/did not retain the session cookie/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("wrong token shows generic message and stays locked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        return jsonResponse({ detail: "Authentication required." }, 401);
      }
      return jsonResponse(sessionStatus({ authenticated: false }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => screen.getByLabelText(/API token/i));
    await user.type(screen.getByLabelText(/API token/i), SENTINEL_TOKEN);
    await user.click(screen.getByRole("button", { name: /Unlock/i }));

    await waitFor(() => expect(screen.getByText(/Token was not accepted/i)).toBeInTheDocument());
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(SENTINEL_TOKEN);
  });

  it("protected 401 unmounts protected tree and clears CSRF", async () => {
    const expiry = futureExpiry();
    let sessionAuthenticated = true;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("auth/session")) {
        return jsonResponse(
          sessionAuthenticated
            ? sessionStatus({
                authenticated: true,
                auth_method: "session",
                browser_session_enabled: true,
                expires_at: expiry,
                csrf_token: "csrf-live",
              })
            : sessionStatus({ authenticated: false }),
        );
      }
      if (url.includes("config/status")) {
        return jsonResponse({
          version: "0.1.0",
          uptime_seconds: 1,
          data_mode: "live",
          mqtt_connected: true,
          storage_ready: true,
          storage_path: "/data",
          retention_days: 7,
          mqtt_server: "mqtt",
          configured_networks: [],
          features: {},
          active_scenario: null,
        });
      }
      if (url.includes("scenarios") || url.includes("health")) {
        if (url.includes("health") && !sessionAuthenticated) {
          return jsonResponse({ detail: "Authentication required." }, 401);
        }
        if (url.includes("scenarios")) {
          return jsonResponse([]);
        }
        return jsonResponse({ status: "ok", collector: {} });
      }
      return jsonResponse({ detail: "Authentication required." }, 401);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <BrowserAuthProvider>
          <AuthGate>
            <ScenarioProvider>
              <ProtectedMarker />
              <AuthProbe />
              <button
                type="button"
                onClick={() => {
                  sessionAuthenticated = false;
                  void api.health().catch(() => {});
                }}
              >
                Trigger 401
              </button>
            </ScenarioProvider>
          </AuthGate>
        </BrowserAuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    expect(authRuntime.applySessionCsrf(new Headers())).toBe("applied");

    await act(async () => {
      screen.getByRole("button", { name: /Trigger 401/i }).click();
    });

    await waitFor(() => expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument());
    expect(screen.queryByLabelText("Main navigation")).not.toBeInTheDocument();
    expect(authRuntime.applySessionCsrf(new Headers())).toBe("not_session");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );
  });

  it("deferred protected response after logout does not repopulate UI", async () => {
    const expiry = futureExpiry();
    let resolveHealth: ((value: Response) => void) | null = null;
    const healthPromise = new Promise<Response>((resolve) => {
      resolveHealth = resolve;
    });

    let authed = true;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("auth/session") && method === "DELETE") {
        authed = false;
        return new Response(null, { status: 204 });
      }
      if (url.includes("auth/session")) {
        return jsonResponse(
          authed
            ? sessionStatus({
                authenticated: true,
                auth_method: "session",
                browser_session_enabled: true,
                expires_at: expiry,
                csrf_token: "csrf-d",
              })
            : sessionStatus({ authenticated: false }),
        );
      }
      if (url.includes("health")) {
        return healthPromise;
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    function DeferredPage() {
      const auth = useAuth();
      const [healthLabel, setHealthLabel] = useState<string | null>(null);
      const epochAtRender = auth.authEpoch;
      return (
        <div>
          <AuthProbe />
          {healthLabel && <div data-testid="health-label">{healthLabel}</div>}
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
          <button
            type="button"
            onClick={() => {
              const startedEpoch = epochAtRender;
              void api
                .health()
                .then((h) => {
                  if (startedEpoch !== authRuntime.getEpoch()) return;
                  setHealthLabel(String(h.status));
                })
                .catch(() => {});
            }}
          >
            Start deferred
          </button>
        </div>
      );
    }

    renderWithAuth(<DeferredPage />);
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));

    await act(async () => {
      screen.getByRole("button", { name: /Start deferred/i }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );

    await act(async () => {
      resolveHealth?.(jsonResponse({ status: "ok", collector: {} }));
      await Promise.resolve();
    });

    expect(screen.queryByTestId("health-label")).not.toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("token sentinel never appears in storage or console after failed login", async () => {
    const user = userEvent.setup();
    const setItemLocal = vi.spyOn(Storage.prototype, "setItem");
    const fetchMock = vi.fn(async (_i: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        return jsonResponse({ detail: "Authentication required." }, 401);
      }
      return jsonResponse(sessionStatus({ authenticated: false }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => screen.getByLabelText(/API token/i));
    await user.type(screen.getByLabelText(/API token/i), SENTINEL_TOKEN);
    await user.click(screen.getByRole("button", { name: /Unlock/i }));
    await waitFor(() => expect(screen.getByText(/Token was not accepted/i)).toBeInTheDocument());

    for (const call of setItemLocal.mock.calls) {
      expect(String(call[0])).not.toContain(SENTINEL_TOKEN);
      expect(String(call[1])).not.toContain(SENTINEL_TOKEN);
    }
    for (const spy of [console.error, console.warn, console.log] as const) {
      for (const args of (spy as unknown as { mock: { calls: unknown[][] } }).mock.calls) {
        expect(JSON.stringify(args)).not.toContain(SENTINEL_TOKEN);
      }
    }
  });

  it("same-session status refresh leaves authEpoch unchanged", async () => {
    const expiry = futureExpiry();
    const status = sessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: expiry,
      csrf_token: "csrf-stable",
    });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status));
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<AuthProbe />);
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    const epochBefore = Number(screen.getByTestId("epoch").textContent);
    const callsBefore = fetchMock.mock.calls.length;
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore));
    expect(Number(screen.getByTestId("epoch").textContent)).toBe(epochBefore);
  });

  it("ScenarioProvider does not mount while locked", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("auth/session")) {
        return jsonResponse(sessionStatus({ authenticated: false }));
      }
      throw new Error(`unexpected protected call: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <BrowserAuthProvider>
          <AuthGate>
            <ScenarioProvider>
              <div data-testid="scenario-child">scenario</div>
            </ScenarioProvider>
          </AuthGate>
        </BrowserAuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => screen.getByRole("heading", { name: /locked/i }));
    expect(screen.queryByTestId("scenario-child")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every((c) => String(c[0]).includes("auth/session"))).toBe(true);
  });
});

describe("SSE access gate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    liveConnection.resetForTests();
    eventSourceTestState.reset();
  });

  it("does not construct EventSource while locked and uses withCredentials when enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(sessionStatus({ authenticated: false })));
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => screen.getByRole("heading", { name: /locked/i }));

    liveConnection.subscribeEvents(() => {});
    expect(eventSourceTestState.constructs).toHaveLength(0);

    // Unlock via runtime + enable access as AuthGate would.
    liveConnection.setAccessEnabled(true);
    liveConnection.subscribeEvents(() => {});
    expect(eventSourceTestState.constructs.length).toBeGreaterThanOrEqual(1);
    expect(eventSourceTestState.constructs.at(-1)?.withCredentials).toBe(true);
    expect(eventSourceTestState.constructs.at(-1)?.url).not.toMatch(/token|csrf/i);

    liveConnection.setAccessEnabled(false);
    expect(eventSourceTestState.closeCount).toBeGreaterThanOrEqual(1);
  });

  it("incomplete session status on EventSource error locks via unauthorized", async () => {
    const listener = vi.fn();
    authRuntime.onUnauthorized(listener);
    liveConnection.setAccessEnabled(true);
    liveConnection.subscribeEvents(() => {});
    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeTruthy();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: new Date(Date.now() - 1000).toISOString(),
          csrf_token: "csrf-x",
        }),
      ),
    );

    await act(async () => {
      source?.onerror?.();
      await vi.waitFor(() => expect(listener).toHaveBeenCalled(), { timeout: 2000 });
    });
  });
});

describe("bfcache and expiry lifecycle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    liveConnection.resetForTests();
  });

  it("persisted pagehide moves to checking before restore", async () => {
    const expiry = futureExpiry(120_000);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "csrf-bf",
          }),
        ),
      ),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    await act(async () => {
      const event = new Event("pagehide") as PageTransitionEvent;
      Object.defineProperty(event, "persisted", { value: true });
      window.dispatchEvent(event);
    });
    expect(screen.getByRole("heading", { name: /Checking access/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("detects hidden-tab expiry immediately on visibility restore", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const start = Date.now();
    vi.setSystemTime(start);
    const expiry = new Date(start + 5_000).toISOString();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "csrf-vis",
          }),
        ),
      ),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    await act(async () => {
      vi.setSystemTime(start + 10_000);
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "visible",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});
