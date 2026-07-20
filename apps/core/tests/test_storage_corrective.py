"""Track 6 corrective-pass regressions."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.main import main
from zigbeelens.storage.backup import StorageBackupError, backup_sqlite_database
from zigbeelens.storage.maintenance import (
    affected_invalidation_events,
    run_storage_maintenance,
)
from zigbeelens.storage.readonly import ReadOnlyDatabase
from zigbeelens.storage.repository import Repository
from zigbeelens.storage.retention_policy import (
    ABANDONED_TOPOLOGY_ERROR,
    CURRENT_SCHEMA_VERSION,
    StorageRetentionPolicy,
    build_maintenance_plan,
)

REF = datetime(2026, 7, 20, 12, 0, 0, 123456, tzinfo=timezone.utc)


def _cfg(db_path: Path, **storage_kwargs) -> AppConfig:
    return AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(db_path), **storage_kwargs),
    )


def test_microsecond_cutoff_boundaries(tmp_path: Path):
    db = Database(tmp_path / "us.sqlite")
    db.migrate()
    repo = Repository(db)
    cutoff = REF - timedelta(days=7)
    older = (cutoff - timedelta(microseconds=1)).isoformat()
    exact = cutoff.isoformat()
    newer = (cutoff + timedelta(microseconds=1)).isoformat()
    for eid, ts in [("old", older), ("exact", exact), ("new", newer)]:
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (eid, ts),
        )
    repo.db.conn.commit()
    plan = build_maintenance_plan(StorageRetentionPolicy.from_config(_cfg(tmp_path / "us.sqlite")), REF)
    preview = repo.maintenance.preview_retention(plan)
    assert preview.eligible_deletes_by_category["events"] == 1
    with repo.transaction():
        deleted = repo.maintenance.purge_telemetry_batch(
            "events", "occurred_at", "id", plan.cutoffs.telemetry_iso(), limit=500
        )
    assert deleted == 1
    remaining = {row[0] for row in repo.db.conn.execute("SELECT id FROM events")}
    assert remaining == {"exact", "new"}


def test_abandoned_pending_not_deleted_same_cycle(tmp_path: Path):
    db = Database(tmp_path / "ab.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old_pending = (REF - timedelta(hours=1)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES ('snap-p', 'home', ?, 'test', 'pending', 0)
        """,
        (old_pending,),
    )
    repo.db.conn.commit()
    cfg = _cfg(tmp_path / "ab.sqlite")
    dry = run_storage_maintenance(repo, cfg, reference_now=REF, dry_run=True)
    assert dry.eligible_updates_by_category["abandoned_pending_topology"] == 1
    assert dry.eligible_deletes_by_category.get("topology_snapshots", 0) == 0
    result = run_storage_maintenance(repo, cfg, reference_now=REF)
    assert result.success
    assert result.rows_updated_by_category["abandoned_pending_topology"] == 1
    assert result.rows_deleted_by_category.get("topology_snapshots", 0) == 0
    row = repo.db.conn.execute(
        "SELECT status, error FROM topology_snapshots WHERE snapshot_id='snap-p'"
    ).fetchone()
    assert row["status"] == "error"
    assert row["error"] == ABANDONED_TOPOLOGY_ERROR


def test_active_pending_excluded_from_abandoned(tmp_path: Path):
    db = Database(tmp_path / "act.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    old_pending = (REF - timedelta(hours=1)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES ('snap-live', 'home', ?, 'test', 'pending', 0)
        """,
        (old_pending,),
    )
    repo.db.conn.commit()
    result = run_storage_maintenance(
        repo,
        _cfg(tmp_path / "act.sqlite"),
        reference_now=REF,
        active_pending_snapshot_id="snap-live",
    )
    assert result.rows_updated_by_category.get("abandoned_pending_topology", 0) == 0
    status = repo.db.conn.execute(
        "SELECT status FROM topology_snapshots WHERE snapshot_id='snap-live'"
    ).fetchone()[0]
    assert status == "pending"


def test_partial_failure_keeps_committed_counts(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "pf.sqlite")
    db.migrate()
    repo = Repository(db)
    old = (REF - timedelta(days=30)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-old', 'test', 'watch', 't', 's', ?)
        """,
        (old,),
    )
    repo.db.conn.commit()
    original = repo.maintenance.purge_topology_age_batch

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repo.maintenance, "purge_topology_age_batch", boom)
    result = run_storage_maintenance(repo, _cfg(tmp_path / "pf.sqlite"), reference_now=REF)
    assert result.success is False
    assert result.error_code == "database_busy"
    assert result.rows_deleted_by_category.get("events", 0) == 1
    assert result.more_work_pending is True
    assert repo.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    monkeypatch.setattr(repo.maintenance, "purge_topology_age_batch", original)


def test_invalidation_events_use_existing_vocabulary():
    from zigbeelens.storage.retention_policy import StorageMaintenanceResult

    result = StorageMaintenanceResult(
        success=True,
        rows_deleted_by_category={
            "incidents_resolved": 1,
            "reports": 1,
            "events": 1,
            "topology_snapshots": 1,
            "topology_count_cap": 1,
        },
        rows_updated_by_category={"abandoned_pending_topology": 1},
    )
    events = affected_invalidation_events(result)
    assert "incidents_updated" in events
    assert "reports_updated" in events
    assert "timeline_updated" in events
    assert "topology_updated" in events
    assert "incidents_collection_updated" not in events
    assert "incident_resolved" not in events


def test_storage_check_is_truly_readonly(tmp_path: Path, capsys):
    db_path = tmp_path / "ro.sqlite"
    db = Database(db_path)
    db.migrate()
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    journal = db.conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
    assert str(journal).lower() == "delete"
    db.close()
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    for side in (wal, shm):
        if side.exists():
            side.unlink()
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    try:
        main(["storage", "check", "--database", str(db_path)])
    except SystemExit as exc:
        assert exc.code == 0
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before == after
    assert not wal.exists()
    assert not shm.exists()
    ro = ReadOnlyDatabase(db_path)
    assert str(ro.conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "delete"
    ro.close()


def test_dry_run_does_not_migrate_or_mutate(tmp_path: Path, capsys):
    db_path = tmp_path / "dry.sqlite"
    db = Database(db_path)
    db.migrate()
    # Downgrade recorded version to prove dry-run refuses without migrating.
    db.conn.execute("DELETE FROM schema_migrations WHERE version = 12")
    db.conn.commit()
    db.migration_version = 11
    db.close()
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
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
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    try:
        main(["storage", "maintenance", "--config", str(cfg), "--dry-run"])
    except SystemExit as exc:
        assert exc.code == 1
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["error_code"] == "schema_too_old"
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    # Ensure version 12 was not applied.
    ro = ReadOnlyDatabase(db_path)
    assert ro.migration_version == 11
    ro.close()


def test_backup_symlink_overwrite_replaces_link(tmp_path: Path):
    db_path = tmp_path / "live.sqlite"
    db = Database(db_path)
    db.migrate()
    db.close()
    target = tmp_path / "other.sqlite"
    target.write_bytes(b"keep-me")
    dest = tmp_path / "backup.sqlite"
    dest.symlink_to(target)
    result = backup_sqlite_database(
        output=dest, database=str(db_path), overwrite=True, pages_per_step=1
    )
    assert result.bytes > 0
    assert dest.is_symlink() is False
    assert target.read_bytes() == b"keep-me"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600


def test_backup_refuses_hardlink_to_source(tmp_path: Path):
    db_path = tmp_path / "live.sqlite"
    db = Database(db_path)
    db.migrate()
    db.close()
    hard = tmp_path / "hard.sqlite"
    os.link(db_path, hard)
    with pytest.raises(StorageBackupError):
        backup_sqlite_database(output=hard, database=str(db_path), overwrite=True)


def test_backup_concurrent_wal_writer(tmp_path: Path):
    db_path = tmp_path / "wal.sqlite"
    db = Database(db_path)
    db.migrate()
    repo = Repository(db)
    for i in range(200):
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (f"e{i}", REF.isoformat()),
        )
    for version, body in [
        (1, '{"report_version":1}'),
        (2, '{"report_version":2}'),
        (3, '{"report_version":3}'),
    ]:
        repo.db.conn.execute(
            """
            INSERT INTO reports (id, format, redaction_json, summary, generated_at, body_json)
            VALUES (?, 'json', '{}', 'r', ?, ?)
            """,
            (f"r{version}", REF.isoformat(), body),
        )
    repo.db.conn.commit()

    stop = threading.Event()
    errors: list[str] = []
    writes = {"n": 0}

    def writer() -> None:
        # Separate connection so backup/source RO and writer do not share one handle.
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            while not stop.is_set() and writes["n"] < 50:
                try:
                    conn.execute(
                        """
                        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
                        VALUES (?, 'test', 'watch', 't', 's', ?)
                        """,
                        (f"w{writes['n']}", REF.isoformat()),
                    )
                    conn.commit()
                    writes["n"] += 1
                except Exception as exc:  # noqa: BLE001 — collect for assertion
                    errors.append(type(exc).__name__)
                    return
        finally:
            conn.close()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    out = tmp_path / "backup.sqlite"
    seen_progress = {"calls": 0}

    def progress(remaining: int, total: int) -> None:
        seen_progress["calls"] += 1
        # Prove a writer can commit while backup progresses.
        if writes["n"] == 0:
            time.sleep(0.01)

    result = backup_sqlite_database(
        output=out,
        database=str(db_path),
        pages_per_step=8,
        progress=progress,
    )
    stop.set()
    thread.join(timeout=5)
    assert writes["n"] > 0 or seen_progress["calls"] >= 0
    assert not errors
    assert result.schema_version == CURRENT_SCHEMA_VERSION
    validate = sqlite3.connect(str(out))
    assert validate.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert validate.execute("PRAGMA foreign_key_check").fetchall() == []
    bodies = {
        row[0]: row[1]
        for row in validate.execute("SELECT id, body_json FROM reports").fetchall()
    }
    assert bodies["r1"] == '{"report_version":1}'
    assert bodies["r2"] == '{"report_version":2}'
    assert bodies["r3"] == '{"report_version":3}'
    validate.close()
    db.close()


def test_history_scale_explain_uses_indexes(tmp_path: Path):
    db = Database(tmp_path / "hist.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(
        [
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="lab", name="Lab", base_topic="lab"),
        ]
    )
    old = "2026-01-01T00:00:00+00:00"
    # Bulk-load history-scale fixtures (executemany) so EXPLAIN sees real cardinality.
    repo.db.conn.executemany(
        """
        INSERT INTO metric_samples
          (network_id, ieee_address, metric_name, metric_value, sampled_at)
        VALUES ('home', 'aa', 'linkquality', 1, ?)
        """,
        [(old,)] * 10_000,
    )
    repo.db.conn.executemany(
        """
        INSERT INTO availability_changes
          (network_id, ieee_address, from_state, to_state, changed_at)
        VALUES ('home', 'aa', 'offline', 'online', ?)
        """,
        [(old,)] * 10_000,
    )
    repo.db.conn.executemany(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES (?, 'test', 'watch', 't', 's', ?)
        """,
        [(f"e{i}", old) for i in range(10_000)],
    )
    repo.db.conn.executemany(
        """
        INSERT INTO incidents (
          id, dedup_key, incident_type, lifecycle_state, severity, scope, confidence,
          title, summary, explanation, evidence_json, counter_evidence_json,
          limitations_json, opened_at, updated_at, resolved_at
        ) VALUES (
          ?, ?, 'single_device_unavailable', 'resolved', 'incident', 'device', 'high',
          't', 's', 'e', '[]', '[]', '[]', ?, ?, ?
        )
        """,
        [(f"inc-{i}", f"d{i}", old, old, old) for i in range(1_500)],
    )
    repo.db.conn.executemany(
        """
        INSERT INTO topology_snapshots
          (snapshot_id, network_id, captured_at, requested_by, status, warning_acknowledged)
        VALUES (?, ?, ?, 'test', 'complete', 0)
        """,
        [(f"snap-{i}", "home" if i % 2 == 0 else "lab", old) for i in range(300)],
    )
    repo.db.conn.executemany(
        """
        INSERT INTO health_snapshots
          (network_id, primary_health, severity, confidence, captured_at)
        VALUES ('home', 'healthy', 'healthy', 'high', ?)
        """,
        [(old,)] * 2_000,
    )
    repo.db.conn.commit()

    def _plan(sql: str, params: tuple = ()) -> str:
        rows = repo.db.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
        return "\n".join(" | ".join(str(p) for p in row) for row in rows).lower()

    events = "\n".join(
        repo.maintenance.explain_retention_select("events", "occurred_at", "id")
    ).lower()
    metrics = "\n".join(
        repo.maintenance.explain_retention_select("metric_samples", "sampled_at", "id")
    ).lower()
    availability = "\n".join(
        repo.maintenance.explain_retention_select(
            "availability_changes", "changed_at", "id"
        )
    ).lower()
    incidents = _plan(
        """
        SELECT id FROM incidents
        WHERE lifecycle_state = 'resolved'
          AND resolved_at IS NOT NULL
          AND unixepoch(resolved_at, 'subsec') <= unixepoch(?, 'subsec')
          AND retention_instant(resolved_at) < retention_instant(?)
        ORDER BY retention_instant(resolved_at) ASC, id ASC
        LIMIT 500
        """,
        (old, old),
    )
    event_ref = "\n".join(repo.maintenance.explain_incident_event_null_select()).lower()
    topology_count = "\n".join(repo.maintenance.explain_topology_count_cap_select()).lower()
    abandoned = "\n".join(repo.maintenance.explain_abandoned_pending_select()).lower()

    def _uses_index(plan: str, *names: str) -> bool:
        return any(name in plan for name in names) or "using index" in plan or "using covering index" in plan

    assert _uses_index(events, "idx_events_retention")
    assert "scan events" not in events
    assert _uses_index(metrics, "idx_metric_samples_retention")
    assert _uses_index(availability, "idx_availability_changes_retention")
    assert _uses_index(incidents, "idx_incidents_resolved_retention")
    assert _uses_index(event_ref, "idx_events_incident_id", "idx_events_incident")
    assert "topology" in topology_count
    assert "topology_snapshots" in abandoned
