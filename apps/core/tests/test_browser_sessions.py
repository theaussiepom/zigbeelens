"""Track 4C browser sessions, CSRF, and session-route regressions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from zigbeelens.api.auth import AUTH_DETAIL, CSRF_DETAIL, CSRF_HEADER_NAME, ORIGIN_DETAIL
from zigbeelens.app.context import get_context
from zigbeelens.config.models import AppConfig, SecurityConfig, SecurityMode, ServerConfig
from zigbeelens.config.security_status import build_security_config_status
from zigbeelens.main import create_app
from zigbeelens.security.browser_sessions import (
    SESSION_COOKIE_NAME,
    BrowserSessionManager,
    resolve_session_cookie_secure,
)

SAME_ORIGIN = "http://testserver"
VALID_TOKEN = "b" * 32
SESSION_SECRET = "s" * 32
OTHER_TOKEN = "e" * 32


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _write_config(
    path: Path,
    *,
    security: str = "",
    host: str = "127.0.0.1",
) -> None:
    path.write_text(
        f"""
server:
  host: {host}
  port: 8377
mode:
  mock: true
storage:
  path: {path.parent / "session.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{security}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _bearer(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session_security(
    *,
    ttl: int | None = None,
    secure: str | None = None,
) -> str:
    lines = [
        "security:",
        f"  api_token: {VALID_TOKEN}",
        f"  session_secret: {SESSION_SECRET}",
    ]
    if ttl is not None:
        lines.append(f"  session_ttl_seconds: {ttl}")
    if secure is not None:
        lines.append(f"  session_cookie_secure: {secure}")
    return "\n".join(lines) + "\n"


def _client(
    tmp_path: Path,
    monkeypatch,
    *,
    security: str = "",
    host: str = "127.0.0.1",
    base_url: str = "http://testserver",
) -> TestClient:
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, security=security, host=host)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)), base_url=base_url)


def _assert_uniform_401(res) -> None:
    assert res.status_code == 401
    assert res.json() == {"detail": AUTH_DETAIL}
    assert res.headers.get("www-authenticate") == "Bearer"
    assert "no-store" in (res.headers.get("cache-control") or "").lower()


def _assert_csrf_403(res) -> None:
    assert res.status_code == 403
    assert res.json() == {"detail": CSRF_DETAIL}
    assert "no-store" in (res.headers.get("cache-control") or "").lower()
    assert res.headers.get("www-authenticate") is None


def _assert_origin_403(res) -> None:
    assert res.status_code == 403
    assert res.json() == {"detail": ORIGIN_DETAIL}
    assert "no-store" in (res.headers.get("cache-control") or "").lower()
    assert res.headers.get("www-authenticate") is None


def _mutation_headers(csrf: str, *, origin: str = SAME_ORIGIN) -> dict[str, str]:
    """Cookie-authenticated mutations require Origin and CSRF."""
    return {CSRF_HEADER_NAME: csrf, "Origin": origin}


def _login(client: TestClient) -> tuple[str, dict]:
    res = client.post("/api/auth/session", headers=_bearer())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["authenticated"] is True
    assert body["auth_method"] == "session"
    assert body["csrf_token"]
    cookie = client.cookies.get(SESSION_COOKIE_NAME)
    assert cookie
    assert SESSION_COOKIE_NAME not in res.text
    assert VALID_TOKEN not in res.text
    assert cookie not in res.text
    return body["csrf_token"], body


def test_session_secret_alone_does_not_enable_sessions():
    config = AppConfig(security=SecurityConfig(session_secret=SESSION_SECRET))
    status = build_security_config_status(config)
    assert status.browser_session_enabled is False
    assert status.csrf_protection_enabled is False
    assert status.bearer_auth_enabled is False


def test_api_token_alone_is_bearer_only():
    config = AppConfig(security=SecurityConfig(api_token=VALID_TOKEN))
    status = build_security_config_status(config)
    assert status.browser_session_enabled is False
    assert status.read_routes_require_bearer is True
    assert status.read_routes_require_authentication is True


def test_both_secrets_enable_browser_sessions():
    config = AppConfig(
        security=SecurityConfig(api_token=VALID_TOKEN, session_secret=SESSION_SECRET)
    )
    status = build_security_config_status(config)
    assert status.browser_session_enabled is True
    assert status.csrf_protection_enabled is True
    assert status.read_routes_require_bearer is False


def test_secure_resolution_loopback_and_non_loopback():
    loopback = AppConfig(
        server=ServerConfig(host="127.0.0.1"),
        security=SecurityConfig(api_token=VALID_TOKEN, session_secret=SESSION_SECRET),
    )
    remote = AppConfig(
        server=ServerConfig(host="0.0.0.0"),
        security=SecurityConfig(api_token=VALID_TOKEN, session_secret=SESSION_SECRET),
    )
    assert resolve_session_cookie_secure(loopback) is False
    assert resolve_session_cookie_secure(remote) is True
    forced = AppConfig(
        server=ServerConfig(host="127.0.0.1"),
        security=SecurityConfig(
            api_token=VALID_TOKEN,
            session_secret=SESSION_SECRET,
            session_cookie_secure=True,
        ),
    )
    assert resolve_session_cookie_secure(forced) is True


def test_ttl_bounds():
    with pytest.raises(Exception):
        SecurityConfig(api_token=VALID_TOKEN, session_secret=SESSION_SECRET, session_ttl_seconds=299)
    with pytest.raises(Exception):
        SecurityConfig(
            api_token=VALID_TOKEN,
            session_secret=SESSION_SECRET,
            session_ttl_seconds=604801,
        )
    ok = SecurityConfig(
        api_token=VALID_TOKEN,
        session_secret=SESSION_SECRET,
        session_ttl_seconds=300,
    )
    assert ok.session_ttl_seconds == 300


def test_login_sets_httponly_cookie(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_session_security(),
        base_url="https://testserver",
    ) as client:
        res = client.post("/api/auth/session", headers=_bearer())
        assert res.status_code == 200
        header = res.headers.get("set-cookie") or ""
        assert SESSION_COOKIE_NAME in header
        assert "HttpOnly" in header
        assert "SameSite=strict" in header or "SameSite=Strict" in header
        assert "Path=/" in header
        assert "Domain=" not in header
        assert "Max-Age=" in header
        assert "Secure" not in header  # loopback automatic
        assert "no-store" in (res.headers.get("cache-control") or "").lower()
        assert res.json()["csrf_token"]
        assert VALID_TOKEN not in res.text


def test_login_secure_cookie_on_non_loopback(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_session_security(),
        host="0.0.0.0",
        base_url="https://testserver",
    ) as client:
        res = client.post("/api/auth/session", headers=_bearer())
        assert res.status_code == 200
        assert "Secure" in (res.headers.get("set-cookie") or "")


def test_login_requires_bearer_and_rejects_session_bootstrap(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        _assert_uniform_401(client.post("/api/auth/session"))
        _assert_uniform_401(client.post("/api/auth/session", headers=_bearer(OTHER_TOKEN)))
        csrf, _ = _login(client)
        # Existing session alone cannot invoke login.
        client.cookies.set(SESSION_COOKIE_NAME, client.cookies.get(SESSION_COOKIE_NAME))
        res = client.post("/api/auth/session")
        _assert_uniform_401(res)
        # Token in JSON/query rejected (still needs bearer).
        _assert_uniform_401(
            client.post("/api/auth/session", json={"api_token": VALID_TOKEN})
        )
        _assert_uniform_401(
            client.post(f"/api/auth/session?token={VALID_TOKEN}")
        )
        assert csrf


def test_login_409_when_sessions_disabled_after_valid_bearer(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        _assert_uniform_401(client.post("/api/auth/session"))
        res = client.post("/api/auth/session", headers=_bearer())
        assert res.status_code == 409
        assert res.json() == {"detail": "Browser sessions are not configured."}
        assert "no-store" in (res.headers.get("cache-control") or "").lower()


def test_session_authenticates_reads_sse_download(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        csrf, _ = _login(client)
        assert client.get("/api/dashboard").status_code == 200
        assert client.get("/api/v1/dashboard").status_code == 200

        import zigbeelens.main as main_mod
        from fastapi.responses import JSONResponse

        monkeypatch.setattr(
            main_mod,
            "EventSourceResponse",
            lambda _gen: JSONResponse({"stream": "started"}),
        )
        assert client.get("/api/events/stream").status_code == 200
        assert client.get("/api/v1/events/stream").status_code == 200

        created = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers=_mutation_headers(csrf),
        )
        assert created.status_code == 200
        report_id = created.json()["id"]
        dl = client.get(f"/api/reports/{report_id}/download")
        assert dl.status_code == 200
        assert "attachment" in dl.headers.get("content-disposition", "")
        missing = client.get("/api/reports/missing/download")
        assert missing.status_code == 404


def test_auth_precedence_bearer_over_cookie(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        _login(client)
        # Malformed bearer must not fall back to cookie.
        _assert_uniform_401(
            client.get(
                "/api/dashboard",
                headers={"Authorization": "Bearer not-a-valid-token!!!!!!!!!!!!"},
            )
        )
        _assert_uniform_401(
            client.get("/api/dashboard", headers=_bearer(OTHER_TOKEN))
        )
        # Valid bearer with invalid cookie still succeeds.
        client.cookies.set(SESSION_COOKIE_NAME, "tampered-cookie-value")
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200


def test_session_status_shapes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        bare = client.get("/api/auth/session")
        assert bare.status_code == 200
        assert bare.json()["authenticated"] is False
        assert bare.json()["auth_method"] is None
        assert bare.json()["browser_session_enabled"] is True
        assert "no-store" in (bare.headers.get("cache-control") or "").lower()

        bearer = client.get("/api/auth/session", headers=_bearer())
        assert bearer.json()["auth_method"] == "bearer"
        assert bearer.json()["csrf_token"] is None

        csrf, body = _login(client)
        status = client.get("/api/auth/session").json()
        assert status["auth_method"] == "session"
        assert status["expires_at"]
        assert status["csrf_token"] == csrf or status["csrf_token"]
        assert client.get("/api/v1/auth/session").json()["authenticated"] is True
        assert SESSION_COOKIE_NAME not in bare.text
        assert VALID_TOKEN not in status.__repr__()


def test_invalid_cookie_cleared_on_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-session")
        res = client.get("/api/auth/session")
        assert res.status_code == 200
        assert res.json()["authenticated"] is False
        set_cookie = res.headers.get("set-cookie") or ""
        assert SESSION_COOKIE_NAME in set_cookie
        assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/reports",
        "/api/topology/home/capture",
        "/api/enrichment/homeassistant",
        "/api/auth/session",
    ],
)
def test_session_mutations_require_csrf(tmp_path, monkeypatch, path):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        csrf, _ = _login(client)
        method = client.delete if path == "/api/auth/session" else client.post
        kwargs: dict = {}
        if path != "/api/auth/session":
            if "reports" in path:
                kwargs["json"] = {"format": "json", "redaction": {"profile": "standard"}}
            elif "capture" in path:
                kwargs["json"] = {"confirmed": True}
            else:
                kwargs["json"] = {"devices": []}

        _assert_origin_403(method(path, **kwargs))
        _assert_csrf_403(method(path, headers={"Origin": SAME_ORIGIN}, **kwargs))
        _assert_csrf_403(method(path, headers=_mutation_headers("bad"), **kwargs))
        # query CSRF rejected
        _assert_csrf_403(
            method(f"{path}?csrf_token={csrf}", headers={"Origin": SAME_ORIGIN}, **kwargs)
        )
        ok_headers = _mutation_headers(csrf)
        if path == "/api/auth/session":
            res = client.delete(path, headers=ok_headers)
            assert res.status_code == 204
        else:
            res = client.post(path, headers=ok_headers, **kwargs)
            # Endpoint business rules may still 400/403 after Origin+CSRF succeed.
            assert res.status_code in {200, 400, 403}, res.text
            assert res.json().get("detail") not in {CSRF_DETAIL, ORIGIN_DETAIL}


def test_bearer_mutation_no_csrf(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers=_bearer(),
        )
        assert res.status_code == 200


def test_csrf_before_body_and_zero_sql(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter

    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        _login(client)
        import zigbeelens.api.routes as routes_mod

        ctx = get_context()
        counter = install_counter(ctx.repo)
        monkeypatch.setattr(
            routes_mod,
            "generate_report",
            MagicMock(side_effect=AssertionError("create")),
        )
        body_reads = {"n": 0}
        original = Request.body

        async def counting_body(self):
            body_reads["n"] += 1
            return await original(self)

        monkeypatch.setattr(Request, "body", counting_body)
        before = counter.stats.copy()
        body_reads["n"] = 0
        _assert_csrf_403(
            client.post(
                "/api/reports",
                content="{",
                headers={
                    "Content-Type": "application/json",
                    "Origin": SAME_ORIGIN,
                },
            )
        )
        assert body_reads["n"] == 0
        assert counter.stats.execute_count == before.execute_count
        assert counter.stats.commit_count == before.commit_count
        assert counter.stats.rollback_count == before.rollback_count


def test_logout_session_csrf_and_bearer(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        csrf, _ = _login(client)
        _assert_origin_403(client.delete("/api/auth/session"))
        _assert_csrf_403(client.delete("/api/auth/session", headers={"Origin": SAME_ORIGIN}))
        assert client.cookies.get(SESSION_COOKIE_NAME)
        res = client.delete("/api/auth/session", headers=_mutation_headers(csrf))
        assert res.status_code == 204
        assert "no-store" in (res.headers.get("cache-control") or "").lower()

        _login(client)
        res = client.delete("/api/auth/session", headers=_bearer())
        assert res.status_code == 204


def test_expiry_and_rotation(tmp_path, monkeypatch):
    clock = FakeClock()
    with _client(
        tmp_path,
        monkeypatch,
        security=_session_security(ttl=300),
    ) as client:
        ctx = get_context()
        ctx.session_manager = BrowserSessionManager.from_config(ctx.config, clock=clock)
        csrf, body = _login(client)
        assert client.get("/api/dashboard").status_code == 200
        clock.advance(299)
        assert client.get("/api/dashboard").status_code == 200
        clock.advance(2)
        _assert_uniform_401(client.get("/api/dashboard"))


def test_api_token_rotation_invalidates(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        _login(client)
        ctx = get_context()
        rotated = ctx.config.model_copy(
            update={
                "security": SecurityConfig(
                    mode=SecurityMode.local,
                    api_token=OTHER_TOKEN,
                    session_secret=SESSION_SECRET,
                    session_ttl_seconds=ctx.config.security.session_ttl_seconds,
                )
            }
        )
        ctx.session_manager = BrowserSessionManager.from_config(rotated)
        _assert_uniform_401(client.get("/api/dashboard"))


def test_repeated_login_new_session(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        _login(client)
        first = client.cookies.get(SESSION_COOKIE_NAME)
        _login(client)
        second = client.cookies.get(SESSION_COOKIE_NAME)
        assert first and second and first != second


def test_openapi_session_security(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(tmp_path, monkeypatch, security=_session_security()) as client:
        schema = client.get("/openapi.json", headers=_bearer()).json()
        assert schema["paths"]["/api/auth/session"]["post"]["security"] == [
            {"BearerAuth": []}
        ]
        delete_sec = schema["paths"]["/api/auth/session"]["delete"]["security"]
        assert {"BearerAuth": []} in delete_sec
        assert {"BrowserSession": [], "CsrfToken": []} in delete_sec
        assert not schema["paths"]["/api/auth/session"]["get"].get("security")
        blob = str(schema)
        assert VALID_TOKEN not in blob
        assert SESSION_SECRET not in blob
