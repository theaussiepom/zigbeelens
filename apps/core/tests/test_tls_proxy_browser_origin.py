"""Browser-visible Origin behind TLS-terminating reverse proxies."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.api.auth import CSRF_HEADER_NAME, ORIGIN_DETAIL
from zigbeelens.main import create_app

VALID_TOKEN = "b" * 32
SESSION_SECRET = "s" * 32
BROWSER_ORIGIN = "https://zigbeelens.example"
ASGI_BASE = "http://zigbeelens.example"


def _client(tmp_path: Path, monkeypatch, *, cors: str) -> TestClient:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
server:
  host: 127.0.0.1
mode:
  mock: true
storage:
  path: {tmp_path / "proxy-origin.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  api_token: {VALID_TOKEN}
  session_secret: {SESSION_SECRET}
  cors_allowed_origins: {cors}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)), base_url=ASGI_BASE)


def test_browser_https_origin_requires_cors_allowlist(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors="[]") as client:
        login = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                CSRF_HEADER_NAME: csrf,
                "Origin": BROWSER_ORIGIN,
                "X-Forwarded-Proto": "https",
            },
        )
        assert res.status_code == 403
        assert res.json() == {"detail": ORIGIN_DETAIL}


def test_browser_https_origin_succeeds_when_allowlisted(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors=f'["{BROWSER_ORIGIN}"]') as client:
        login = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        res = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                CSRF_HEADER_NAME: csrf,
                "Origin": BROWSER_ORIGIN,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "203.0.113.9",
            },
        )
        assert res.status_code == 200, res.text

        # ASGI same-origin (http) still works; X-Forwarded-Proto is ignored.
        same = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers={
                CSRF_HEADER_NAME: csrf,
                "Origin": "http://zigbeelens.example",
                "X-Forwarded-Proto": "https",
            },
        )
        assert same.status_code == 200


def test_wrong_scheme_host_port_still_fail(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, cors=f'["{BROWSER_ORIGIN}"]') as client:
        login = client.post(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        csrf = login.json()["csrf_token"]
        for origin in (
            "https://zigbeelens.example:8443",
            "https://other.example",
            "http://other.example",
        ):
            res = client.post(
                "/api/reports",
                json={"format": "json", "redaction": {"profile": "standard"}},
                headers={CSRF_HEADER_NAME: csrf, "Origin": origin},
            )
            assert res.status_code == 403, origin
            assert res.json() == {"detail": ORIGIN_DETAIL}
