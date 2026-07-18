"""Optional API key middleware tests."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from zigbeelens.main import create_app

VALID_TOKEN = "c" * 32
OTHER_TOKEN = "d" * 32


def _write_auth_config(path, *, extra: str = "") -> None:
    path.write_text(
        f"""
mode:
  mock: true
storage:
  path: {path.parent / "auth.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{extra}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_mutating_routes_open_without_api_key(mock_client: TestClient):
    res = mock_client.post("/api/reports", json={"format": "json"})
    assert res.status_code == 200


def test_mutating_routes_require_api_key_from_yaml(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(
        config_path,
        extra=f"""
security:
  api_token: {VALID_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    app = create_app(str(config_path))
    with TestClient(app) as client:
        blocked = client.post("/api/reports", json={"format": "json"})
        assert blocked.status_code == 401

        ok = client.post(
            "/api/reports",
            json={"format": "json"},
            headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
        )
        assert ok.status_code == 200

        get_ok = client.get("/api/dashboard")
        assert get_ok.status_code == 200


def test_mutating_routes_require_canonical_env_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.post("/api/reports", json={"format": "json"}).status_code == 401
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 200
        )


def test_mutating_routes_require_token_file(tmp_path, monkeypatch):
    token_file = tmp_path / "api.token"
    token_file.write_text(VALID_TOKEN + "\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(token_file))
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.post("/api/reports", json={"format": "json"}).status_code == 401
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 200
        )


def test_mutating_routes_require_legacy_alias(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_API_KEY", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.post("/api/reports", json={"format": "json"}).status_code == 401
        wrong = client.post(
            "/api/reports",
            json={"format": "json"},
            headers={"X-ZigbeeLens-Api-Key": OTHER_TOKEN},
        )
        assert wrong.status_code == 401
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 200
        )


def test_read_routes_and_sse_remain_open_with_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 200
        assert client.get("/api/config/status").status_code == 200
        paths = {route.path for route in client.app.routes if hasattr(route, "path")}
        assert "/api/events/stream" in paths


def test_effective_token_frozen_at_startup(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", OTHER_TOKEN)
        os.environ["ZIGBEELENS_SECURITY_API_TOKEN"] = OTHER_TOKEN
        # Startup token still required; rotated env value is ignored.
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": OTHER_TOKEN},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 200
        )


def test_middleware_does_not_reread_environ_on_request(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    app = create_app(str(config_path))

    original_getenv = os.environ.get
    watched = {"ZIGBEELENS_API_KEY", "ZIGBEELENS_SECURITY_API_TOKEN"}

    def guarded_getenv(key, default=None):
        if key in watched:
            raise AssertionError(f"request path must not read {key}")
        return original_getenv(key, default)

    with TestClient(app) as client:
        monkeypatch.setattr(os.environ, "get", guarded_getenv)
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 200
        )
