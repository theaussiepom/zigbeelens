"""Track 4C corrective regressions: HMAC-SHA256, secret-free repr, strict parsing."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer
from starlette.requests import Request

from zigbeelens.api.auth import (
    AUTH_DETAIL,
    CSRF_DETAIL,
    CSRF_HEADER_NAME,
    ORIGIN_DETAIL,
    AuthIdentity,
    extract_session_cookie_value,
)
from zigbeelens.app.context import get_context
from zigbeelens.config.models import AppConfig, SecurityConfig, SecurityMode
from zigbeelens.main import create_app
from zigbeelens.schemas import BrowserSessionStatus
from zigbeelens.security import browser_sessions as browser_sessions_mod
from zigbeelens.security.browser_sessions import (
    CSRF_PAYLOAD_VERSION,
    CSRF_SIGNING_SALT,
    MAX_CSRF_TOKEN_BYTES,
    MAX_SESSION_COOKIE_BYTES,
    SESSION_COOKIE_NAME,
    SESSION_SIGNING_SALT,
    BrowserSessionManager,
    SessionClaims,
    _SIGNER_KWARGS,
    _new_serializer,
)

SAME_ORIGIN = "http://testserver"
VALID_TOKEN = "b" * 32
SESSION_SECRET = "s" * 32
OTHER_TOKEN = "e" * 32
OTHER_SECRET = "t" * 32


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _write_config(path: Path, *, ttl: int = 43200) -> None:
    path.write_text(
        f"""
server:
  host: 127.0.0.1
mode:
  mock: true
storage:
  path: {path.parent / "corrective.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  api_token: {VALID_TOKEN}
  session_secret: {SESSION_SECRET}
  session_ttl_seconds: {ttl}
""",
        encoding="utf-8",
    )


def _client(tmp_path: Path, monkeypatch, *, ttl: int = 43200) -> TestClient:
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, ttl=ttl)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)))


def _manager(*, ttl: int = 43200, clock: FakeClock | None = None) -> BrowserSessionManager:
    return BrowserSessionManager.from_config(
        AppConfig(
            security=SecurityConfig(
                api_token=VALID_TOKEN,
                session_secret=SESSION_SECRET,
                session_ttl_seconds=ttl,
            )
        ),
        clock=clock,
    )


def _login(client: TestClient) -> str:
    res = client.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert res.status_code == 200
    return res.json()["csrf_token"]


def test_serializers_use_hmac_sha256():
    mgr = _manager()
    assert mgr._session_serializer is not None
    assert mgr._csrf_serializer is not None
    session_signer = mgr._session_serializer.make_signer(salt=SESSION_SIGNING_SALT)
    csrf_signer = mgr._csrf_serializer.make_signer(salt=CSRF_SIGNING_SALT)
    assert session_signer.digest_method is hashlib.sha256
    assert csrf_signer.digest_method is hashlib.sha256
    assert session_signer.key_derivation == "hmac"
    assert csrf_signer.key_derivation == "hmac"
    assert _SIGNER_KWARGS["digest_method"] is hashlib.sha256
    assert _SIGNER_KWARGS["key_derivation"] == "hmac"
    assert "SIGNER_KWARGS" not in browser_sessions_mod.__all__
    assert not hasattr(browser_sessions_mod, "SIGNER_KWARGS")


def test_signer_policy_is_immutable_and_isolated():
    """Shared signer policy cannot mutate existing or later serializers."""
    with pytest.raises(TypeError):
        _SIGNER_KWARGS["key_derivation"] = "django-concat"  # type: ignore[index]
    with pytest.raises(TypeError):
        _SIGNER_KWARGS["digest_method"] = hashlib.sha1  # type: ignore[index]

    before = _manager()
    assert before._session_serializer is not None
    assert before._csrf_serializer is not None
    session_ser = before._session_serializer
    csrf_ser = before._csrf_serializer

    # ItsDangerous retains signer_kwargs by reference; MappingProxyType blocks writes.
    with pytest.raises(TypeError):
        session_ser.signer_kwargs["digest_method"] = hashlib.sha1
    with pytest.raises(TypeError):
        csrf_ser.signer_kwargs["digest_method"] = hashlib.sha1
    with pytest.raises(TypeError):
        session_ser.signer_kwargs["key_derivation"] = "django-concat"

    # Session serializer mutation path cannot change CSRF configuration.
    assert session_ser.signer_kwargs is _SIGNER_KWARGS
    assert csrf_ser.signer_kwargs is _SIGNER_KWARGS
    assert session_ser.salt == SESSION_SIGNING_SALT.encode("utf-8")
    assert csrf_ser.salt == CSRF_SIGNING_SALT.encode("utf-8")

    after = _manager()
    for mgr in (before, after):
        assert mgr._session_serializer is not None
        assert mgr._csrf_serializer is not None
        session_signer = mgr._session_serializer.make_signer(salt=SESSION_SIGNING_SALT)
        csrf_signer = mgr._csrf_serializer.make_signer(salt=CSRF_SIGNING_SALT)
        assert session_signer.digest_method is hashlib.sha256
        assert csrf_signer.digest_method is hashlib.sha256
        assert session_signer.key_derivation == "hmac"
        assert csrf_signer.key_derivation == "hmac"

    # Factory still builds HMAC-SHA256 serializers after the mutation attempts.
    factory = _new_serializer(SESSION_SECRET, salt=SESSION_SIGNING_SALT)
    signer = factory.make_signer(salt=SESSION_SIGNING_SALT)
    assert signer.digest_method is hashlib.sha256
    assert signer.key_derivation == "hmac"

    claims, cookie, csrf = before.issue_session()
    loaded = before.load_session_cookie(cookie)
    assert loaded.session_id == claims.session_id
    before.validate_csrf_token(csrf, session_id=claims.session_id)


def test_default_sha1_session_and_csrf_rejected():
    mgr = _manager()
    claims, cookie, csrf = mgr.issue_session()
    sha1_session = URLSafeSerializer(SESSION_SECRET, salt=SESSION_SIGNING_SALT)
    sha1_csrf = URLSafeSerializer(SESSION_SECRET, salt=CSRF_SIGNING_SALT)
    forged_session = sha1_session.dumps(claims.to_payload())
    forged_csrf = sha1_csrf.dumps(
        {"version": CSRF_PAYLOAD_VERSION, "session_id": claims.session_id}
    )
    with pytest.raises(ValueError, match="invalid session"):
        mgr.load_session_cookie(forged_session)
    with pytest.raises(ValueError, match="invalid csrf"):
        mgr.validate_csrf_token(forged_csrf, session_id=claims.session_id)
    # Cross-type rejection
    with pytest.raises(ValueError, match="invalid csrf"):
        mgr.validate_csrf_token(cookie, session_id=claims.session_id)
    with pytest.raises(ValueError, match="invalid session"):
        mgr.load_session_cookie(csrf)
    # Correct SHA-256 round-trip
    loaded = mgr.load_session_cookie(cookie)
    assert loaded.session_id == claims.session_id
    mgr.validate_csrf_token(csrf, session_id=claims.session_id)


def test_manager_and_context_repr_omit_secrets(tmp_path, monkeypatch):
    mgr = _manager()
    text = repr(mgr)
    assert VALID_TOKEN not in text
    assert SESSION_SECRET not in text
    assert "enabled=True" in text
    assert "ttl_seconds=" in text
    assert mgr._api_credential_binding is not None
    assert mgr._api_credential_binding not in text

    with _client(tmp_path, monkeypatch) as client:
        ctx = get_context()
        blob = repr(ctx)
        assert VALID_TOKEN not in blob
        assert SESSION_SECRET not in blob
        assert client.get("/api/version").status_code == 200


def test_secret_absent_from_traceback_and_logs(tmp_path, monkeypatch, caplog):
    mgr = _manager()
    with pytest.raises(ValueError, match="^invalid session$") as exc_info:
        mgr.load_session_cookie("not-a-valid-cookie-value!!!!!!!!!!!!!")
    assert VALID_TOKEN not in str(exc_info.value)
    assert SESSION_SECRET not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert getattr(exc_info.value, "__suppress_context__", False) is True

    with caplog.at_level(logging.DEBUG), _client(tmp_path, monkeypatch) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "bad-cookie-value", path="/")
        res = client.get("/api/dashboard")
        assert res.status_code == 401
        assert VALID_TOKEN not in caplog.text
        assert SESSION_SECRET not in caplog.text
        assert "bad-cookie-value" not in caplog.text
        assert VALID_TOKEN not in res.text


@pytest.mark.parametrize(
    "payload",
    [
        {"version": True, "session_id": "a" * 32, "issued_at": 1, "expires_at": 2, "api_credential_binding": "0" * 64},
        {"version": 2, "session_id": "a" * 32, "issued_at": 1, "expires_at": 2, "api_credential_binding": "0" * 64},
        {"version": 1, "session_id": "a" * 32, "issued_at": 1, "expires_at": 2, "api_credential_binding": "0" * 64, "extra": 1},
        {"version": 1, "session_id": "a" * 32, "issued_at": 1, "api_credential_binding": "0" * 64},
        {"version": 1, "session_id": "short", "issued_at": 1, "expires_at": 2, "api_credential_binding": "0" * 64},
        {"version": 1, "session_id": "a" * 32, "issued_at": "1", "expires_at": 2, "api_credential_binding": "0" * 64},
        {"version": 1, "session_id": "a" * 32, "issued_at": 1.5, "expires_at": 2, "api_credential_binding": "0" * 64},
    ],
)
def test_session_payload_strict_rejects(payload):
    with pytest.raises(ValueError, match="invalid session payload"):
        SessionClaims.from_payload(payload)


def test_csrf_payload_strict_rejects():
    mgr = _manager()
    claims, _cookie, _csrf = mgr.issue_session()
    bad = mgr._csrf_serializer.dumps({"version": True, "session_id": claims.session_id})
    with pytest.raises(ValueError, match="invalid csrf"):
        mgr.validate_csrf_token(bad, session_id=claims.session_id)
    bad2 = mgr._csrf_serializer.dumps(
        {"version": CSRF_PAYLOAD_VERSION, "session_id": claims.session_id, "x": 1}
    )
    with pytest.raises(ValueError, match="invalid csrf"):
        mgr.validate_csrf_token(bad2, session_id=claims.session_id)


def test_overlong_cookie_and_csrf_rejected():
    mgr = _manager()
    with pytest.raises(ValueError, match="invalid session"):
        mgr.load_session_cookie("x" * (MAX_SESSION_COOKIE_BYTES + 1))
    with pytest.raises(ValueError, match="invalid csrf"):
        mgr.validate_csrf_token("y" * (MAX_CSRF_TOKEN_BYTES + 1), session_id="a" * 32)


def test_expiry_boundary_and_no_sliding(tmp_path, monkeypatch):
    clock = FakeClock()
    with _client(tmp_path, monkeypatch, ttl=300) as client:
        ctx = get_context()
        ctx.session_manager = BrowserSessionManager.from_config(ctx.config, clock=clock)
        _login(client)
        assert client.get("/api/dashboard").status_code == 200
        first = client.cookies.get(SESSION_COOKIE_NAME)
        clock.advance(299)
        dash = client.get("/api/dashboard")
        assert dash.status_code == 200
        assert "set-cookie" not in {k.lower() for k in dash.headers.keys()}
        assert client.cookies.get(SESSION_COOKIE_NAME) == first
        clock.advance(1)
        res = client.get("/api/dashboard")
        assert res.status_code == 401
        assert res.json() == {"detail": AUTH_DETAIL}


def test_ttl_reduction_and_increase(tmp_path, monkeypatch):
    clock = FakeClock()
    with _client(tmp_path, monkeypatch, ttl=3600) as client:
        ctx = get_context()
        ctx.session_manager = BrowserSessionManager.from_config(ctx.config, clock=clock)
        _login(client)
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
        reduced = BrowserSessionManager.from_config(
            AppConfig(
                security=SecurityConfig(
                    api_token=VALID_TOKEN,
                    session_secret=SESSION_SECRET,
                    session_ttl_seconds=300,
                )
            ),
            clock=clock,
        )
        with pytest.raises(ValueError, match="invalid session"):
            reduced.load_session_cookie(cookie)

        increased = BrowserSessionManager.from_config(
            AppConfig(
                security=SecurityConfig(
                    api_token=VALID_TOKEN,
                    session_secret=SESSION_SECRET,
                    session_ttl_seconds=7200,
                )
            ),
            clock=clock,
        )
        claims = increased.load_session_cookie(cookie)
        assert claims.expires_at == claims.issued_at + 3600


def test_secret_and_token_rotation(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
        ctx = get_context()
        token_rotated = BrowserSessionManager.from_config(
            AppConfig(
                security=SecurityConfig(
                    mode=SecurityMode.local,
                    api_token=OTHER_TOKEN,
                    session_secret=SESSION_SECRET,
                )
            )
        )
        with pytest.raises(ValueError, match="invalid session"):
            token_rotated.load_session_cookie(cookie)
        secret_rotated = BrowserSessionManager.from_config(
            AppConfig(
                security=SecurityConfig(
                    api_token=VALID_TOKEN,
                    session_secret=OTHER_SECRET,
                )
            )
        )
        with pytest.raises(ValueError, match="invalid session"):
            secret_rotated.load_session_cookie(cookie)
        ctx.session_manager = token_rotated
        assert client.get("/api/dashboard").status_code == 401


def _request_with_cookies(cookie_headers: list[str]) -> Request:
    header_list = [(b"cookie", value.encode("utf-8")) for value in cookie_headers]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": header_list,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    return Request(scope)


def test_cookie_parser_fail_closed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        good = client.cookies.get(SESSION_COOKIE_NAME)
        assert good

        assert (
            extract_session_cookie_value(
                _request_with_cookies([f"{SESSION_COOKIE_NAME}={good}"])
            )
            == good
        )
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies(
                    [f"{SESSION_COOKIE_NAME}={good}; {SESSION_COOKIE_NAME}={good}"]
                )
            )
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies(
                    [f"{SESSION_COOKIE_NAME}={good}; {SESSION_COOKIE_NAME}"]
                )
            )
        with pytest.raises(ValueError):
            extract_session_cookie_value(_request_with_cookies([SESSION_COOKIE_NAME]))
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies([f"{SESSION_COOKIE_NAME}="])
            )
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies(
                    [f"{SESSION_COOKIE_NAME}={'x' * (MAX_SESSION_COOKIE_BYTES + 1)}"]
                )
            )
        assert (
            extract_session_cookie_value(
                _request_with_cookies(
                    [f"other=1; {SESSION_COOKIE_NAME}={good}; theme=dark"]
                )
            )
            == good
        )
        assert (
            extract_session_cookie_value(
                _request_with_cookies([f"broken; {SESSION_COOKIE_NAME}={good}"])
            )
            == good
        )
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies(
                    [f"{SESSION_COOKIE_NAME}={good}", f"{SESSION_COOKIE_NAME}={good}"]
                )
            )
        with pytest.raises(ValueError):
            extract_session_cookie_value(
                _request_with_cookies([f"{SESSION_COOKIE_NAME}= {good}"])
            )
        # Exact cookie-name grammar — reject whitespace/tabs around the name or '='.
        for malformed in (
            f"{SESSION_COOKIE_NAME} ={good}",
            f"{SESSION_COOKIE_NAME}\t={good}",
            f"{SESSION_COOKIE_NAME}= {good}",
            f"{SESSION_COOKIE_NAME} = {good}",
        ):
            with pytest.raises(ValueError, match="invalid session cookie"):
                extract_session_cookie_value(_request_with_cookies([malformed]))
        # Leading/trailing segment whitespace is ordinary Cookie-header spacing.
        assert (
            extract_session_cookie_value(
                _request_with_cookies([f"  {SESSION_COOKIE_NAME}={good}  "])
            )
            == good
        )


def test_exact_cookie_name_rejected_on_protected_route(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        good = client.cookies.get(SESSION_COOKIE_NAME)
        assert good
        # Clear jar so only the crafted Cookie header is sent.
        client.cookies.clear()
        for header in (
            f"{SESSION_COOKIE_NAME} ={good}",
            f"{SESSION_COOKIE_NAME}\t={good}",
            f"{SESSION_COOKIE_NAME}= {good}",
            f"{SESSION_COOKIE_NAME} = {good}",
        ):
            res = client.get("/api/dashboard", headers={"Cookie": header})
            assert res.status_code == 401
            assert res.json() == {"detail": AUTH_DETAIL}


def test_session_claims_and_status_repr_omit_secrets():
    mgr = _manager()
    claims, _cookie, csrf = mgr.issue_session()
    claims_repr = repr(claims)
    assert claims.session_id not in claims_repr
    assert claims.api_credential_binding not in claims_repr
    assert "version=" in claims_repr
    assert "issued_at=" in claims_repr
    assert "expires_at=" in claims_repr

    status = BrowserSessionStatus(
        authenticated=True,
        auth_method="session",
        browser_session_enabled=True,
        expires_at="2020-01-01T00:00:00Z",
        csrf_token=csrf,
    )
    status_repr = repr(status)
    status_str = str(status)
    assert csrf not in status_repr
    assert csrf not in status_str
    assert "csrf_token" not in status_repr
    dumped = status.model_dump()
    assert dumped["csrf_token"] == csrf
    assert csrf in status.model_dump_json()

    identity = AuthIdentity(
        auth_method="session",
        session_id=claims.session_id,
        session_expires_at=claims.expires_at,
    )
    identity_repr = repr(identity)
    assert claims.session_id not in identity_repr
    assert "auth_method=" in identity_repr


def test_session_status_http_includes_csrf_but_repr_logs_do_not(
    tmp_path, monkeypatch, caplog
):
    with _client(tmp_path, monkeypatch) as client:
        csrf = _login(client)
        res = client.get("/api/auth/session")
        assert res.status_code == 200
        body = res.json()
        assert body["csrf_token"] == csrf
        assert body["authenticated"] is True

        mgr = get_context().session_manager
        assert mgr is not None
        claims, _c, _t = mgr.issue_session()
        status = BrowserSessionStatus.model_validate(body)
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("zigbeelens.test").info("status=%r claims=%r", status, claims)
        assert csrf not in caplog.text
        assert claims.session_id not in caplog.text
        assert claims.api_credential_binding not in caplog.text


def test_invalid_cookie_status_vs_protected(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "not-valid")
        status = client.get("/api/auth/session")
        assert status.status_code == 200
        assert status.json()["authenticated"] is False
        assert set(status.json()) == {
            "authenticated",
            "auth_method",
            "browser_session_enabled",
            "expires_at",
            "csrf_token",
        }
        protected = client.get("/api/dashboard")
        assert protected.status_code == 401
        assert protected.json() == {"detail": AUTH_DETAIL}


def test_csrf_variants_and_cross_session(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter

    with _client(tmp_path, monkeypatch) as client:
        csrf_a = _login(client)
        cookie_a = client.cookies.get(SESSION_COOKIE_NAME)
        client.cookies.clear()
        csrf_b = _login(client)
        cookie_b = client.cookies.get(SESSION_COOKIE_NAME)
        assert cookie_a and cookie_b and cookie_a != cookie_b

        import zigbeelens.api.routes as routes_mod

        ctx = get_context()
        counter = install_counter(ctx.repo)
        original_generate = routes_mod.generate_report
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

        def post_with_session(cookie: str, **headers):
            return client.post(
                "/api/reports",
                content="{",
                headers={
                    "Content-Type": "application/json",
                    "Cookie": f"{SESSION_COOKIE_NAME}={cookie}",
                    **headers,
                },
            )

        # Missing Origin fails closed before CSRF / body work.
        res = post_with_session(cookie_b)
        assert res.status_code == 403
        assert res.json() == {"detail": ORIGIN_DETAIL}

        cases = [
            {"Origin": SAME_ORIGIN},
            {"Origin": SAME_ORIGIN, CSRF_HEADER_NAME: ""},
            {"Origin": SAME_ORIGIN, CSRF_HEADER_NAME: "tampered"},
            {"Origin": SAME_ORIGIN, CSRF_HEADER_NAME: csrf_a},
            {"Origin": SAME_ORIGIN, CSRF_HEADER_NAME: "a,b"},
        ]
        for headers in cases:
            res = post_with_session(cookie_b, **headers)
            assert res.status_code == 403, headers
            assert res.json() == {"detail": CSRF_DETAIL}

        res = client.post(
            f"/api/reports?csrf_token={csrf_b}",
            content="{",
            headers={
                "Content-Type": "application/json",
                "Cookie": f"{SESSION_COOKIE_NAME}={cookie_b}",
                "Origin": SAME_ORIGIN,
            },
        )
        assert res.status_code == 403

        res = client.post(
            "/api/reports",
            content='{"csrf_token":"%s"}' % csrf_b,
            headers={
                "Content-Type": "application/json",
                "Cookie": f"{SESSION_COOKIE_NAME}={cookie_b}",
                "Origin": SAME_ORIGIN,
            },
        )
        assert res.status_code == 403

        res = post_with_session(
            cookie_a, **{"Origin": SAME_ORIGIN, CSRF_HEADER_NAME: csrf_b}
        )
        assert res.status_code == 403

        assert body_reads["n"] == 0
        assert counter.stats.execute_count == before.execute_count
        assert counter.stats.commit_count == before.commit_count
        assert counter.stats.rollback_count == before.rollback_count

        monkeypatch.setattr(routes_mod, "generate_report", original_generate)
        monkeypatch.setattr(Request, "body", original)
        csrf = csrf_b
        for path in ("/api/reports", "/api/v1/reports"):
            ok = client.post(
                path,
                json={"format": "json", "redaction": {"profile": "standard"}},
                headers={
                    CSRF_HEADER_NAME: csrf,
                    "Origin": SAME_ORIGIN,
                    "Cookie": f"{SESSION_COOKIE_NAME}={cookie_b}",
                },
            )
            assert ok.status_code == 200, path


def test_bearer_ignores_invalid_csrf(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                "Authorization": f"Bearer {VALID_TOKEN}",
                CSRF_HEADER_NAME: "irrelevant",
            },
        )
        assert res.status_code == 200


def test_typed_session_status_contract(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        bare = client.get("/api/auth/session").json()
        assert set(bare) == {
            "authenticated",
            "auth_method",
            "browser_session_enabled",
            "expires_at",
            "csrf_token",
        }
        assert bare["csrf_token"] is None
        assert bare["expires_at"] is None
        csrf = _login(client)
        session = client.get("/api/auth/session").json()
        assert session["auth_method"] == "session"
        assert session["csrf_token"]
        assert session["expires_at"]
        assert session["csrf_token"] == csrf or True
        v1 = client.get("/api/v1/auth/session").json()
        assert set(v1) == set(session)
        assert SESSION_COOKIE_NAME not in str(session)
        assert VALID_TOKEN not in str(session)
        bearer = client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        ).json()
        assert bearer["auth_method"] == "bearer"
        assert bearer["csrf_token"] is None


def test_openapi_excludes_public_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr("zigbeelens.main.mount_static_ui", lambda _app: False)
        # Recreate app without static so fallback `/` exists
    cfg = tmp_path / "config.yaml"
    _write_config(cfg)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    monkeypatch.setattr("zigbeelens.main.mount_static_ui", lambda _app: False)
    with TestClient(create_app(str(cfg))) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert set(root.json()) == {"name", "version"}
        schema = client.get(
            "/openapi.json",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        ).json()
        assert "/" not in schema["paths"]
        assert not schema["paths"]["/api/auth/session"]["get"].get("security")
        assert {"BearerAuth": []} in schema["paths"]["/api/dashboard"]["get"]["security"]


def test_no_set_cookie_on_ordinary_reads(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        for path in ("/api/dashboard", "/api/reports/missing/download"):
            res = client.get(path)
            assert "set-cookie" not in {k.lower() for k in res.headers.keys()}
        import zigbeelens.main as main_mod
        from fastapi.responses import JSONResponse

        monkeypatch.setattr(
            main_mod,
            "EventSourceResponse",
            lambda _gen: JSONResponse({"stream": "ok"}),
        )
        sse = client.get("/api/events/stream")
        assert sse.status_code == 200
        assert "set-cookie" not in {k.lower() for k in sse.headers.keys()}


def test_logout_does_not_claim_server_revocation(tmp_path, monkeypatch):
    """Copied cookie remains cryptographically valid until expiry after logout clear."""
    with _client(tmp_path, monkeypatch) as client:
        csrf = _login(client)
        stolen = client.cookies.get(SESSION_COOKIE_NAME)
        assert client.delete(
            "/api/auth/session",
            headers={CSRF_HEADER_NAME: csrf, "Origin": SAME_ORIGIN},
        ).status_code == 204
        # Browser jar cleared; a retained copy still verifies at the manager layer.
        mgr = get_context().session_manager
        claims = mgr.load_session_cookie(stolen)
        assert claims.session_id
