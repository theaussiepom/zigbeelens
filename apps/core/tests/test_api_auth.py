"""Bearer authentication tests (replaces legacy X-ZigbeeLens-Api-Key middleware)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from zigbeelens.api.auth import AUTH_DETAIL
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


def _bearer(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_trusted_local_open_without_api_token(mock_client: TestClient):
    assert mock_client.get("/api/dashboard").status_code == 200
    assert mock_client.post("/api/reports", json={"format": "json"}).status_code == 200
    assert mock_client.get("/healthz").status_code == 200
    assert mock_client.get("/api/version").status_code == 200


def test_bearer_required_from_yaml(tmp_path, monkeypatch):
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
        assert blocked.json()["detail"] == AUTH_DETAIL
        assert blocked.headers.get("www-authenticate") == "Bearer"

        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers=_bearer(),
            ).status_code
            == 200
        )
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
        assert client.get("/api/version").status_code == 200
        assert client.get("/healthz").status_code == 200


def test_bearer_from_canonical_env_token(tmp_path, monkeypatch):
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
                headers=_bearer(),
            ).status_code
            == 200
        )


def test_bearer_from_token_file(tmp_path, monkeypatch):
    token_file = tmp_path / "api.token"
    token_file.write_text(VALID_TOKEN + "\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(token_file))
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200


def test_legacy_env_alias_authenticates_via_bearer_header(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_API_KEY", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.post("/api/reports", json={"format": "json"}).status_code == 401
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers=_bearer(),
            ).status_code
            == 200
        )


def test_legacy_header_rejected_when_bearer_required(tmp_path, monkeypatch):
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
        res = client.get(
            "/api/dashboard",
            headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == AUTH_DETAIL


def test_effective_token_frozen_at_startup(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_auth_config(config_path)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", VALID_TOKEN)
    app = create_app(str(config_path))
    with TestClient(app) as client:
        monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", OTHER_TOKEN)
        os.environ["ZIGBEELENS_SECURITY_API_TOKEN"] = OTHER_TOKEN
        assert client.get("/api/dashboard", headers=_bearer(OTHER_TOKEN)).status_code == 401
        assert client.get("/api/dashboard", headers=_bearer(VALID_TOKEN)).status_code == 200


def test_auth_does_not_reread_environ_on_request(tmp_path, monkeypatch):
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
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
