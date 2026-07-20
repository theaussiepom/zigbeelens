"""Track 6 storage status API tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.main import create_app


def test_storage_status_aliases_and_defaults(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "status.sqlite"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {db_path}
  retention_days: 7
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg_path))
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path), retention_days=7),
    )
    app = create_app(config_path=str(cfg_path), resolved_config=cfg)
    with TestClient(app) as client:
        caps = client.get("/api/capabilities").json()
        assert caps["capabilities"]["retention_policy_v2"] is True
        assert caps["capabilities"]["periodic_storage_maintenance"] is True
        assert caps["capabilities"]["online_sqlite_backup_cli"] is True
        assert caps["capabilities"]["storage_integrity_checks"] is True

        a = client.get("/api/storage/status")
        b = client.get("/api/v1/storage/status")
        assert a.status_code == 200
        assert b.status_code == 200
        assert a.json() == b.json()
        body = a.json()
        assert body["policy"]["telemetry_retention_days"] == 7
        assert body["policy"]["resolved_incident_retention_days"] == 90
        assert body["policy"]["report_retention_days"] is None
        assert "database_bytes" in body["footprint"]

        cfg_status = client.get("/api/config/status").json()
        assert cfg_status["retention_days"] == 7
        assert cfg_status["report_retention_days"] is None
        assert cfg_status["storage"]["policy"]["telemetry_retention_days"] == 7
