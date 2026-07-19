import { describe, expect, it } from "vitest";
import { isValidCsrfTokenGrammar, parseBrowserSessionStatus } from "./sessionStatus";
import { CORE_ISSUED_CSRF_FIXTURE } from "@/test/authTestUtils";

describe("parseBrowserSessionStatus", () => {
  it("accepts trusted_local with null expiry and csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "trusted_local",
      browser_session_enabled: false,
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
      expires_at: null,
      csrf_token: "x",
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("accepts home_assistant_ingress with null expiry and csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "home_assistant_ingress",
      browser_session_enabled: false,
      home_assistant_ingress_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects home_assistant_ingress with expiry or csrf", () => {
    expect(
      parseBrowserSessionStatus({
        authenticated: true,
        auth_method: "home_assistant_ingress",
        browser_session_enabled: false,
        home_assistant_ingress_enabled: true,
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        csrf_token: null,
      }),
    ).toEqual({ ok: false, reason: "malformed" });
    expect(
      parseBrowserSessionStatus({
        authenticated: true,
        auth_method: "home_assistant_ingress",
        browser_session_enabled: false,
        home_assistant_ingress_enabled: true,
        expires_at: null,
        csrf_token: "e30.abc",
      }),
    ).toEqual({ ok: false, reason: "malformed" });
  });

  it("does not treat home_assistant_ingress as unexpected_bearer", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "home_assistant_ingress",
      browser_session_enabled: false,
      home_assistant_ingress_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).not.toEqual({ ok: false, reason: "unexpected_bearer" });
    expect(parsed.ok).toBe(true);
  });

  it("accepts unauthenticated ingress-required status (sessions disabled)", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: false,
      auth_method: null,
      browser_session_enabled: false,
      home_assistant_ingress_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({
      ok: true,
      status: {
        authenticated: false,
        auth_method: null,
        browser_session_enabled: false,
        home_assistant_ingress_enabled: true,
        expires_at: null,
        csrf_token: null,
      },
    });
  });

  it("accepts valid session", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      home_assistant_ingress_enabled: false,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "e30.abc",
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects unexpected bearer unlock", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "bearer",
      browser_session_enabled: false,
      home_assistant_ingress_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "unexpected_bearer" });
  });

  it("rejects unknown auth methods", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "totally_new_method",
      browser_session_enabled: false,
      home_assistant_ingress_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("rejects session without csrf", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
      expires_at: new Date(Date.now() - 1_000).toISOString(),
      csrf_token: "e30.abc",
    });
    expect(parsed).toEqual({ ok: false, reason: "incomplete_session" });
  });

  it("rejects session expiry beyond Core max TTL", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      home_assistant_ingress_enabled: false,
      expires_at: new Date(Date.now() + 8 * 24 * 60 * 60_000).toISOString(),
      csrf_token: "e30.abc",
    });
    expect(parsed).toEqual({ ok: false, reason: "incomplete_session" });
  });

  it("rejects unauthenticated with non-null method/csrf/expiry", () => {
    expect(
      parseBrowserSessionStatus({
        authenticated: false,
        auth_method: "session",
        browser_session_enabled: true,
        home_assistant_ingress_enabled: false,
        expires_at: null,
        csrf_token: null,
      }),
    ).toEqual({ ok: false, reason: "malformed" });
    expect(
      parseBrowserSessionStatus({
        authenticated: false,
        auth_method: null,
        browser_session_enabled: true,
        home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("rejects missing home_assistant_ingress_enabled", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: false,
      auth_method: null,
      browser_session_enabled: true,
      expires_at: null,
      csrf_token: null,
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("rejects non-boolean home_assistant_ingress_enabled", () => {
    const parsed = parseBrowserSessionStatus({
      authenticated: false,
      auth_method: null,
      browser_session_enabled: true,
      home_assistant_ingress_enabled: "true",
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
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
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
      home_assistant_ingress_enabled: false,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: "x".repeat(4097),
    });
    expect(parsed).toEqual({ ok: false, reason: "malformed" });
  });

  it("accepts a real Core-issued CSRF fixture", () => {
    expect(isValidCsrfTokenGrammar(CORE_ISSUED_CSRF_FIXTURE)).toBe(true);
    const parsed = parseBrowserSessionStatus({
      authenticated: true,
      auth_method: "session",
      browser_session_enabled: true,
      home_assistant_ingress_enabled: false,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      csrf_token: CORE_ISSUED_CSRF_FIXTURE,
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects CSRF grammar violations", () => {
    const expiry = new Date(Date.now() + 60_000).toISOString();
    for (const csrf_token of [
      "e30.bad token",
      "e30.bad,token",
      "e30.bad:token",
      'e30."quoted"',
      "e30.emoji😀",
      "nodot",
      "e30.",
      ".sig",
    ]) {
      expect(
        parseBrowserSessionStatus({
          authenticated: true,
          auth_method: "session",
          browser_session_enabled: true,
          home_assistant_ingress_enabled: false,
          expires_at: expiry,
          csrf_token,
        }),
      ).toEqual({ ok: false, reason: "malformed" });
    }
  });
});
