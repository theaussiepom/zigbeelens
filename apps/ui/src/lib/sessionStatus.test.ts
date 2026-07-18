import { describe, expect, it } from "vitest";
import { parseBrowserSessionStatus } from "./sessionStatus";

describe("parseBrowserSessionStatus", () => {
  it("accepts trusted_local", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "trusted_local",
      browser_session_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed.ok).toBe(true);
  });

  it("accepts valid session", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "csrf-abc",
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects unexpected bearer unlock", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "bearer",
      browser_session_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "unexpected_bearer" });
  });

  it("rejects session without csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "",
    });
    expect(parsed).toEqual({ ok: false, reason: "incomplete_session" });
  });

  it("rejects expired session", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() - 1_000).toISOString(),
      csrf_token: "csrf-abc",
    });
    expect(parsed).toEqual({ ok: false, reason: "incomplete_session" });
  });

  it("rejects malformed booleans", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: "yes",
      auth_method: null,
      browser_session_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("ignores unknown forward-compatible fields", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: false,
      auth_method: null,
      browser_session_enabled: true,
      expires_at: null,
      csrf_token: null,
      future_field: true,
    });
    expect(parsed.ok).toBe(true);
  });
});
