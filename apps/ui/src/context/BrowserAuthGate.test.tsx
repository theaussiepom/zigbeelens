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
  fetchCallParts,
  futureExpiry,
  jsonResponse,
  renderWithAuth,
  SENTINEL_TOKEN,
  sessionStatus,
} from "@/test/authTestUtils";
import { isSessionTransportActive } from "@/lib/sessionTransport";
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = fetchCallParts([input, init]).url;
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
    const first = fetchCallParts(fetchMock.mock.calls[0] ?? []);
    expect(first.credentials).toBe("include");
    expect(first.cache).toBe("no-store");
    expect(first.headers.has("Authorization")).toBe(false);
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
    expect(isSessionTransportActive()).toBe(false);
    expect("applySessionCsrf" in authRuntime).toBe(false);
  });

  it("home_assistant_ingress unlocks without Sign out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "home_assistant_ingress",
            browser_session_enabled: false,
            home_assistant_ingress_enabled: true,
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
    expect(screen.getByTestId("method")).toHaveTextContent("home_assistant_ingress");
    expect(screen.getByTestId("protected-data")).toBeInTheDocument();
    expect(isSessionTransportActive()).toBe(false);
    expect(screen.queryByRole("button", { name: /Sign out/i })).not.toBeInTheDocument();
  });

  it("ingress required when unauthenticated with sessions disabled and ingress enabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          sessionStatus({
            authenticated: false,
            browser_session_enabled: false,
            home_assistant_ingress_enabled: true,
          }),
        ),
      ),
    );
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Open ZigbeeLens through Home Assistant/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/API token/i)).not.toBeInTheDocument();
  });

  it("valid session unlocks and keeps CSRF transport-private", async () => {
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
            csrf_token: "e30.mem",
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
    expect(isSessionTransportActive()).toBe(true);
    expect(screen.queryByText("e30.mem")).not.toBeInTheDocument();
    expect(JSON.stringify(authRuntime)).not.toContain("e30.mem");
    expect(JSON.stringify(authRuntime.toJSON())).not.toContain("e30.mem");
    expect("applySessionCsrf" in authRuntime).toBe(false);
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
          home_assistant_ingress_enabled: false,
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
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "GET") {
        // After POST, cookie round-trip succeeds.
        if (fetchMock.mock.calls.some((c) => fetchCallParts(c).method === "POST")) {
          return jsonResponse(
            sessionStatus({
              authenticated: true,
              auth_method: "session",
              browser_session_enabled: true,
              expires_at: futureExpiry(),
              csrf_token: "e30.after-login",
            }),
          );
        }
        return jsonResponse(sessionStatus({ authenticated: false }));
      }
      if (call.url.includes("auth/session") && call.method === "POST") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: futureExpiry(),
            csrf_token: "e30.post",
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

    const postCall = fetchMock.mock.calls.find((c) => fetchCallParts(c).method === "POST");
    expect(postCall).toBeTruthy();
    const post = fetchCallParts(postCall ?? []);
    expect(post.headers.get("Authorization")).toBe(`Bearer ${SENTINEL_TOKEN}`);
    expect(post.headers.has("X-ZigbeeLens-CSRF-Token")).toBe(false);

    expect(input.value).toBe("");
    expect(document.body.textContent).not.toContain(SENTINEL_TOKEN);
    expect(localStorage.getItem("zigbeelens-scenario") === SENTINEL_TOKEN).toBe(false);
    expect(sessionStorage.length === 0 || !sessionStorage.getItem(SENTINEL_TOKEN)).toBe(true);
    for (const key of Object.keys(localStorage)) {
      expect(localStorage.getItem(key)).not.toContain(SENTINEL_TOKEN);
    }
    expect(isSessionTransportActive()).toBe(true);
    expect(document.body.textContent).not.toContain("e30.after-login");
    expect(JSON.stringify(authRuntime.toJSON())).not.toContain("e30.after-login");
  });

  it("POST 200 without cookie round-trip stays locked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.method === "POST") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: futureExpiry(),
            csrf_token: "e30.post",
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchCallParts([input, init]).method === "POST") {
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = fetchCallParts([input, init]).url;
      if (url.includes("auth/session")) {
        return jsonResponse(
          sessionAuthenticated
            ? sessionStatus({
                authenticated: true,
                auth_method: "session",
                browser_session_enabled: true,
                expires_at: expiry,
                csrf_token: "e30.live",
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
    expect(isSessionTransportActive()).toBe(true);

    await act(async () => {
      screen.getByRole("button", { name: /Trigger 401/i }).click();
    });

    await waitFor(() => expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument());
    expect(screen.queryByLabelText("Main navigation")).not.toBeInTheDocument();
    expect(isSessionTransportActive()).toBe(false);
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
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        authed = false;
        return new Response(null, { status: 204 });
      }
      if (call.url.includes("auth/session")) {
        return jsonResponse(
          authed
            ? sessionStatus({
                authenticated: true,
                auth_method: "session",
                browser_session_enabled: true,
                expires_at: expiry,
                csrf_token: "e30.d",
              })
            : sessionStatus({ authenticated: false }),
        );
      }
      if (call.url.includes("health")) {
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (fetchCallParts([input, init]).method === "POST") {
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
      csrf_token: "e30.stable",
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = fetchCallParts([input, init]).url;
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
    expect(fetchMock.mock.calls.every((c) => fetchCallParts(c).url.includes("auth/session"))).toBe(
      true,
    );
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

  it("EventSource error requests a provider-owned sse_error probe without fetching", async () => {
    const requester = vi.fn();
    liveConnection.setSessionProbeRequester(requester);
    liveConnection.setAccessEnabled(true);
    liveConnection.subscribeEvents(() => {});
    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeTruthy();

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      source?.onerror?.();
      await vi.waitFor(() => expect(requester).toHaveBeenCalledWith("sse_error"), {
        timeout: 2000,
      });
    });
    expect(fetchMock).not.toHaveBeenCalled();
    liveConnection.setSessionProbeRequester(null);
  });
});

describe("bfcache and expiry lifecycle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    liveConnection.resetForTests();
  });

  function dispatchPersisted(type: "pagehide" | "pageshow") {
    const event = new Event(type) as PageTransitionEvent;
    Object.defineProperty(event, "persisted", { value: true });
    window.dispatchEvent(event);
  }

  it("persisted pagehide then pageshow requires a fresh status before remount", async () => {
    const expiry = futureExpiry(120_000);
    let resolveStatus: ((value: Response) => void) | null = null;
    let statusCalls = 0;
    const fetchMock = vi.fn(async () => {
      statusCalls += 1;
      if (statusCalls === 1) {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.bf",
          }),
        );
      }
      return new Promise<Response>((resolve) => {
        resolveStatus = resolve;
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(
      <>
        <AuthProbe />
        <ProtectedMarker />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    const callsAfterAuth = fetchMock.mock.calls.length;

    await act(async () => {
      dispatchPersisted("pagehide");
    });
    expect(screen.getByRole("heading", { name: /Checking access/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();

    await act(async () => {
      dispatchPersisted("pageshow");
    });
    expect(screen.getByRole("heading", { name: /Checking access/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(callsAfterAuth + 1));

    await act(async () => {
      resolveStatus?.(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.bf",
          }),
        ),
      );
    });
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
  });

  it("persisted pageshow with unauthenticated status stays locked", async () => {
    const expiry = futureExpiry(120_000);
    let phase: "authed" | "restore" = "authed";
    const fetchMock = vi.fn(async () => {
      if (phase === "authed") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.bf2",
          }),
        );
      }
      return jsonResponse(sessionStatus({ authenticated: false }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    await act(async () => {
      dispatchPersisted("pagehide");
      phase = "restore";
      dispatchPersisted("pageshow");
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("persisted pageshow network failure is unreachable", async () => {
    const expiry = futureExpiry(120_000);
    let fail = false;
    const fetchMock = vi.fn(async () => {
      if (fail) throw new TypeError("offline");
      return jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiry,
          csrf_token: "e30.bf3",
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    await act(async () => {
      dispatchPersisted("pagehide");
      fail = true;
      dispatchPersisted("pageshow");
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /not reachable/i })).toBeInTheDocument(),
    );
  });

  it("pre-pagehide status cannot unlock after restore", async () => {
    const expiry = futureExpiry(120_000);
    let resolveStale: ((value: Response) => void) | null = null;
    let mode: "initial" | "stale_focus" | "restore" = "initial";
    const fetchMock = vi.fn(async () => {
      if (mode === "initial") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.stale-bf",
          }),
        );
      }
      if (mode === "stale_focus") {
        return new Promise<Response>((resolve) => {
          resolveStale = resolve;
        });
      }
      return jsonResponse(sessionStatus({ authenticated: false }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    mode = "stale_focus";
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(resolveStale).toBeTruthy());

    mode = "restore";
    await act(async () => {
      dispatchPersisted("pagehide");
      dispatchPersisted("pageshow");
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );

    await act(async () => {
      resolveStale?.(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.stale-bf",
          }),
        ),
      );
    });
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument();
  });

  it("bfcache listeners remain functional across multiple cycles", async () => {
    const expiry = futureExpiry(120_000);
    const fetchMock = vi.fn().mockImplementation(() =>
      jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiry,
          csrf_token: "e30.cycle",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    for (let i = 0; i < 3; i += 1) {
      await act(async () => {
        dispatchPersisted("pagehide");
      });
      expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
      await act(async () => {
        dispatchPersisted("pageshow");
      });
      await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    }
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
            csrf_token: "e30.vis",
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

describe("probe races, logout ownership, identity remount", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authRuntime.resetForTests();
    liveConnection.resetForTests();
    eventSourceTestState.reset();
  });

  it("logout confirmation wins over a stale authenticated focus probe", async () => {
    const expiry = futureExpiry();
    let resolveFocus: ((value: Response) => void) | null = null;
    let resolveDelete: ((value: Response) => void) | null = null;
    let mode: "authed" | "focus_deferred" | "deleted" = "authed";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        return new Promise<Response>((resolve) => {
          resolveDelete = resolve;
        });
      }
      if (call.url.includes("auth/session")) {
        if (mode === "focus_deferred") {
          return new Promise<Response>((resolve) => {
            resolveFocus = resolve;
          });
        }
        if (mode === "deleted") {
          return jsonResponse(sessionStatus({ authenticated: false }));
        }
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.race",
          }),
        );
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    function LogoutRace() {
      const auth = useAuth();
      return (
        <div>
          <AuthProbe />
          <ProtectedMarker />
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
        </div>
      );
    }

    renderWithAuth(<LogoutRace />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    mode = "focus_deferred";
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(resolveFocus).toBeTruthy());

    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });
    expect(screen.getByRole("heading", { name: /Signing out/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();

    mode = "deleted";
    await act(async () => {
      resolveDelete?.(new Response(null, { status: 204 }));
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );

    await act(async () => {
      resolveFocus?.(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.race",
          }),
        ),
      );
    });
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(isSessionTransportActive()).toBe(false);
  });

  it("identical status refresh preserves child state; changed session remounts", async () => {
    const expiryA = futureExpiry(120_000);
    let csrf = "e30.a";
    let expiresAt = expiryA;
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiresAt,
          csrf_token: csrf,
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    let mounts = 0;
    function StatefulChild() {
      const [n, setN] = useState(0);
      const [mountCount] = useState(() => {
        mounts += 1;
        return mounts;
      });
      return (
        <div>
          <span data-testid="mounts">{mountCount}</span>
          <span data-testid="local">{n}</span>
          <button type="button" onClick={() => setN((v) => v + 1)}>
            Inc
          </button>
        </div>
      );
    }

    renderWithAuth(
      <>
        <AuthProbe />
        <StatefulChild />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    await act(async () => {
      screen.getByRole("button", { name: /Inc/i }).click();
    });
    expect(screen.getByTestId("local")).toHaveTextContent("1");
    const mountsBefore = Number(screen.getByTestId("mounts").textContent);
    const epochBefore = Number(screen.getByTestId("epoch").textContent);

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    expect(Number(screen.getByTestId("epoch").textContent)).toBe(epochBefore);
    expect(screen.getByTestId("local")).toHaveTextContent("1");
    expect(Number(screen.getByTestId("mounts").textContent)).toBe(mountsBefore);

    csrf = "e30.b";
    expiresAt = futureExpiry(180_000);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() =>
      expect(Number(screen.getByTestId("epoch").textContent)).toBeGreaterThan(epochBefore),
    );
    expect(screen.getByTestId("local")).toHaveTextContent("0");
    expect(Number(screen.getByTestId("mounts").textContent)).toBeGreaterThan(mountsBefore);
  });

  it("malformed initial status fails closed to protocol guidance", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ authenticated: "nope" })));
    renderWithAuth(<ProtectedMarker />);
    await waitFor(() =>
      expect(screen.getByText(/Unexpected session response from Core/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("pagehide advances access generation without clearing identity", async () => {
    const expiry = futureExpiry(120_000);
    const fetchMock = vi.fn().mockImplementation(() =>
      jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiry,
          csrf_token: "e30.access",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithAuth(<AuthProbe />);
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    const identityBefore = authRuntime.getIdentityGeneration();
    const accessBefore = authRuntime.getAccessGeneration();

    await act(async () => {
      const event = new Event("pagehide") as PageTransitionEvent;
      Object.defineProperty(event, "persisted", { value: true });
      window.dispatchEvent(event);
    });

    expect(authRuntime.getIdentityGeneration()).toBe(identityBefore);
    expect(authRuntime.getAccessGeneration()).toBeGreaterThan(accessBefore);
    expect(authRuntime.getAuthMethod()).toBe("session");
    expect(isSessionTransportActive()).toBe(true);
    expect(screen.getByRole("heading", { name: /Checking access/i })).toBeInTheDocument();
  });

  it("logout CSRF 403 refreshes after ownership release without replaying DELETE", async () => {
    const expiry = futureExpiry();
    let deleteCount = 0;
    let resolveDelete: ((value: Response) => void) | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        deleteCount += 1;
        return new Promise<Response>((resolve) => {
          resolveDelete = resolve;
        });
      }
      if (call.url.includes("auth/session")) {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: deleteCount > 0 ? "e30.refreshed" : "e30.oldcsrf",
          }),
        );
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    function LogoutCsrf() {
      const auth = useAuth();
      return (
        <div>
          <AuthProbe />
          <ProtectedMarker />
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
          {auth.logoutError && <div data-testid="logout-error">{auth.logoutError}</div>}
        </div>
      );
    }

    renderWithAuth(<LogoutCsrf />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });

    expect(screen.getByRole("heading", { name: /Signing out/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(deleteCount).toBe(1);

    await act(async () => {
      resolveDelete?.(jsonResponse({ detail: "CSRF validation failed." }, 403));
    });

    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    expect(screen.getByTestId("logout-error")).toBeInTheDocument();
    expect(deleteCount).toBe(1);
    expect(isSessionTransportActive()).toBe(true);
  });

  it("stale SSE probe cannot lock a newer session", async () => {
    const expiryA = futureExpiry(120_000);
    const expiryB = futureExpiry(180_000);
    let resolveStale: ((value: Response) => void) | null = null;
    let mode: "a" | "stale" | "b" = "a";
    const fetchMock = vi.fn(async () => {
      if (mode === "a") {
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiryA,
            csrf_token: "e30.sessionA",
          }),
        );
      }
      if (mode === "stale") {
        return new Promise<Response>((resolve) => {
          resolveStale = resolve;
        });
      }
      return jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiryB,
          csrf_token: "e30.sessionB",
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithAuth(
      <>
        <AuthProbe />
        <ProtectedMarker />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));

    mode = "stale";
    // Ensure SSE is connected under the provider-owned requester.
    await waitFor(() => expect(liveConnection.isAccessEnabled()).toBe(true));
    liveConnection.subscribeEvents(() => {});
    const source = eventSourceTestState.instances.at(-1);
    expect(source).toBeTruthy();
    await act(async () => {
      source?.onerror?.();
    });
    await waitFor(() => expect(resolveStale).toBeTruthy(), { timeout: 2000 });

    mode = "b";
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(authRuntime.getExpiresAt()).toBe(expiryB), {
      timeout: 2000,
    });

    await act(async () => {
      resolveStale?.(jsonResponse(sessionStatus({ authenticated: false })));
    });
    expect(screen.getByTestId("phase")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("protected-data")).toBeInTheDocument();
    expect(authRuntime.getExpiresAt()).toBe(expiryB);
  });

  it("suspends protected tree for entire DELETE lifecycle with zero protected requests", async () => {
    const expiry = futureExpiry();
    let resolveDelete: ((value: Response) => void) | null = null;
    let deleted = false;
    const protectedUrls: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        return new Promise<Response>((resolve) => {
          resolveDelete = (value) => {
            deleted = true;
            resolve(value);
          };
        });
      }
      if (call.url.includes("auth/session")) {
        if (deleted) return jsonResponse(sessionStatus({ authenticated: false }));
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.suspend",
          }),
        );
      }
      protectedUrls.push(call.url);
      if (call.url.includes("scenarios")) return jsonResponse([]);
      if (call.url.includes("config/status")) {
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
      return jsonResponse({ status: "ok", collector: {} });
    });
    vi.stubGlobal("fetch", fetchMock);

    function LogoutPage() {
      const auth = useAuth();
      return (
        <div>
          <ProtectedMarker />
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
        </div>
      );
    }

    render(
      <MemoryRouter>
        <BrowserAuthProvider>
          <AuthProbe />
          <AuthGate>
            <ScenarioProvider>
              <div data-testid="scenario-child">scenario-mounted</div>
              <LogoutPage />
            </ScenarioProvider>
          </AuthGate>
        </BrowserAuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("scenario-child")).toBeInTheDocument());
    const protectedBefore = protectedUrls.length;
    expect(protectedBefore).toBeGreaterThan(0);

    liveConnection.subscribeEvents(() => {});
    expect(eventSourceTestState.constructs.length).toBeGreaterThan(0);
    const closesBefore = eventSourceTestState.closeCount;

    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });

    expect(screen.getByTestId("phase")).toHaveTextContent("signing_out");
    expect(screen.getByRole("heading", { name: /Signing out/i })).toBeInTheDocument();
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Main navigation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scenario-child")).not.toBeInTheDocument();
    expect(eventSourceTestState.closeCount).toBeGreaterThan(closesBefore);
    expect(resolveDelete).toBeTruthy();
    expect(protectedUrls.length).toBe(protectedBefore);

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      eventSourceTestState.instances.at(-1)?.onerror?.();
    });
    expect(protectedUrls.length).toBe(protectedBefore);

    await act(async () => {
      resolveDelete?.(new Response(null, { status: 204 }));
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("scenario-child")).not.toBeInTheDocument();
    expect(protectedUrls.length).toBe(protectedBefore);
  });

  it("network failure restores authenticated tree under newer access generation", async () => {
    const expiry = futureExpiry();
    let rejectDelete: ((reason?: unknown) => void) | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        return new Promise<Response>((_resolve, reject) => {
          rejectDelete = reject;
        });
      }
      return jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: expiry,
          csrf_token: "e30.netfail",
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    function LogoutNet() {
      const auth = useAuth();
      return (
        <div>
          <span data-testid="epoch">{auth.authEpoch}</span>
          <ProtectedMarker />
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
          {auth.logoutError && <div data-testid="logout-error">{auth.logoutError}</div>}
        </div>
      );
    }

    renderWithAuth(<LogoutNet />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    const epochBefore = Number(screen.getByTestId("epoch").textContent);

    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Signing out/i })).toBeInTheDocument();

    await act(async () => {
      rejectDelete?.(new TypeError("offline"));
    });

    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());
    expect(Number(screen.getByTestId("epoch").textContent)).toBeGreaterThan(epochBefore);
    expect(screen.getByTestId("logout-error")).toHaveTextContent(/could not reach Core/i);
    expect(isSessionTransportActive()).toBe(true);
  });

  it("unauthorized during logout forces a fresh status probe before restore", async () => {
    const expiry = futureExpiry();
    let rejectDelete: ((reason?: unknown) => void) | null = null;
    let deleteFinished = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.url.includes("auth/session") && call.method === "DELETE") {
        return new Promise<Response>((_resolve, reject) => {
          rejectDelete = (reason) => {
            deleteFinished = true;
            reject(reason);
          };
        });
      }
      if (call.url.includes("auth/session")) {
        if (deleteFinished) {
          return jsonResponse(sessionStatus({ authenticated: false }));
        }
        return jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: expiry,
            csrf_token: "e30.unauth",
          }),
        );
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    function LogoutUnauth() {
      const auth = useAuth();
      return (
        <div>
          <ProtectedMarker />
          <button type="button" onClick={() => void auth.logout()}>
            Sign out
          </button>
        </div>
      );
    }

    renderWithAuth(<LogoutUnauth />);
    await waitFor(() => expect(screen.getByTestId("protected-data")).toBeInTheDocument());

    await act(async () => {
      screen.getByRole("button", { name: /Sign out/i }).click();
    });
    expect(screen.getByRole("heading", { name: /Signing out/i })).toBeInTheDocument();

    await act(async () => {
      authRuntime.notifyUnauthorized();
    });

    await act(async () => {
      rejectDelete?.(new TypeError("offline"));
    });

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /locked/i })).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("protected-data")).not.toBeInTheDocument();
  });

  it("deferred bootstrap releases token from input before confirmation GET", async () => {
    const user = userEvent.setup();
    let resolveBootstrap: ((value: Response) => void) | null = null;
    let bootstrapped = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = fetchCallParts([input, init]);
      if (call.method === "POST") {
        bootstrapped = true;
        return new Promise<Response>((resolve) => {
          resolveBootstrap = resolve;
        });
      }
      if (!bootstrapped) {
        return jsonResponse(sessionStatus({ authenticated: false }));
      }
      return jsonResponse(
        sessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          expires_at: futureExpiry(),
          csrf_token: "e30.boot",
        }),
      );
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

    expect(input.value).toBe("");
    expect(document.body.textContent).not.toContain(SENTINEL_TOKEN);
    expect(JSON.stringify(authRuntime.toJSON())).not.toContain(SENTINEL_TOKEN);

    const post = fetchMock.mock.calls.find((c) => fetchCallParts(c).method === "POST");
    expect(fetchCallParts(post ?? []).headers.get("Authorization")).toBe(
      `Bearer ${SENTINEL_TOKEN}`,
    );

    await act(async () => {
      resolveBootstrap?.(
        jsonResponse(
          sessionStatus({
            authenticated: true,
            auth_method: "session",
            browser_session_enabled: true,
            expires_at: futureExpiry(),
            csrf_token: "e30.boot",
          }),
        ),
      );
    });
    await waitFor(() => expect(screen.getByTestId("phase")).toHaveTextContent("authenticated"));
    const confirmation = fetchMock.mock.calls
      .map((c) => fetchCallParts(c))
      .filter((c) => c.url.includes("auth/session") && c.method === "GET")
      .at(-1);
    expect(confirmation?.headers.has("Authorization")).toBe(false);
  });
});
