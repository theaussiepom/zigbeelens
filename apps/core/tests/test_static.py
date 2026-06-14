from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.main import create_app
from zigbeelens.static import mount_static_ui, resolve_static_dir


def test_resolve_static_dir_from_env(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("ZIGBEELENS_STATIC_DIR", str(static))
    assert resolve_static_dir() == static


def test_mount_static_ui_serves_spa(tmp_path, monkeypatch):
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("<html><body>ZigbeeLens UI</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")

    monkeypatch.setenv("ZIGBEELENS_STATIC_DIR", str(static))
    app = create_app()
    assert mount_static_ui(app) is True

    client = TestClient(app)
    assert "ZigbeeLens UI" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert "ZigbeeLens UI" in client.get("/incidents").text
