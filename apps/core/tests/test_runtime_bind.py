"""First-party launcher bind authority: AppConfig owns Uvicorn host/port."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context, reset_context
from zigbeelens.config import ConfigError, is_loopback_bind, load_config, load_effective_config
from zigbeelens.config.addon import options_to_app_config
from zigbeelens.config.security_status import build_security_config_status
from zigbeelens.main import create_app, run_server

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_config(path: Path, *, host: str = "127.0.0.1", port: int = 8377) -> None:
    path.write_text(
        f"""
server:
  host: "{host}"
  port: {port}
mode:
  mock: true
storage:
  path: {path.parent / "bind.sqlite"}
networks: []
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_run_server_default_source_config_binds_loopback(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg)
    monkeypatch.delenv("ZIGBEELENS_PORT", raising=False)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    with patch("uvicorn.run", side_effect=fake_run):
        run_server(cfg, reload=False)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8377
    assert captured["reload"] is False


@pytest.mark.parametrize("host", ["0.0.0.0", "::"])
def test_run_server_passes_explicit_hosts(tmp_path: Path, monkeypatch, host: str):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, host=host)
    monkeypatch.delenv("ZIGBEELENS_PORT", raising=False)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    captured: dict = {}

    with patch("uvicorn.run", side_effect=lambda app, **kwargs: captured.update(kwargs)):
        run_server(cfg, reload=False)

    assert captured["host"] == host
    assert captured["reload"] is False


def test_run_server_passes_configured_port(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, port=9123)
    monkeypatch.delenv("ZIGBEELENS_PORT", raising=False)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    captured: dict = {}

    with patch("uvicorn.run", side_effect=lambda app, **kwargs: captured.update(kwargs)):
        run_server(cfg, reload=False)

    assert captured["port"] == 9123


def test_port_env_override_applies_to_config_and_uvicorn(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, port=8377)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg_path))
    monkeypatch.setenv("ZIGBEELENS_PORT", "9456")
    effective = load_effective_config(cfg_path)
    assert effective.server.port == 9456
    assert effective.server.host == "127.0.0.1"

    captured: dict = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    with patch("uvicorn.run", side_effect=fake_run):
        run_server(cfg_path, reload=False)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9456


def test_invalid_port_env_fails_safely(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path)
    monkeypatch.setenv("ZIGBEELENS_PORT", "not-a-port")
    with pytest.raises(ConfigError, match="ZIGBEELENS_PORT"):
        load_effective_config(cfg_path)


def test_preloaded_config_is_same_instance_in_app_context(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, host="0.0.0.0", port=8377)
    monkeypatch.delenv("ZIGBEELENS_PORT", raising=False)
    effective = load_effective_config(cfg_path)
    app = create_app(config_path=str(cfg_path), resolved_config=effective)
    reset_context()
    with TestClient(app) as client:
        assert client.get("/api/config/status").status_code == 200
        ctx = get_context()
        assert ctx.config is effective
        status = build_security_config_status(ctx.config)
        assert status.loopback_bind is False
        assert ctx.config.server.host == "0.0.0.0"
    reset_context()


def test_production_reload_disabled(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg)
    monkeypatch.delenv("ZIGBEELENS_PORT", raising=False)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    captured: dict = {}
    with patch("uvicorn.run", side_effect=lambda app, **kwargs: captured.update(kwargs)):
        run_server(cfg, reload=False)
    assert captured["reload"] is False


def test_docker_and_addon_configs_bind_non_loopback():
    docker = load_config(REPO_ROOT / "deploy" / "docker" / "config.example.yaml")
    assert docker.server.host == "0.0.0.0"
    assert is_loopback_bind(docker.server.host) is False

    docker_dev = load_config(REPO_ROOT / "deploy" / "compose" / "config.dev.yaml")
    assert docker_dev.server.host == "0.0.0.0"
    assert build_security_config_status(docker_dev).loopback_bind is False

    addon = options_to_app_config(
        {
            "mqtt": {"host": "core-mosquitto", "port": 1883},
            "networks": [{"id": "home", "name": "Home", "base_topic": "zigbee2mqtt"}],
        }
    )
    assert addon.server.host == "0.0.0.0"


def test_source_development_binds_loopback():
    source = load_config(REPO_ROOT / "config" / "config.yaml")
    example = load_config(REPO_ROOT / "examples" / "config.example.yaml")
    assert source.server.host == "127.0.0.1"
    assert example.server.host == "127.0.0.1"
    assert build_security_config_status(source).loopback_bind is True


def test_first_party_shell_scripts_do_not_force_host_override():
    scripts = [
        REPO_ROOT / "deploy" / "docker" / "entrypoint.sh",
        REPO_ROOT / "apps" / "addon" / "zigbeelens" / "run.sh",
        REPO_ROOT / "scripts" / "dev.sh",
        REPO_ROOT / "apps" / "core" / "package.json",
    ]
    host_flag = re.compile(r"--host\s+0\.0\.0\.0")
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert not host_flag.search(text), path
        assert "uvicorn zigbeelens.main:app --host" not in text


def test_dockerfile_healthcheck_follows_zigbeelens_port():
    dockerfile = (REPO_ROOT / "deploy" / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "python -m zigbeelens.docker_healthcheck" in dockerfile
    assert "ZIGBEELENS_PORT=8377" in dockerfile
    # Literal-only :8377 health URL must not be the probe target.
    assert "http://127.0.0.1:8377/api/health" not in dockerfile
