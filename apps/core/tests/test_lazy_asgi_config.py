"""Import-safe ASGI entry and single AppConfig ownership."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context
from zigbeelens.config.loader import load_effective_config
from zigbeelens.main import LazyASGIApp, create_app, main, run_server


def _write_mock_config(path: Path, *, cors: str = "[]", token_file: Path | None = None) -> None:
    token_yaml = ""
    if token_file is not None:
        token_yaml = ""  # token comes from env FILE
    path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: true
storage:
  path: {path.parent / "lazy.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  cors_allowed_origins: {cors}
{token_yaml}
""",
        encoding="utf-8",
    )


def test_import_main_performs_no_config_io(tmp_path: Path) -> None:
    """Import zigbeelens.main with no default config and no secrets."""
    core_src = Path(__file__).resolve().parents[1] / "src"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("ZIGBEELENS_")
    }
    env["PYTHONPATH"] = str(core_src)
    script = textwrap.dedent(
        """
        import zigbeelens.config.loader as loader

        def boom(*_a, **_k):
            raise AssertionError("configuration I/O during import")

        loader.load_effective_config = boom  # type: ignore[assignment]
        loader.resolve_config_path = boom  # type: ignore[assignment]
        loader._read_secret_file = boom  # type: ignore[attr-defined]

        import zigbeelens.main as main_mod

        assert isinstance(main_mod.app, main_mod.LazyASGIApp)
        assert repr(main_mod.app) == "LazyASGIApp()"
        assert "token" not in repr(main_mod.app).lower()
        assert "secret" not in repr(main_mod.app).lower()
        print("IMPORT_OK")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "IMPORT_OK" in proc.stdout


def test_console_main_uses_explicit_config_before_load(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "custom.yaml"
    _write_mock_config(cfg, cors='["https://ui.example"]')
    # No default config in cwd.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZIGBEELENS_CONFIG", raising=False)
    captured: dict = {}

    def fake_run(application, **kwargs):
        captured["app"] = application
        captured["kwargs"] = kwargs

    with patch("uvicorn.run", side_effect=fake_run):
        main(["--config", str(cfg)])
    assert captured["kwargs"]["proxy_headers"] is False
    with TestClient(captured["app"]) as client:
        ctx = get_context()
        assert ctx.config.security.cors_allowed_origins == ("https://ui.example",)
        assert client.get("/api/version").status_code == 200


def test_run_server_reads_secret_file_once(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("t" * 32, encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    _write_mock_config(cfg)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN", raising=False)

    reads = {"n": 0}
    real = Path.read_bytes

    def counting(self, *a, **kw):
        if self.resolve() == token_file.resolve():
            reads["n"] += 1
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_bytes", counting)
    captured: dict = {}

    def fake_run(application, **kwargs):
        captured["app"] = application

    with patch("uvicorn.run", side_effect=fake_run):
        run_server(cfg, reload=False)
    assert reads["n"] == 1
    token_file.write_text("u" * 32, encoding="utf-8")
    with TestClient(captured["app"]) as client:
        ctx = get_context()
        assert ctx.config.security.api_token is not None
        assert ctx.config.security.api_token.get_secret_value() == "t" * 32
        pre = client.options(
            "/api/version",
            headers={
                "Origin": "https://ui.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS empty by default in this fixture — policy still from same cfg.
        assert ctx.config.security.api_token.get_secret_value() == "t" * 32
        assert client.get("/api/version").status_code == 200
    assert reads["n"] == 1
    assert pre.status_code in {200, 204, 400}


def test_lazy_asgi_app_loads_once(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    _write_mock_config(cfg, cors='["https://a.example"]')
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN", raising=False)
    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", raising=False)

    loads = {"n": 0}
    real_load = load_effective_config

    def counting_load(path):
        loads["n"] += 1
        return real_load(path)

    monkeypatch.setattr("zigbeelens.main.load_effective_config", counting_load)
    lazy = LazyASGIApp()
    assert loads["n"] == 0
    assert "LazyASGIApp()" == repr(lazy)

    with TestClient(lazy) as client:
        assert loads["n"] == 1
        ctx = get_context()
        assert ctx.config.security.cors_allowed_origins == ("https://a.example",)
        pre = client.options(
            "/api/version",
            headers={
                "Origin": "https://a.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert pre.headers.get("access-control-allow-origin") == "https://a.example"
        monkeypatch.setenv("ZIGBEELENS_CONFIG", str(tmp_path / "missing.yaml"))
        assert client.get("/api/version").status_code == 200
        assert ctx.config.security.cors_allowed_origins == ("https://a.example",)
    assert loads["n"] == 1
    assert "resolved" in repr(lazy)


def test_create_app_explicit_and_resolved_still_work(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    _write_mock_config(cfg, cors='["https://b.example"]')
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    resolved = load_effective_config(cfg)
    app = create_app(str(cfg), resolved_config=resolved)
    with TestClient(app) as client:
        assert get_context().config is resolved
        assert get_context().config.security.cors_allowed_origins == ("https://b.example",)
        assert client.get("/api/version").status_code == 200
