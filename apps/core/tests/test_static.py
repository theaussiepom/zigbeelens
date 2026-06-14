from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.main import create_app
from zigbeelens.static import mount_static_ui, resolve_static_dir

from conftest import write_config


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


def test_event_stream_route_precedes_static_spa_fallback(tmp_path, monkeypatch):
    """The SSE route must win over the SPA catch-all when static UI is mounted.

    Regression: if `/{full_path:path}` is registered before the event stream,
    `/api/events/stream` resolves to the HTML fallback (404 for api paths) and
    the UI is stuck "reconnecting". We assert route registration order so we
    never make a (never-ending) live SSE request.
    """
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html><body>ZigbeeLens UI</body></html>", encoding="utf-8")
    monkeypatch.setenv("ZIGBEELENS_STATIC_DIR", str(static))

    config_path = tmp_path / "config.yaml"
    write_config(config_path, mock=True, db_path=tmp_path / "sse.sqlite")
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))

    app = create_app(str(config_path))

    paths = [getattr(r, "path", None) for r in app.router.routes]
    assert "/api/events/stream" in paths, "event stream route missing"
    sse_index = paths.index("/api/events/stream")
    catch_all_index = paths.index("/{full_path:path}")
    assert sse_index < catch_all_index, "SSE route must precede the SPA catch-all"
