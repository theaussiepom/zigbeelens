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
        "legacy_mutation_guard_enabled": True,
    }
    assert VALID_TOKEN not in status.model_dump_json()


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
        legacy = client.get("/api/config/status")
        v1 = client.get("/api/v1/config/status")
        assert legacy.status_code == 200
        assert v1.status_code == 200
        assert legacy.json() == v1.json()
        body = legacy.json()
        assert body["security"]["api_token_configured"] is True
        assert body["security"]["legacy_mutation_guard_enabled"] is True
        assert VALID_TOKEN not in legacy.text
        assert "token.txt" not in legacy.text


def test_startup_posture_local_loopback_no_remote_warning(caplog):
    config = AppConfig(server=ServerConfig(host="127.0.0.1"))
    with caplog.at_level(logging.INFO):
        log_security_posture(config)
    assert "non-loopback" not in caplog.text
    assert "mutation-route API-key guard" in caplog.text


def test_startup_posture_local_non_loopback_warns(caplog):
    config = AppConfig(server=ServerConfig(host="0.0.0.0"))
    with caplog.at_level(logging.WARNING):
        log_security_posture(config)
    assert "non-loopback address" in caplog.text
    assert "0.0.0.0" in caplog.text


def test_startup_posture_local_non_loopback_with_token_logs_guard(caplog):
    config = AppConfig(
        server=ServerConfig(host="0.0.0.0"),
        security=SecurityConfig(api_token=VALID_TOKEN),
    )
    with caplog.at_level(logging.INFO):
        log_security_posture(config)
    assert "api_token_configured=True" in caplog.text
    assert "mutation_guard=enabled" in caplog.text
    assert VALID_TOKEN not in caplog.text
    assert "non-loopback address" not in caplog.text


def test_startup_posture_authenticated_partial_enforcement_warning(caplog):
    config = AppConfig(
        security=SecurityConfig(mode=SecurityMode.authenticated, api_token=VALID_TOKEN)
    )
    with caplog.at_level(logging.WARNING):
        log_security_posture(config)
    assert "security.mode=authenticated" in caplog.text
    assert "legacy mutation-route API-key guard" in caplog.text
    assert VALID_TOKEN not in caplog.text


def test_startup_posture_ingress_non_enforcement_warning(caplog):
    config = AppConfig(security=SecurityConfig(mode=SecurityMode.home_assistant_ingress))
    with caplog.at_level(logging.WARNING):
        log_security_posture(config)
    assert "ingress identity enforcement is not active" in caplog.text


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
    reset_context()
