"""Security status, posture logging, and config/status parity."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.app.context import bootstrap, reset_context
from zigbeelens.config.models import AppConfig, SecurityConfig, SecurityMode, ServerConfig
from zigbeelens.config.security_status import build_security_config_status, log_security_posture
from zigbeelens.main import create_app

VALID_TOKEN = "g" * 32


def _write_config(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _bearer(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_security_status_booleans_only():
    config = AppConfig(
        server=ServerConfig(host="0.0.0.0"),
        security=SecurityConfig(
            mode=SecurityMode.local,
            api_token=VALID_TOKEN,
            session_secret="h" * 32,
        ),
    )
    status = build_security_config_status(config)
    dumped = status.model_dump(mode="json")
    assert dumped == {
        "mode": "local",
        "loopback_bind": False,
        "api_token_configured": True,
        "session_secret_configured": True,
        "bearer_auth_enabled": True,
        "browser_session_enabled": True,
        "csrf_protection_enabled": True,
        "session_cookie_secure": True,
        "read_routes_require_authentication": True,
        "mutation_routes_require_authentication": True,
        "read_routes_require_bearer": False,
        "mutation_routes_require_bearer": False,
        "ingress_identity_enforced": False,
        "trusted_local_open": False,
        "legacy_mutation_guard_enabled": False,
        "cors_allowed_origins_count": 0,
        "credentialed_cors_enabled": False,
        "frame_ancestor_origins_count": 0,
        "external_framing_enabled": False,
        "content_security_policy_enabled": True,
        "session_origin_validation_enabled": True,
    }
    assert VALID_TOKEN not in status.model_dump_json()
    assert "h" * 32 not in status.model_dump_json()


def test_security_status_trusted_local_open():
    status = build_security_config_status(AppConfig())
    assert status.trusted_local_open is True
    assert status.bearer_auth_enabled is False
    assert status.read_routes_require_bearer is False
    assert status.mutation_routes_require_bearer is False
    assert status.legacy_mutation_guard_enabled is False


def test_config_status_api_and_v1_parity(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "status.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  api_token: {VALID_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    app = create_app(str(config_path))
    with TestClient(app) as client:
        assert client.get("/api/config/status").status_code == 401
        legacy = client.get("/api/config/status", headers=_bearer())
        v1 = client.get("/api/v1/config/status", headers=_bearer())
        assert legacy.status_code == 200
        assert v1.status_code == 200
        assert legacy.json() == v1.json()
        body = legacy.json()
        assert body["security"]["api_token_configured"] is True
        assert body["security"]["bearer_auth_enabled"] is True
        assert body["security"]["trusted_local_open"] is False
        assert body["security"]["legacy_mutation_guard_enabled"] is False
        assert VALID_TOKEN not in legacy.text
        assert "token.txt" not in legacy.text


def test_startup_posture_local_loopback_trusted_open(caplog):
    config = AppConfig(server=ServerConfig(host="127.0.0.1"))
    with caplog.at_level(logging.INFO):
        log_security_posture(config)
    assert "non-loopback" not in caplog.text
    assert "trusted-open" in caplog.text


def test_startup_posture_local_non_loopback_warns(caplog):
    config = AppConfig(server=ServerConfig(host="0.0.0.0"))
    with caplog.at_level(logging.WARNING):
        log_security_posture(config)
    assert "non-loopback address" in caplog.text
    assert "0.0.0.0" in caplog.text
    assert "All API routes are open" in caplog.text


def test_startup_posture_local_with_token_logs_bearer(caplog):
    config = AppConfig(
        server=ServerConfig(host="0.0.0.0"),
        security=SecurityConfig(api_token=VALID_TOKEN),
    )
    with caplog.at_level(logging.INFO):
        log_security_posture(config)
    assert "api_token_configured=True" in caplog.text
    assert "bearer_auth_enabled=True" in caplog.text
    assert "Bearer authentication is enabled" in caplog.text
    assert VALID_TOKEN not in caplog.text
    assert "non-loopback address" not in caplog.text


def test_startup_posture_authenticated_bearer_enforced(caplog):
    config = AppConfig(
        security=SecurityConfig(mode=SecurityMode.authenticated, api_token=VALID_TOKEN)
    )
    with caplog.at_level(logging.INFO):
        log_security_posture(config)
    assert "security.mode=authenticated" in caplog.text
    assert "require Authorization: Bearer" in caplog.text
    assert "legacy mutation-route" not in caplog.text
    assert VALID_TOKEN not in caplog.text


def test_startup_posture_ingress_bearer_fallback_warning(caplog):
    config = AppConfig(
        security=SecurityConfig(
            mode=SecurityMode.home_assistant_ingress,
            api_token=VALID_TOKEN,
        )
    )
    with caplog.at_level(logging.WARNING):
        log_security_posture(config)
    assert "temporary bearer/session" in caplog.text
    assert "ingress identity validation is not" in caplog.text


def test_bootstrap_logs_posture_without_secrets(tmp_path, monkeypatch, caplog):
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        f"""
server:
  host: 0.0.0.0
mode:
  mock: true
storage:
  path: {tmp_path / "boot.sqlite"}
networks: []
security:
  api_token: {VALID_TOKEN}
""",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    reset_context()
    with caplog.at_level(logging.INFO):
        bootstrap(config_path=str(config_path))
    assert VALID_TOKEN not in caplog.text
    assert "api_token_configured=True" in caplog.text
    assert "bearer_auth_enabled=True" in caplog.text
    reset_context()
