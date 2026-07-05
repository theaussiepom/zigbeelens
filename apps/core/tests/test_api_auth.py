"""Optional API key middleware tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from zigbeelens.main import create_app


def test_mutating_routes_open_without_api_key(mock_client: TestClient):
    res = mock_client.post("/api/reports", json={"format": "json"})
    assert res.status_code == 200


def test_mutating_routes_require_api_key_when_configured(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mode:
  mock: true
storage:
  path: {db}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
""".format(db=tmp_path / "auth.sqlite"),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_API_KEY", "secret-key")
    app = create_app(str(config_path))
    with TestClient(app) as client:
        blocked = client.post("/api/reports", json={"format": "json"})
        assert blocked.status_code == 401

        ok = client.post(
            "/api/reports",
            json={"format": "json"},
            headers={"X-ZigbeeLens-Api-Key": "secret-key"},
        )
        assert ok.status_code == 200

        get_ok = client.get("/api/dashboard")
        assert get_ok.status_code == 200
