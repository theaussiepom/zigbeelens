"""Storage retention enforcement tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository, utc_now_iso
from zigbeelens.storage.retention import enforce_storage_retention


def _config(db_path: Path, retention_days: int = 7) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=False),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path), retention_days=retention_days),
    )


def test_purge_removes_old_events_and_reports(tmp_path: Path):
    db = Database(tmp_path / "retention.sqlite")
    db.migrate()
    repo = Repository(db)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-old', 'test', 'watch', 'Old', 'Old event', ?)
        """,
        (old_ts,),
    )
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-new', 'test', 'watch', 'New', 'New event', ?)
        """,
        (utc_now_iso(),),
    )
    repo.db.conn.execute(
        """
        INSERT INTO reports (id, format, redaction_json, summary, generated_at)
        VALUES ('rep-old', 'json', '{}', 'Old report', ?)
        """,
        (old_ts,),
    )
    repo.db.conn.commit()

    counts = enforce_storage_retention(repo, retention_days=7)

    assert counts["events"] == 1
    assert counts["reports"] == 1
    remaining_events = repo.db.conn.execute("SELECT id FROM events").fetchall()
    assert [row[0] for row in remaining_events] == ["evt-new"]


def test_purge_keeps_active_incidents(tmp_path: Path):
    db = Database(tmp_path / "incidents.sqlite")
    db.migrate()
    repo = Repository(db)
    old_resolved = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    now = utc_now_iso()

    repo.insert_incident(
        incident_id="inc-open",
        dedup_key="open:home",
        incident_type="single_device_unavailable",
        lifecycle_state="open",
        severity="incident",
        scope="device",
        confidence="high",
        title="Open",
        summary="Still open",
        explanation="Test",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=now,
        updated_at=now,
    )
    repo.insert_incident(
        incident_id="inc-old-resolved",
        dedup_key="resolved:home",
        incident_type="single_device_unavailable",
        lifecycle_state="resolved",
        severity="incident",
        scope="device",
        confidence="high",
        title="Resolved old",
        summary="Old resolved",
        explanation="Test",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at=old_resolved,
        updated_at=old_resolved,
    )
    repo.update_incident(
        incident_id="inc-old-resolved",
        resolved_at=old_resolved,
        updated_at=old_resolved,
    )
    counts = enforce_storage_retention(repo, retention_days=7)

    assert counts["incidents_resolved"] == 1
    remaining = {row["id"] for row in repo.list_incidents()}
    assert remaining == {"inc-open"}


def test_bootstrap_runs_retention(tmp_path: Path, monkeypatch):
    from zigbeelens.app.context import bootstrap, reset_context

    db_path = tmp_path / "boot.sqlite"
    cfg = _config(db_path, retention_days=7)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
mode:
  mock: false
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

    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-old', 'test', 'watch', 'Old', 'Old event', ?)
        """,
        (old_ts,),
    )
    repo.db.conn.commit()
    db.close()

    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg_path))
    ctx = bootstrap(config_path=str(cfg_path), config=cfg)
    try:
        remaining = ctx.repo.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert remaining == 0
    finally:
        reset_context()
