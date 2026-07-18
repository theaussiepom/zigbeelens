"""Pre-body browser Origin validation for session-authenticated mutations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from starlette.requests import Request

from zigbeelens.api.auth import CSRF_DETAIL, CSRF_HEADER_NAME, ORIGIN_DETAIL
from zigbeelens.app.context import get_context
from zigbeelens.main import create_app

VALID_TOKEN = "b" * 32
SESSION_SECRET = "s" * 32
SAME = "http://testserver"
CORS_ORIGIN = "https://ui.example"
FRAME_ONLY = "https://ha.example"


def _client(tmp_path: Path, monkeypatch, *, cors=None, frames=None) -> TestClient:
    cors_yaml = f'["{CORS_ORIGIN}"]' if cors is None else cors
    frames_yaml = f'["{FRAME_ONLY}"]' if frames is None else frames
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
server:
  host: 127.0.0.1
mode:
  mock: true
storage:
  path: {tmp_path / "origin.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  api_token: {VALID_TOKEN}
  session_secret: {SESSION_SECRET}
  cors_allowed_origins: {cors_yaml}
  frame_ancestor_origins: {frames_yaml}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)))


def _login(client: TestClient) -> str:
    res = client.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert res.status_code == 200
    return res.json()["csrf_token"]


def _assert_origin_403(res) -> None:
    assert res.status_code == 403
    assert res.json() == {"detail": ORIGIN_DETAIL}
    assert "no-store" in (res.headers.get("cache-control") or "").lower()
    assert res.headers.get("www-authenticate") is None


def test_same_origin_and_cors_origin_succeed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        csrf = _login(client)
        for origin in (SAME, CORS_ORIGIN):
            res = client.post(
                "/api/reports",
                json={"format": "json", "redaction": {"profile": "standard"}},
                headers={CSRF_HEADER_NAME: csrf, "Origin": origin},
            )
            assert res.status_code == 200, origin


def test_malformed_host_rejects_before_csrf_and_body(tmp_path, monkeypatch):
    import zigbeelens.api.routes as routes_mod
    from performance.query_instrumentation import install_counter
    from starlette.requests import Request as StarletteRequest

    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        ctx = get_context()
        counter = install_counter(ctx.repo)
        monkeypatch.setattr(
            routes_mod,
            "generate_report",
            MagicMock(side_effect=AssertionError("create")),
        )
        body_reads = {"n": 0}
        original = StarletteRequest.body

        async def counting_body(self):
            body_reads["n"] += 1
            return await original(self)

        monkeypatch.setattr(StarletteRequest, "body", counting_body)
        before = counter.stats.copy()
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                CSRF_HEADER_NAME: "definitely-wrong-csrf",
                "Origin": SAME,
                "Host": "example.com:notaport",
            },
        )
        _assert_origin_403(res)
        assert res.json()["detail"] != CSRF_DETAIL
        assert body_reads["n"] == 0
        assert counter.stats.execute_count == before.execute_count


def test_origin_rejection_matrix_zero_work(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter
    import zigbeelens.api.routes as routes_mod

    with _client(tmp_path, monkeypatch) as client:
        csrf = _login(client)
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

        bad_origins = [
            None,
            "null",
            "https://evil.example",
            FRAME_ONLY,
            "http://ui.example",
            "https://ui.example:8443",
            "https://user:pass@ui.example",
            "https://ui.example/path",
        ]
        for origin in bad_origins:
            headers = {CSRF_HEADER_NAME: csrf}
            if origin is not None:
                headers["Origin"] = origin
            res = client.post(
                "/api/reports",
                content="{",
                headers={"Content-Type": "application/json", **headers},
            )
            _assert_origin_403(res)

        # Duplicate Origin headers — unit-style Request with getlist > 1.
        from zigbeelens.api.auth import AuthIdentity, enforce_session_mutation_origin
        from starlette.requests import Request as StarletteRequest

        req = StarletteRequest(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/reports",
                "raw_path": b"/api/reports",
                "query_string": b"",
                "headers": [
                    (b"origin", b"http://a.example"),
                    (b"origin", b"http://b.example"),
                ],
                "client": ("127.0.0.1", 1),
                "server": ("testserver", 80),
            }
        )
        try:
            enforce_session_mutation_origin(req, AuthIdentity("session", session_id="a" * 32))
            raise AssertionError("expected origin failure")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 403
            assert exc.detail == ORIGIN_DETAIL

        assert body_reads["n"] == 0
        assert counter.stats.execute_count == before.execute_count
        assert counter.stats.commit_count == before.commit_count
        assert counter.stats.rollback_count == before.rollback_count


def test_valid_origin_invalid_csrf(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _login(client)
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={"Origin": SAME, CSRF_HEADER_NAME: "bad"},
        )
        assert res.status_code == 403
        assert res.json() == {"detail": CSRF_DETAIL}


def test_bearer_and_trusted_local_bypass_origin(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert res.status_code == 200

    cfg = tmp_path / "open.yaml"
    cfg.write_text(
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "open.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    with TestClient(create_app(str(cfg))) as open_client:
        res = open_client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
        )
        assert res.status_code == 200


def test_session_bootstrap_origin_policy(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        # No Origin: curl/API bootstrap permitted
        ok = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert ok.status_code == 200
        # Allowed / same origin permitted
        for origin in (SAME, CORS_ORIGIN):
            res = client.post(
                "/api/auth/session",
                headers={
                    "Authorization": f"Bearer {VALID_TOKEN}",
                    "Origin": origin,
                },
            )
            assert res.status_code == 200, origin
        # Disallowed origin rejected
        bad = client.post(
            "/api/auth/session",
            headers={
                "Authorization": f"Bearer {VALID_TOKEN}",
                "Origin": "https://evil.example",
            },
        )
        _assert_origin_403(bad)
