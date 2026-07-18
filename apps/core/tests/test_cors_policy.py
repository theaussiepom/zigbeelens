"""Exact credentialed CORS policy regressions."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.api.auth import AUTH_DETAIL, CSRF_DETAIL, CSRF_HEADER_NAME
from zigbeelens.app.context import get_context
from zigbeelens.main import create_app
from zigbeelens.security.headers import GENERAL_HEADERS

VALID_TOKEN = "b" * 32
SESSION_SECRET = "s" * 32
ALLOWED = "https://ui.example"
SAME = "http://testserver"


def _write(path: Path, *, cors: str = "[]", frames: str = "[]", sessions: bool = False) -> None:
    security = f"""
security:
  cors_allowed_origins: {cors}
  frame_ancestor_origins: {frames}
"""
    if sessions:
        security += f"""
  api_token: {VALID_TOKEN}
  session_secret: {SESSION_SECRET}
"""
    path.write_text(
        f"""
server:
  host: 127.0.0.1
mode:
  mock: true
storage:
  path: {path.parent / "cors.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{security}
""",
        encoding="utf-8",
    )


def _client(tmp_path: Path, monkeypatch, **kwargs) -> TestClient:
    cfg = tmp_path / "config.yaml"
    _write(cfg, **kwargs)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)))


def test_empty_allowlist_no_wildcard(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        pre = client.options(
            "/api/dashboard",
            headers={
                "Origin": ALLOWED,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert pre.headers.get("access-control-allow-origin") is None
        assert "*" not in (pre.headers.get("access-control-allow-origin") or "")
        assert pre.headers.get("access-control-allow-credentials") is None
        # Same-origin / direct clients unchanged.
        assert client.get("/api/version").status_code == 200
        assert client.get("/healthz").status_code == 200


def test_allowed_origin_preflight_and_credentials(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors=f'["{ALLOWED}"]', sessions=True) as client:
        pre = client.options(
            "/api/reports",
            headers={
                "Origin": ALLOWED,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,content-type,x-zigbeelens-csrf-token,last-event-id,accept"
                ),
            },
        )
        assert pre.status_code in {200, 204}
        assert pre.headers.get("access-control-allow-origin") == ALLOWED
        assert pre.headers.get("access-control-allow-credentials") == "true"
        assert "origin" in (pre.headers.get("vary") or "").lower()
        for key, value in GENERAL_HEADERS.items():
            assert pre.headers.get(key.lower()) == value
        assert pre.headers.get("content-security-policy") is None
        assert pre.headers.get("x-frame-options") is None
        assert pre.headers.get("strict-transport-security") is None
        methods = (pre.headers.get("access-control-allow-methods") or "").upper()
        for m in ("GET", "HEAD", "OPTIONS", "POST", "DELETE"):
            assert m in methods
        assert "*" not in methods
        allow_headers = (pre.headers.get("access-control-allow-headers") or "").lower()
        assert "authorization" in allow_headers
        assert "x-zigbeelens-csrf-token" in allow_headers
        assert "*" not in allow_headers

        login = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}", "Origin": ALLOWED},
        )
        assert login.status_code == 200
        assert login.headers.get("access-control-allow-origin") == ALLOWED
        csrf = login.json()["csrf_token"]

        created = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                "Origin": ALLOWED,
                CSRF_HEADER_NAME: csrf,
            },
        )
        assert created.status_code == 200
        assert created.headers.get("access-control-allow-origin") == ALLOWED
        report_id = created.json()["id"]
        dl = client.get(
            f"/api/reports/{report_id}/download",
            headers={"Origin": ALLOWED},
        )
        assert dl.status_code == 200
        expose = (dl.headers.get("access-control-expose-headers") or "").lower()
        assert "content-disposition" in expose


def test_disallowed_origin_no_allow_header_zero_work(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter

    with _client(tmp_path, monkeypatch, cors=f'["{ALLOWED}"]', sessions=True) as client:
        ctx = get_context()
        counter = install_counter(ctx.repo)
        before = counter.stats.copy()
        bad = "https://evil.example"
        pre = client.options(
            "/api/dashboard",
            headers={
                "Origin": bad,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert pre.headers.get("access-control-allow-origin") is None
        assert pre.headers.get("access-control-allow-credentials") is None
        for key, value in GENERAL_HEADERS.items():
            assert pre.headers.get(key.lower()) == value
        assert counter.stats.execute_count == before.execute_count

        # Near-match denials
        for origin in (
            "http://ui.example",
            "https://ui.example:8443",
            "https://sub.ui.example",
            "https://ui.example.",
            "null",
            "https://user:pass@ui.example",
        ):
            res = client.get("/api/dashboard", headers={"Origin": origin})
            assert res.headers.get("access-control-allow-origin") is None
            assert res.headers.get("access-control-allow-credentials") is None


def test_cors_on_401_and_403_for_allowed_origin(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors=f'["{ALLOWED}"]', sessions=True) as client:
        unauth = client.get("/api/dashboard", headers={"Origin": ALLOWED})
        assert unauth.status_code == 401
        assert unauth.json() == {"detail": AUTH_DETAIL}
        assert unauth.headers.get("access-control-allow-origin") == ALLOWED

        login = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        # Wrong origin → 403 with no CORS allow for disallowed origin
        wrong = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                "Origin": "https://evil.example",
                CSRF_HEADER_NAME: csrf,
            },
        )
        assert wrong.status_code == 403
        assert wrong.headers.get("access-control-allow-origin") is None

        # Allowed origin + missing CSRF → 403 still carries CORS
        missing_csrf = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={"Origin": ALLOWED},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json() == {"detail": CSRF_DETAIL}
        assert missing_csrf.headers.get("access-control-allow-origin") == ALLOWED


def test_api_v1_cors_parity(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors=f'["{ALLOWED}"]') as client:
        for path in ("/api/version", "/api/v1/version"):
            res = client.get(path, headers={"Origin": ALLOWED})
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == ALLOWED
