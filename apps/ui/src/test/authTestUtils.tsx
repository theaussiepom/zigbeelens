import { type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { render, type RenderOptions } from "@testing-library/react";
import { BrowserAuthProvider } from "@/context/BrowserAuthContext";
import { AuthGate } from "@/components/AuthGate";
import { authRuntime } from "@/lib/authRuntime";
import {
  clearSessionTransportCredentials,
  installSessionTransportCredentials,
} from "@/lib/sessionTransport";

export const SENTINEL_TOKEN = "zl-test-sentinel-token-DO-NOT-PERSIST";

/**
 * Grammar-valid CSRF tokens matching Core ItsDangerous URLSafeSerializer output
 * (url-safe base64 segments separated by `.`).
 */
export function testCsrf(label = "test"): string {
  const safe = label.replace(/[^A-Za-z0-9_-]/g, "") || "x";
  return `e30.${safe}`;
}

/** Real Core-issued sample from BrowserSessionManager.issue_csrf_token(). */
export const CORE_ISSUED_CSRF_FIXTURE =
  "eyJ2ZXJzaW9uIjoxLCJzZXNzaW9uX2lkIjoiNWFiMzkwM2M5ZjBiZWZlYjQzODBlOTFjZjRlMmNlYTQifQ.bBPL3di-nSQQbHEBTrNO976JWNIn_7jYHBRaflmKoXY";

export function sessionStatus(overrides: Record<string, unknown> = {}) {
  return {
    authenticated: false,
    auth_method: null,
    browser_session_enabled: true,
    home_assistant_ingress_enabled: false,
    expires_at: null,
    csrf_token: null,
    ...overrides,
  };
}

export function futureExpiry(msFromNow = 60_000): string {
  return new Date(Date.now() + msFromNow).toISOString();
}

export function jsonResponse(body: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** Normalize fetch mock calls that may receive a Request or (url, init). */
export function fetchCallParts(call: unknown[]): {
  url: string;
  method: string;
  headers: Headers;
  credentials: RequestCredentials | undefined;
  cache: RequestCache | undefined;
  request: Request | null;
} {
  const [input, init] = call as [RequestInfo | URL, RequestInit?];
  if (input instanceof Request) {
    return {
      url: input.url,
      method: input.method.toUpperCase(),
      headers: new Headers(input.headers),
      credentials: input.credentials,
      cache: input.cache,
      request: input,
    };
  }
  return {
    url: String(input),
    method: (init?.method ?? "GET").toUpperCase(),
    headers: new Headers(init?.headers),
    credentials: init?.credentials,
    cache: init?.cache,
    request: null,
  };
}

/** Seed in-memory session auth without going through login UI. */
export function seedSessionAuth(csrf = testCsrf("seed")): void {
  const { revision } = installSessionTransportCredentials(csrf);
  authRuntime.setSession({
    expiresAt: futureExpiry(120_000),
    browserSessionEnabled: true,
    credentialRevision: revision,
  });
}

export function seedTrustedLocal(): void {
  clearSessionTransportCredentials();
  authRuntime.setTrustedLocal(false);
}

export function seedHomeAssistantIngress(): void {
  clearSessionTransportCredentials();
  authRuntime.setHomeAssistantIngress();
}

type Options = Omit<RenderOptions, "wrapper"> & {
  gated?: boolean;
};

export function renderWithAuth(ui: ReactNode, options: Options = {}) {
  const { gated = true, ...rest } = options;
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <BrowserAuthProvider>
          {gated ? <AuthGate>{children}</AuthGate> : children}
        </BrowserAuthProvider>
      </MemoryRouter>
    );
  }
  return render(ui, { wrapper: Wrapper, ...rest });
}
