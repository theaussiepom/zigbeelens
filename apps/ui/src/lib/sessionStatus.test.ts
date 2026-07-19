import { describe, expect, it } from "vitest";
import { parseBrowserSessionStatus } from "./sessionStatus";

describe("parseBrowserSessionStatus", () => {
  it("accepts trusted_local with null expiry and csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "trusted_local",
      browser_session_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects trusted_local with csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "trusted_local",
      browser_session_enabled: false,
      expires_at: null,
      csrf_token: "x",
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
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

  it("rejects session csrf with surrounding whitespace", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "  csrf-abc  ",
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
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

  it("rejects session expiry beyond Core max TTL", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 8 * 24 * 60 * 60_000).toISOString(),
      csrf_token: "csrf-abc",
    });
    expect(parsed).toEqual({ ok: false, reason: "incomplete_session" });
  });

  it("rejects unauthenticated with non-null method/csrf/expiry", () => {
    expect(
      parseBrowserSessionStatus({
        authenticated: false,
        auth_method: "session",
        browser_session_enabled: true,
        expires_at: null,
        csrf_token: null,
      }),
    ).toEqual({ ok: false, reason: "malformed" });
    expect(
      parseBrowserSessionStatus({
        authenticated: false,
        auth_method: null,
        browser_session_enabled: true,
        expires_at: new Date().toISOString(),
        csrf_token: null,
      }),
    ).toEqual({ ok: false, reason: "malformed" });
  });

  it("accepts unauthenticated null credentials", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: false,
      auth_method: null,
      browser_session_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed.ok).toBe(true);
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

  it("rejects CSRF with control characters", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "csrf\nbad",
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("rejects CSRF over Core 4096-byte maximum", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "x".repeat(4097),
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });
});
