import { type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { render, type RenderOptions } from "@testing-library/react";
import { BrowserAuthProvider } from "@/context/BrowserAuthContext";
import { AuthGate } from "@/components/AuthGate";
import { authRuntime } from "@/lib/authRuntime";

export const SENTINEL_TOKEN = "zl-test-sentinel-token-DO-NOT-PERSIST";

export function sessionStatus(overrides: Record<string, unknown> = {}) {
  return {
    authenticated: false,
    auth_method: null,
    browser_session_enabled: true,
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

/** Seed in-memory session auth without going through login UI. */
export function seedSessionAuth(csrf = "csrf-test-token"): void {
  authRuntime.setSession({
    csrfToken: csrf,
    expiresAt: futureExpiry(120_000),
    browserSessionEnabled: true,
  });
}

export function seedTrustedLocal(): void {
  authRuntime.setTrustedLocal(false);
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
