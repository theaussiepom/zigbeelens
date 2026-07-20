"""Track 6 pure retention policy, timestamps, indexes, and preview."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zigbeelens.config.models import AppConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.retention_policy import (
    NEVER_AGE_PURGE_TABLES,
    StorageRetentionPolicy,
    build_maintenance_plan,
    compute_cutoffs,
)
from zigbeelens.storage.repository import Repository


REF = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_storage_config_defaults_and_legacy_only_retention_days():
    legacy = StorageConfig.model_validate({"path": "./data/x.sqlite", "retention_days": 7})
    assert legacy.retention_days == 7
    assert legacy.resolved_incident_retention_days == 90
    assert legacy.report_retention_days is None
    assert legacy.maintenance_interval_hours == 24


def test_storage_config_rejects_zero_and_bool():
    with pytest.raises(Exception):
        StorageConfig.model_validate({"path": "x", "retention_days": 0})
    with pytest.raises(Exception):
        StorageConfig.model_validate({"path": "x", "retention_days": True})
    with pytest.raises(Exception):
        StorageConfig.model_validate({"path": "x", "report_retention_days": 0})


def test_cutoffs_strictly_older_than_and_null_policies():
    policy = StorageRetentionPolicy(
        telemetry_retention_days=7,
        resolved_incident_retention_days=90,
        report_retention_days=None,
        maintenance_interval_hours=24,
        topology_max_snapshots_per_network=30,
    )
    cutoffs = compute_cutoffs(policy, REF)
    assert cutoffs.telemetry == datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
    assert cutoffs.resolved_incident == datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert cutoffs.report is None

    disabled = StorageRetentionPolicy(
        telemetry_retention_days=7,
        resolved_incident_retention_days=None,
        report_retention_days=30,
        maintenance_interval_hours=24,
        topology_max_snapshots_per_network=30,
    )
    cut2 = compute_cutoffs(disabled, REF)
    assert cut2.resolved_incident is None
    assert cut2.report == datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_never_age_purge_tables_documented():
    assert "networks" in NEVER_AGE_PURGE_TABLES
    assert "devices" in NEVER_AGE_PURGE_TABLES
    assert "device_current_state" in NEVER_AGE_PURGE_TABLES
    assert "reports" not in NEVER_AGE_PURGE_TABLES


def test_julianday_timestamp_forms_equivalent(tmp_path: Path):
    db = Database(tmp_path / "ts.sqlite")
    db.migrate()
    repo = Repository(db)
    # Four equivalent instants in different stored forms.
    forms = [
        ("evt-plus", "2026-01-01T00:00:00+00:00"),
        ("evt-z", "2026-01-01T00:00:00Z"),
        ("evt-space", "2026-01-01 00:00:00"),
        ("evt-offset", "2026-01-01T10:00:00+10:00"),
    ]
    for event_id, ts in forms:
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (event_id, ts),
        )
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-bad', 'test', 'watch', 't', 's', 'not-a-timestamp')
        """
    )
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
        VALUES ('evt-new', 'test', 'watch', 't', 's', ?)
        """,
        ("2026-07-19T00:00:00+00:00",),
    )
    repo.db.conn.commit()

    policy = StorageRetentionPolicy.from_storage(
        StorageConfig(path=str(tmp_path / "ts.sqlite"), retention_days=7),
    )
    plan = build_maintenance_plan(policy, REF)
    preview = repo.maintenance.preview_retention(plan)
    # Four equivalent old rows eligible; malformed retained/counted; new retained.
    assert preview.by_category["events"].eligible == 4
    assert preview.by_category["events"].malformed_timestamps == 1

    with repo.transaction():
        deleted = repo.maintenance.purge_telemetry_batch(
            "events",
            "occurred_at",
            "id",
            plan.cutoffs.telemetry_iso(),
            limit=500,
        )
    assert deleted == 4
    remaining = {
        row[0] for row in repo.db.conn.execute("SELECT id FROM events").fetchall()
    }
    assert remaining == {"evt-bad", "evt-new"}


def test_preview_reports_default_not_eligible(tmp_path: Path):
    db = Database(tmp_path / "rep.sqlite")
    db.migrate()
    repo = Repository(db)
    old = (REF - timedelta(days=30)).isoformat()
    repo.db.conn.execute(
        """
        INSERT INTO reports (id, format, redaction_json, summary, generated_at)
        VALUES ('rep-old', 'json', '{}', 'Old', ?)
        """,
        (old,),
    )
    repo.db.conn.commit()
    policy = StorageRetentionPolicy.from_config(
        AppConfig(storage=StorageConfig(path=str(tmp_path / "rep.sqlite")))
    )
    plan = build_maintenance_plan(policy, REF)
    preview = repo.maintenance.preview_retention(plan)
    assert preview.by_category["reports"].eligible == 0


def test_preview_and_delete_resolved_incidents(tmp_path: Path):
    db = Database(tmp_path / "inc.sqlite")
    db.migrate()
    repo = Repository(db)
    old = (REF - timedelta(days=120)).isoformat()
    recent = (REF - timedelta(days=10)).isoformat()
    now = REF.isoformat()
    for incident_id, resolved_at, state in [
        ("inc-open", None, "open"),
        ("inc-watch", None, "watching"),
        ("inc-old", old, "resolved"),
        ("inc-recent", recent, "resolved"),
        ("inc-null-resolved", None, "resolved"),
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
            opened_at=resolved_at or now,
            updated_at=resolved_at or now,
        )
        if state == "resolved" and resolved_at is not None:
            repo.update_incident(
                incident_id=incident_id,
                resolved_at=resolved_at,
                updated_at=resolved_at,
            )
    # Surviving event referencing old resolved incident.
    repo.db.conn.execute(
        """
        INSERT INTO events (id, event_type, severity, title, summary, occurred_at, incident_id)
        VALUES ('evt-keep', 'test', 'watch', 't', 's', ?, 'inc-old')
        """,
        (now,),
    )
    repo.db.conn.commit()

    policy = StorageRetentionPolicy.from_storage(
        StorageConfig(path=str(tmp_path / "inc.sqlite"), retention_days=7)
    )
    plan = build_maintenance_plan(policy, REF)
    preview = repo.maintenance.preview_retention(plan)
    assert preview.by_category["incidents_resolved"].eligible == 1

    with repo.transaction():
        deleted = repo.maintenance.purge_resolved_incident_batch(
            plan.cutoffs.resolved_incident_iso(),  # type: ignore[arg-type]
            limit=500,
        )
    assert deleted == 1
    ids = {row["id"] for row in repo.list_incidents()}
    assert "inc-old" not in ids
    assert {"inc-open", "inc-watch", "inc-recent", "inc-null-resolved"} <= ids
    event_ref = repo.db.conn.execute(
        "SELECT incident_id FROM events WHERE id = 'evt-keep'"
    ).fetchone()[0]
    assert event_ref is None


def test_migration_012_and_explain_uses_index(tmp_path: Path):
    db = Database(tmp_path / "idx.sqlite")
    version = db.migrate()
    assert version >= 12
    repo = Repository(db)
    # Seed enough rows so planner prefers the retention index when present.
    for i in range(200):
        repo.db.conn.execute(
            """
            INSERT INTO events (id, event_type, severity, title, summary, occurred_at)
            VALUES (?, 'test', 'watch', 't', 's', ?)
            """,
            (f"e{i}", "2026-01-01T00:00:00+00:00"),
        )
    repo.db.conn.commit()
    plan_lines = "\n".join(
        repo.maintenance.explain_retention_select("events", "occurred_at", "id")
    ).lower()
    assert "idx_events_retention" in plan_lines or "using index" in plan_lines


def test_topology_count_cap_ignores_pending(tmp_path: Path):
    from zigbeelens.config.models import NetworkConfig

    db = Database(tmp_path / "top.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    base = REF - timedelta(days=1)
    # Newest first by captured_at: snap-0 newest complete, snap-2 oldest complete,
    # snap-3 pending must never count toward the cap.
    for i, status in enumerate(["complete", "complete", "complete", "pending"]):
        captured = (base - timedelta(hours=i)).isoformat()
        repo.db.conn.execute(
            """
            INSERT INTO topology_snapshots (
                snapshot_id, network_id, captured_at, requested_by, status
            ) VALUES (?, 'home', ?, 'test', ?)
            """,
            (f"snap-{i}", captured, status),
        )
    repo.db.conn.commit()
    deleted = repo.maintenance.enforce_topology_count_retention("home", 2)
    assert deleted == 1
    rows = repo.db.conn.execute(
        "SELECT snapshot_id, status FROM topology_snapshots ORDER BY snapshot_id"
    ).fetchall()
    statuses = {row["snapshot_id"]: row["status"] for row in rows}
    assert statuses["snap-3"] == "pending"
    assert len([s for s in statuses.values() if s == "complete"]) == 2
    assert len(statuses) == 3
