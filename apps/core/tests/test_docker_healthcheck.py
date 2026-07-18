"""Docker HEALTHCHECK port resolution — no AppConfig / secret loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zigbeelens.docker_healthcheck import (
    DEFAULT_PORT,
    healthcheck_url,
    main,
    resolve_healthcheck_port,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_default_port_is_8377():
    assert DEFAULT_PORT == 8377
    assert resolve_healthcheck_port({}) == 8377
    assert healthcheck_url({}) == "http://127.0.0.1:8377/healthz"


def test_zigbeelens_port_overrides_target():
    env = {"ZIGBEELENS_PORT": "9123"}
    assert resolve_healthcheck_port(env) == 9123
    assert healthcheck_url(env) == "http://127.0.0.1:9123/healthz"


@pytest.mark.parametrize("raw", ["", "not-a-port", "0", "65536", "-1", "12.5"])
def test_invalid_port_raises(raw: str):
    with pytest.raises(ValueError):
        resolve_healthcheck_port({"ZIGBEELENS_PORT": raw})


def test_main_fails_safely_on_invalid_port(monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_PORT", "not-a-port")
    assert main([]) == 1


def test_main_probes_health_url_without_token(monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_PORT", "9123")
    with patch("zigbeelens.docker_healthcheck.urllib.request.urlopen") as urlopen:
        urlopen.return_value = MagicMock()
        assert main([]) == 0
        urlopen.assert_called_once()
        args, kwargs = urlopen.call_args
        assert args[0] == "http://127.0.0.1:9123/healthz"
        assert kwargs.get("timeout") == 5


def test_healthcheck_module_does_not_load_appconfig():
    source = (
        REPO_ROOT / "apps/core/src/zigbeelens/docker_healthcheck.py"
    ).read_text(encoding="utf-8")
    assert "from zigbeelens.config" not in source
    assert "import zigbeelens.config" not in source
    assert "load_config" not in source
    assert "load_effective_config" not in source
    assert "api_token" not in source
    assert "Authorization" not in source
    assert "X-ZigbeeLens-Api-Key" not in source
    assert "/healthz" in source
    assert "/api/health" not in source


def test_dockerfile_uses_module_not_literal_url():
    dockerfile = (REPO_ROOT / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
    assert "python -m zigbeelens.docker_healthcheck" in dockerfile
    assert "http://127.0.0.1:8377/api/health" not in dockerfile
    assert "healthz" in dockerfile
