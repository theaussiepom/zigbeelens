"""Pre-Track-6 (schema v11) → migration 012 → default maintenance upgrade proof."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.integrity import foreign_key_check, quick_check
from zigbeelens.storage.maintenance import run_storage_maintenance
from zigbeelens.storage.repository import Repository
from zigbeelens.storage.retention_policy import ABANDONED_TOPOLOGY_ERROR

REF = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def _load_migrations_through(version: int) -> list[tuple[int, str]]:
    migrations_dir = (
        Path(__file__).resolve().parents[1] / "src/zigbeelens/db/migrations"
    )
    items: list[tuple[int, str]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        ver = int(path.name.split("_", 1)[0])
        if ver <= version:
            items.append((ver, path.read_text(encoding="utf-8")))
    return items


def test_pre_track6_upgrade_preserves_reports_and_active_incidents(tmp_path: Path):
    db_path = tmp_path / "v11.sqlite"
    db = Database(db_path)
    # Apply only through schema v11 (pre Track 6 indexes).
    with db._lock:
        db._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        for version, sql in _load_migrations_through(11):
            db._conn.executescript(sql)
            db._conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            db._conn.commit()
        db.migration_version = 11

    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    repo.db.conn.execute(
        """
        INSERT INTO devices (network_id, ieee_address, friendly_name, device_type)
        VALUES ('home', '0xabc', 'Lamp', 'EndDevice')
        """
    )
    repo.db.conn.execute(
        """
        INSERT INTO device_current_state
          (network_id, ieee_address, availability, last_seen, updated_at)
        VALUES ('home', '0xabc', 'online', ?, ?)
        """,
        (REF.isoformat(), REF.isoformat()),
    )

    old_telemetry = (REF - timedelta(days=30)).isoformat()
    recent_resolved = (REF - timedelta(days=10)).isoformat()
    old_resolved = (REF - timedelta(days=120)).isoformat()
    forms = [
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00Z",
        "2026-01-01 00:00:00",
        "2026-01-01T10:00:00+10:00",
    ]
    for i, ts in enumerate(forms):
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (f"evt-form-{i}", ts),
        )
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-old', 'test', 'watch', 't', 's', ?)
        """,
        (old_telemetry,),
    )

    for incident_id, state, resolved_at in [
        ("inc-open", "open", None),
        ("inc-watch", "watching", None),
        ("inc-old", "resolved", old_resolved),
        ("inc-recent", "resolved", recent_resolved),
    ]:
        repo.insert_incident(
            incident_id=incident_id,
            dedup_key=f"{incident_id}:home",
            incident_type="single_device_unavailable",
            lifecycle_state=state,
            severity="incident",
            scope="device",
            confidence="high",
            title=incident_id,
            summary=incident_id,
            explanation="t",
            evidence=[],
            counter_evidence=[],
            limitations=[],
            opened_at=resolved_at or old_telemetry,
            updated_at=resolved_at or old_telemetry,
        )
        if resolved_at is not None:
            repo.update_incident(
                incident_id=incident_id, resolved_at=resolved_at, updated_at=resolved_at
            )
    repo.db.conn.execute(
        """
        INSERT INTO events
          (id, event_type, severity, title, summary, occurred_at, incident_id)
        VALUES ('evt-link', 'test', 'watch', 't', 's', ?, 'inc-old')
        """,
        (REF.isoformat(),),
    )

    bodies = {
        "r1": '{"report_version":1,"note":"keep-v1"}',
        "r2": '{"report_version":2,"note":"keep-v2"}',
        "r3": '{"report_version":3,"note":"keep-v3"}',
    }
    for rid, body in bodies.items():
        repo.db.conn.execute(
            """
            INSERT INTO reports
              (id, format, redaction_json, summary, generated_at, body_json)
            VALUES (?, 'json', '{}', 'Report', ?, ?)
            """,
            (rid, old_telemetry, body),
        )

    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES
          ('snap-complete', 'home', ?, 'test', 'complete', 0),
          ('snap-error', 'home', ?, 'test', 'error', 0),
          ('snap-pending', 'home', ?, 'test', 'pending', 0)
        """,
        (
            old_telemetry,
            old_telemetry,
            (REF - timedelta(hours=1)).isoformat(),
        ),
    )
    repo.db.conn.execute(
        """
        INSERT INTO topology_nodes
          (snapshot_id, network_id, ieee_address, node_type, friendly_name)
        VALUES ('snap-complete', 'home', '0xabc', 'EndDevice', 'Lamp')
        """
    )
    repo.db.conn.commit()
    assert db.migration_version == 11

    # Upgrade path: migration 012, integrity, default Track 6 maintenance.
    assert db.migrate() == 14
    quick_check(db)
    foreign_key_check(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path)),
    )
    result = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert result.success
    foreign_key_check(db)

    # Migration 014 is a deliberate pre-release report wipe; older report rows
    # are not retained across the Track 6 → schema 14 upgrade path.
    report_count = repo.db.conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]
    assert report_count == 0
    assert bodies  # seeded pre-upgrade development reports existed before wipe
    incident_ids = {row["id"] for row in repo.list_incidents()}
    assert {"inc-open", "inc-watch", "inc-recent"} <= incident_ids
    assert "inc-old" not in incident_ids
    assert (
        repo.db.conn.execute(
            "SELECT incident_id FROM events WHERE id='evt-link'"
        ).fetchone()[0]
        is None
    )
    assert (
        repo.db.conn.execute("SELECT COUNT(*) FROM events WHERE id='evt-old'").fetchone()[
            0
        ]
        == 0
    )
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM device_current_state WHERE ieee_address='0xabc'"
        ).fetchone()[0]
        == 1
    )
    pending = repo.db.conn.execute(
        "SELECT status, error FROM topology_snapshots WHERE snapshot_id='snap-pending'"
    ).fetchone()
    assert pending["status"] == "error"
    assert pending["error"] == ABANDONED_TOPOLOGY_ERROR
    assert result.rows_deleted_by_category.get("topology_snapshots", 0) >= 1
    # Newly terminalized abandoned pending is not deleted in the same cycle.
    assert result.rows_updated_by_category.get("abandoned_pending_topology", 0) == 1
    assert (
        repo.db.conn.execute(
            "SELECT COUNT(*) FROM topology_snapshots WHERE snapshot_id='snap-pending'"
        ).fetchone()[0]
        == 1
    )
