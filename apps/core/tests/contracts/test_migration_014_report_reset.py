"""Migration 014 — pre-release report table reset to ReportDetailV3-only."""

from __future__ import annotations

import json
from pathlib import Path

from zigbeelens.db.connection import Database
from zigbeelens.schemas import ReportDetailV3, ReportRequest
from zigbeelens.services.report_storage import load_stored_report_envelope
from zigbeelens.services.reports import generate_report, store_report
from zigbeelens.storage.repository import Repository
from zigbeelens.config.models import AppConfig
from zigbeelens.services.data_service import DataService


def _apply_migrations_through(db: Database, through_version: int) -> None:
    db.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied = {
        int(row[0]) for row in db.conn.execute("SELECT version FROM schema_migrations")
    }
    for version, sql in db._load_migrations():
        if version > through_version or version in applied:
            continue
        db.conn.executescript(sql)
        db.conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (version,),
        )
        applied.add(version)
    db.conn.commit()
    db.migration_version = max(applied, default=0)


def _seed_non_report_rows(db: Database) -> dict[str, object]:
    repo = Repository(db)
    db.conn.execute(
        """
        INSERT INTO networks (id, name, base_topic, bridge_state, created_at, updated_at)
        VALUES ('home', 'Home', 'z2m/home', 'online', '2026-07-15T12:00:00+00:00',
                '2026-07-15T12:00:00+00:00')
        """
    )
    db.conn.execute(
        """
        INSERT INTO devices (
            network_id, ieee_address, friendly_name, device_type, power_source, interview_state
        ) VALUES ('home', '0xAA', 'Sensor', 'EndDevice', 'Battery', 'successful')
        """
    )
    db.conn.execute(
        """
        INSERT INTO device_current_state (network_id, ieee_address, availability)
        VALUES ('home', '0xAA', 'online')
        """
    )
    repo.insert_incident(
        incident_id="inc-1",
        dedup_key="device_offline:home:0xAA",
        incident_type="device_offline",
        lifecycle_state="open",
        severity="incident",
        scope="device",
        confidence="medium",
        title="t",
        summary="s",
        explanation="e",
        evidence=[],
        counter_evidence=[],
        limitations=[],
        opened_at="2026-07-15T11:00:00+00:00",
        updated_at="2026-07-15T12:00:00+00:00",
    )
    db.conn.execute(
        """
        INSERT INTO events (
            id, network_id, ieee_address, event_type, severity, title, summary,
            payload_json, occurred_at
        ) VALUES (
            'evt-1', 'home', '0xAA', 'availability', 'info', 'online', 'online',
            '{}', '2026-07-15T12:00:00+00:00'
        )
        """
    )
    db.conn.execute(
        """
        INSERT INTO topology_snapshots (
            snapshot_id, network_id, captured_at, requested_by, status,
            router_count, end_device_count, link_count, warning_acknowledged, error
        ) VALUES (
            'snap-1', 'home', '2026-07-15T12:00:00+00:00', 'manual', 'complete',
            0, 1, 0, 0, NULL
        )
        """
    )
    db.conn.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ('demo_setting', '{"ok": true}')
        """
    )
    db.conn.commit()
    return {
        "networks": db.conn.execute("SELECT * FROM networks ORDER BY id").fetchall(),
        "devices": db.conn.execute(
            "SELECT * FROM devices ORDER BY network_id, ieee_address"
        ).fetchall(),
        "device_current_state": db.conn.execute(
            "SELECT * FROM device_current_state ORDER BY network_id, ieee_address"
        ).fetchall(),
        "incidents": db.conn.execute("SELECT * FROM incidents ORDER BY id").fetchall(),
        "events": db.conn.execute("SELECT * FROM events ORDER BY id").fetchall(),
        "topology_snapshots": db.conn.execute(
            "SELECT * FROM topology_snapshots ORDER BY snapshot_id"
        ).fetchall(),
        "settings": db.conn.execute("SELECT * FROM settings ORDER BY key").fetchall(),
    }


def _insert_report(db: Database, report_id: str, body: object) -> None:
    raw = body if isinstance(body, str) else json.dumps(body)
    db.conn.execute(
        """
        INSERT INTO reports (
            id, generated_at, format, scope, redaction_profile, summary,
            body_json, body_markdown, redaction_json, metadata_json
        ) VALUES (?, '2026-07-15T12:00:00+00:00', 'json', 'full', 'standard', 's',
                  ?, '', '{}', '{}')
        """,
        (report_id, raw),
    )


def test_migration_014_deletes_all_reports_and_preserves_other_data(tmp_path: Path):
    db = Database(tmp_path / "v13_reset.sqlite")
    _apply_migrations_through(db, 13)
    assert db.migration_version == 13
    before = _seed_non_report_rows(db)

    seeded_bodies = {
        "missing": {"id": "missing"},
        "v1": {"id": "v1", "report_version": 1},
        "v2": {"id": "v2", "report_version": 2},
        "s1": {"id": "s1", "report_version": "1"},
        "s2": {"id": "s2", "report_version": "2"},
        "v3": {"id": "v3", "report_version": 3, "product": "ZigbeeLens"},
        "s3": {"id": "s3", "report_version": "3"},
        "bool": {"id": "bool", "report_version": True},
        "float": {"id": "float", "report_version": 3.0},
        "nullbody": "null",
        "malformed": "{not-json",
    }
    for report_id, body in seeded_bodies.items():
        _insert_report(db, report_id, body)
    db.conn.commit()
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == len(
        seeded_bodies
    )

    assert db.migrate() == 14
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
    after = {
        "networks": db.conn.execute("SELECT * FROM networks ORDER BY id").fetchall(),
        "devices": db.conn.execute(
            "SELECT * FROM devices ORDER BY network_id, ieee_address"
        ).fetchall(),
        "device_current_state": db.conn.execute(
            "SELECT * FROM device_current_state ORDER BY network_id, ieee_address"
        ).fetchall(),
        "incidents": db.conn.execute("SELECT * FROM incidents ORDER BY id").fetchall(),
        "events": db.conn.execute("SELECT * FROM events ORDER BY id").fetchall(),
        "topology_snapshots": db.conn.execute(
            "SELECT * FROM topology_snapshots ORDER BY snapshot_id"
        ).fetchall(),
        "settings": db.conn.execute("SELECT * FROM settings ORDER BY key").fetchall(),
    }
    assert after == before
    assert db.conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_install_and_idempotent_create_v3(tmp_path: Path):
    db = Database(tmp_path / "fresh14.sqlite")
    assert db.migrate() == 14
    assert db.migrate() == 14
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0

    repo = Repository(db)
    config = AppConfig()
    config.mode.mock = True
    data = DataService(config, repo)
    detail = generate_report(
        data=data,
        config=config,
        reporting=config.reporting,
        collector={},
        request=ReportRequest(),
        scenario="bridge_offline",
        repo=repo,
    )
    assert isinstance(detail, ReportDetailV3)
    assert type(detail.report_version) is int
    assert detail.report_version == 3
    row = store_report(repo, detail, ReportRequest())
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1

    # Second normal migrate must not delete the new report.
    assert db.migrate() == 14
    assert db.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
    envelope = load_stored_report_envelope(repo.reports.get_report(row.id))
    assert envelope is not None
    assert envelope.body.report_version == 3
