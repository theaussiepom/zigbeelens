"""First-party proxy-header posture and default AppConfig ownership."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from zigbeelens.api.auth import request_same_origin
from zigbeelens.app.context import get_context
from zigbeelens.config.http_origin import InvalidHttpOrigin
from zigbeelens.main import _UVICORN_NO_PROXY_TRUST, create_app, run_server


def _write_config(
    path: Path,
    *,
    cors: str = '["https://ui.example"]',
    networks: int = 1,
) -> None:
    nets = "\n".join(
        f"  - id: n{i}\n    name: N{i}\n    base_topic: zigbee2mqtt{i}"
        for i in range(networks)
    )
    path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: true
storage:
  path: {path.parent / "own.sqlite"}
networks:
{nets}
security:
  cors_allowed_origins: {cors}
""",
        encoding="utf-8",
    )


def test_run_server_disables_proxy_header_trust(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    for reload in (False, True):
        captured: dict = {}
        with patch(
            "uvicorn.run", side_effect=lambda *a, **kwargs: captured.update(kwargs)
        ):
            run_server(cfg, reload=reload)
        assert captured["proxy_headers"] is False
        assert captured["forwarded_allow_ips"] == ""
        assert _UVICORN_NO_PROXY_TRUST["proxy_headers"] is False


def test_forwarded_proto_does_not_change_request_scheme(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    app = create_app(str(cfg))
    seen: dict[str, str] = {}

    @app.middleware("http")
    async def capture(request, call_next):
        seen["scheme"] = request.url.scheme
        seen["origin"] = str(request_same_origin(request))
        return await call_next(request)

    with TestClient(app, base_url="http://testserver") as client:
        client.get(
            "/api/version",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "203.0.113.9",
                "Forwarded": "proto=https;for=203.0.113.9",
            },
        )
        assert seen["scheme"] == "http"
        assert seen["origin"] == "http://testserver"


def test_create_app_uses_resolve_config_path_default(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, networks=2, cors='["https://a.example"]')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZIGBEELENS_CONFIG", raising=False)
    # Place the tracked default path relative to cwd.
    (tmp_path / "config").mkdir()
    default = tmp_path / "config" / "config.yaml"
    default.write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/version").status_code == 200
        ctx = get_context()
        assert len(ctx.config.networks) == 2
        assert ctx.config.security.cors_allowed_origins == ("https://a.example",)
        assert ctx.config.security.cors_allowed_origins == ("https://a.example",)
        pre = client.options(
            "/api/version",
            headers={
                "Origin": "https://a.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert pre.headers.get("access-control-allow-origin") == "https://a.example"


def test_secret_file_read_once_at_create_app(tmp_path, monkeypatch):
    token_file = tmp_path / "token.txt"
    token_file.write_text("t" * 32, encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "sec.sqlite"}
networks: []
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN", raising=False)
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(token_file))

    reads = {"n": 0}
    real_read_bytes = Path.read_bytes

    def counting_read_bytes(self, *args, **kwargs):
        if self.resolve() == token_file.resolve():
            reads["n"] += 1
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    app = create_app(str(cfg))
    first_reads = reads["n"]
    assert first_reads == 1
    token_file.write_text("u" * 32, encoding="utf-8")
    with TestClient(app) as client:
        ctx = get_context()
        assert ctx.config.security.api_token is not None
        assert ctx.config.security.api_token.get_secret_value() == "t" * 32
        assert client.get("/api/version").status_code == 200
    # Lifespan must not reread the mutated secret file.
    assert reads["n"] == first_reads


def test_malformed_host_fails_origin_closed():
    def req(host: str) -> Request:
        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": [(b"host", host.encode("utf-8"))],
                "client": ("127.0.0.1", 1),
                "server": ("127.0.0.1", 80),
            }
        )

    for host in (
        "example.com:notaport",
        "example.com:0",
        "example.com:65536",
        "user@example.com",
        "[::1",
        "exampl\x01e.com",
    ):
        with pytest.raises(InvalidHttpOrigin) as exc_info:
            request_same_origin(req(host))
        assert host not in str(exc_info.value)

    dup = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"host", b"a.example"), (b"host", b"b.example")],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        }
    )
    with pytest.raises(InvalidHttpOrigin):
        request_same_origin(dup)

    # Valid IPv6 and ordinary hosts still work when ASGI provides them.
    good = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"host", b"[::1]:8377")],
            "client": ("::1", 1),
            "server": ("::1", 8377),
        }
    )
    assert request_same_origin(good) == "http://[::1]:8377"
    ordinary = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"host", b"localhost:8377")],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8377),
        }
    )
    assert request_same_origin(ordinary) == "http://localhost:8377"


def test_docs_cookie_mutation_examples_include_origin():
    root = Path(__file__).resolve().parents[3]
    security = (root / "docs" / "security.md").read_text(encoding="utf-8")
    release = (root / "docs" / "release-test.md").read_text(encoding="utf-8")
    assert 'Origin: http://127.0.0.1:8377' in security
    assert "X-ZigbeeLens-CSRF-Token" in security
    assert "Origin: http://localhost:8377" in release
    # Bearer examples remain Origin-free in the nearby bearer report block.
    assert "Authorization: Bearer" in release
