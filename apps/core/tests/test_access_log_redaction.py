"""Uvicorn access-log request-target redaction."""

from __future__ import annotations

import logging

from zigbeelens.config.redaction import REDACTED, redact_request_target
from zigbeelens.config.security_types import SESSION_COOKIE_NAME
from zigbeelens.logging_config import (
    UvicornAccessSecretRedactionFilter,
    configure_logging,
    install_uvicorn_access_redaction_filter,
)
from zigbeelens.security.browser_sessions import SESSION_COOKIE_NAME as SESSION_COOKIE_NAME_EXPORT


def _access_record(full_path: str, *, status: int = 401) -> logging.LogRecord:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:9", "GET", full_path, "1.1", status),
        exc_info=None,
    )
    return record


def test_redact_request_target_examples():
    assert (
        redact_request_target(
            "/api/dashboard?token=secret&client_id=safe&token_count=2"
        )
        == f"/api/dashboard?token={REDACTED}&client_id=safe&token_count=2"
    )


def test_session_cookie_name_constant_matches_redaction_policy():
    """Prevent drift between the fixed cookie name and secret-key redaction."""
    assert SESSION_COOKIE_NAME == "zigbeelens_session"
    assert SESSION_COOKIE_NAME_EXPORT == SESSION_COOKIE_NAME
    assert (
        redact_request_target(
            f"/api/dashboard?{SESSION_COOKIE_NAME}=signed-cookie&client_id=safe"
        )
        == f"/api/dashboard?{SESSION_COOKIE_NAME}={REDACTED}&client_id=safe"
    )


def test_redact_request_target_session_cookie_query_key():
    signed = "eyJ.signed.cookie.value"
    target = (
        f"/api/dashboard?{SESSION_COOKIE_NAME}={signed}&client_id=safe"
        f"&{SESSION_COOKIE_NAME}=again&token_count=2"
    )
    redacted = redact_request_target(target)
    assert signed not in redacted
    assert "again" not in redacted
    assert f"{SESSION_COOKIE_NAME}={REDACTED}" in redacted
    assert "client_id=safe" in redacted
    assert "token_count=2" in redacted
    assert redacted.startswith("/api/dashboard?")
    # Percent-encoded cookie-name key (%7A... for 'z')
    encoded_key = "%7Aigbeelens_session"
    enc_redacted = redact_request_target(
        f"/api/dashboard?{encoded_key}={signed}&client_id=safe"
    )
    assert signed not in enc_redacted
    assert "client_id=safe" in enc_redacted
    assert REDACTED in enc_redacted


def test_uvicorn_access_filter_redacts_session_cookie_query():
    filt = UvicornAccessSecretRedactionFilter()
    signed = "prod-style-session-cookie"
    record = _access_record(
        f"/api/dashboard?{SESSION_COOKIE_NAME}={signed}&client_id=safe&token_count=2",
        status=200,
    )
    assert filt.filter(record) is True
    path = record.args[2]
    assert signed not in path
    assert f"{SESSION_COOKIE_NAME}={REDACTED}" in path
    assert "client_id=safe" in path
    assert "token_count=2" in path
    assert record.args[4] == 200
    rendered = record.getMessage()
    assert signed not in rendered
    assert "/api/dashboard" in rendered
    assert "200" in rendered


def test_uvicorn_access_filter_still_suppresses_unknown_shapes_with_session_key():
    filt = UvicornAccessSecretRedactionFilter()
    bad = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="unexpected %s",
        args=(f"/api/dashboard?{SESSION_COOKIE_NAME}=leaked",),
        exc_info=None,
    )
    assert filt.filter(bad) is False
    assert "leaked" in bad.args[0]


def test_redact_request_target_secret_keys_and_safe_params():
    target = (
        "/api/dashboard?"
        "token=tok-secret&"
        "access_token=at-secret&"
        "api_key=ak-secret&"
        "authorization=ah-secret&"
        "client_secret=cs-secret&"
        "oauth_token=ot-secret&"
        "client_id=safe&"
        "token_count=2&"
        "flag=&"
        "flag=again"
    )
    redacted = redact_request_target(target)
    assert "tok-secret" not in redacted
    assert "at-secret" not in redacted
    assert "ak-secret" not in redacted
    assert "ah-secret" not in redacted
    assert "cs-secret" not in redacted
    assert "ot-secret" not in redacted
    assert f"token={REDACTED}" in redacted
    assert f"access_token={REDACTED}" in redacted
    assert f"api_key={REDACTED}" in redacted
    assert f"authorization={REDACTED}" in redacted
    assert f"client_secret={REDACTED}" in redacted
    assert f"oauth_token={REDACTED}" in redacted
    assert "client_id=safe" in redacted
    assert "token_count=2" in redacted
    assert "flag=" in redacted
    assert "flag=again" in redacted
    assert redacted.startswith("/api/dashboard?")


def test_redact_request_target_percent_encoded_secret_key():
    # %74oken -> token
    redacted = redact_request_target("/api/dashboard?%74oken=leaked-value&ok=1")
    assert "leaked-value" not in redacted
    assert f"token={REDACTED}" in redacted or f"%74oken={REDACTED}" in redacted
    assert "ok=1" in redacted


def test_redact_request_target_drops_fragment():
    assert (
        redact_request_target("/api/dashboard?token=secret#api_key=fragment-secret")
        == f"/api/dashboard?token={REDACTED}"
    )
    assert "fragment-secret" not in redact_request_target(
        "/api/dashboard?client_id=safe#api_key=fragment-secret"
    )


def test_redact_request_target_malformed_secret_query_fails_closed(monkeypatch):
    from zigbeelens.config import redaction as redaction_mod

    def boom(_query: str) -> str:
        raise RuntimeError("parse failed")

    monkeypatch.setattr(redaction_mod, "_redact_param_string", boom)
    assert (
        redact_request_target("/api/dashboard?token=still-secret&client_id=safe")
        == f"/api/dashboard?{REDACTED}"
    )
    assert "still-secret" not in redact_request_target(
        "/api/dashboard?token=still-secret"
    )


def test_uvicorn_access_filter_redacts_recognised_shape():
    filt = UvicornAccessSecretRedactionFilter()
    record = _access_record(
        "/api/dashboard?token=secret&client_id=safe&token_count=2",
        status=200,
    )
    assert filt.filter(record) is True
    assert record.args is not None
    path = record.args[2]
    assert "secret" not in path
    assert f"token={REDACTED}" in path
    assert "client_id=safe" in path
    assert "token_count=2" in path
    assert record.args[0] == "127.0.0.1:9"
    assert record.args[1] == "GET"
    assert record.args[3] == "1.1"
    assert record.args[4] == 200
    # Authorization header values must never be introduced into the record.
    assert "Authorization" not in str(record.args)
    assert "Bearer" not in str(record.args)


def test_uvicorn_access_filter_suppresses_unrecognised_shape():
    filt = UvicornAccessSecretRedactionFilter()
    bad = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="unexpected %s",
        args=("/api/dashboard?token=secret",),
        exc_info=None,
    )
    assert filt.filter(bad) is False
    assert bad.args == ("/api/dashboard?token=secret",)


def test_install_uvicorn_access_filter_is_idempotent():
    access = logging.getLogger("uvicorn.access")
    before = len(access.filters)
    install_uvicorn_access_redaction_filter()
    install_uvicorn_access_redaction_filter()
    marked = [
        f
        for f in access.filters
        if getattr(f, "_zigbeelens_uvicorn_access_redaction", False)
    ]
    assert len(marked) == 1
    assert len(access.filters) >= before


def test_configure_logging_redacts_uvicorn_access_message(monkeypatch):
    monkeypatch.delenv("ZIGBEELENS_LOG_LEVEL", raising=False)
    configure_logging()
    access = logging.getLogger("uvicorn.access")
    handler = logging.Handler()
    records: list[logging.LogRecord] = []

    def emit(record: logging.LogRecord) -> None:
        records.append(record)

    handler.emit = emit  # type: ignore[method-assign]
    access.addHandler(handler)
    try:
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:9",
            "GET",
            "/api/dashboard?token=prod-style-secret&client_id=safe",
            "1.1",
            401,
        )
        assert len(records) == 1
        rendered = records[0].getMessage()
        assert "prod-style-secret" not in rendered
        assert f"token={REDACTED}" in rendered
        assert "client_id=safe" in rendered
        assert "401" in rendered
        assert "/api/dashboard" in rendered
    finally:
        access.removeHandler(handler)
