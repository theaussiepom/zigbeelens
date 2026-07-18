"""CSP, framing, and general security-header middleware."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.main import create_app
from zigbeelens.security.headers import GENERAL_HEADERS, build_csp

VALID_TOKEN = "b" * 32
HA = "https://ha.example"


def _static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(
        "<!doctype html><html><body>ui</body></html>", encoding="utf-8"
    )
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return root


def _client(
    tmp_path: Path,
    monkeypatch,
    *,
    frames: str = "[]",
    openapi: bool = False,
) -> TestClient:
    static = _static_dir(tmp_path)
    monkeypatch.setenv("ZIGBEELENS_STATIC_DIR", str(static))
    if openapi:
        monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    else:
        monkeypatch.delenv("ZIGBEELENS_OPENAPI_ENABLED", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
server:
  host: 127.0.0.1
mode:
  mock: true
storage:
  path: {tmp_path / "hdr.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
security:
  api_token: {VALID_TOKEN}
  frame_ancestor_origins: {frames}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)))


def test_build_csp_frame_ancestors():
    csp = build_csp(frame_ancestor_origins=(HA,))
    assert "frame-ancestors 'self' https://ha.example" in csp
    assert "*" not in csp
    assert "unsafe-eval" not in csp
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    docs = build_csp(frame_ancestor_origins=(), docs=True)
    assert "cdn.jsdelivr.net" in docs
    assert "unsafe-inline" in docs


def test_frame_ancestor_is_single_csp_source():
    import pytest
    from pydantic import ValidationError

    from zigbeelens.config.models import SecurityConfig
    from zigbeelens.security.headers import _frame_ancestors

    with pytest.raises(ValidationError):
        SecurityConfig(
            frame_ancestor_origins=["https://trusted.example evil.example"]
        )
    with pytest.raises(ValidationError):
        SecurityConfig(frame_ancestor_origins=["https://exa mple.com"])
    ancestors = _frame_ancestors((HA,))
    assert ancestors == ("'self'", HA)
    assert all(" " not in item for item in ancestors if item != "'self'")
    with pytest.raises(AssertionError):
        _frame_ancestors(("https://trusted.example evil.example",))


def test_default_html_framing_sameorigin(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        for path in ("/", "/devices", "/topology/home/graph"):
            res = client.get(path)
            assert res.status_code == 200
            assert "text/html" in res.headers.get("content-type", "")
            csp = res.headers.get("content-security-policy") or ""
            assert "frame-ancestors 'self'" in csp
            assert "*" not in csp
            assert res.headers.get("x-frame-options") == "SAMEORIGIN"
            assert res.headers.get("x-content-type-options") == "nosniff"
            assert res.headers.get("referrer-policy") == "no-referrer"
            assert "camera=()" in (res.headers.get("permissions-policy") or "")
            assert res.headers.get("strict-transport-security") is None


def test_external_frame_ancestor_omits_xfo(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, frames=f'["{HA}"]') as client:
        res = client.get("/")
        csp = res.headers.get("content-security-policy") or ""
        assert f"frame-ancestors 'self' {HA}" in csp
        assert res.headers.get("x-frame-options") is None
        assert HA in csp
        assert "https://evil.example" not in csp


def test_assets_have_general_headers_not_document_csp(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        res = client.get("/assets/app.js")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        # Non-HTML assets should not receive the document CSP.
        ctype = res.headers.get("content-type", "")
        if "text/html" not in ctype:
            assert res.headers.get("content-security-policy") is None


def test_json_api_no_html_csp(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        res = client.get("/api/version", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("content-security-policy") is None
        assert res.headers.get("x-frame-options") is None


def test_docs_csp_separate_when_enabled(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, openapi=True) as client:
        docs = client.get("/docs", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert docs.status_code == 200
        csp = docs.headers.get("content-security-policy") or ""
        assert "cdn.jsdelivr.net" in csp
        assert "unsafe-inline" in csp
        ui = client.get("/")
        ui_csp = ui.headers.get("content-security-policy") or ""
        assert "cdn.jsdelivr.net" not in ui_csp
        assert "script-src 'self'" in ui_csp
        assert "unsafe-eval" not in ui_csp


def test_general_headers_constant():
    assert GENERAL_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert GENERAL_HEADERS["Referrer-Policy"] == "no-referrer"
