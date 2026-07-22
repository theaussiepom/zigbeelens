"""Runtime SQLite 3.34.1 smoke for migration 013 and Phase 7A production queries.

Host developers typically run newer SQLite; this module skips unless the linked
library is exactly 3.34.1. Use ``scripts/smoke-sqlite-3.34.1.sh`` for the Docker
proof against ``python:3.12-slim-bullseye`` (SQLite 3.34.1).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from zigbeelens.db.connection import Database
from zigbeelens.storage.incident_collection import build_incident_collection_query
from zigbeelens.storage.repository import Repository

pytestmark = pytest.mark.skipif(
    sqlite3.sqlite_version_info != (3, 34, 1),
    reason="requires linked SQLite 3.34.1 (see scripts/smoke-sqlite-3.34.1.sh)",
)


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


def test_sqlite_3_34_1_migration_013_and_production_queries(tmp_path: Path):
    assert sqlite3.sqlite_version == "3.34.1"
    db = Database(tmp_path / "smoke3341.sqlite")
    _apply_migrations_through(db, 12)
    assert db.migration_version == 12
    assert db.migrate() == 13
    assert db.migrate() == 13
    assert db.conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []

    indexes = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for name in (
        "idx_incidents_recent_order",
        "idx_topology_snapshots_latest_complete",
        "idx_metric_samples_device_time",
        "idx_availability_changes_offline_since",
        "idx_topology_links_snapshot_target",
    ):
        assert name in indexes
    assert "idx_topology_links_snapshot_source" not in indexes

    repo = Repository(db)
    db.conn.execute(
        """
        INSERT INTO networks (id, name, base_topic, bridge_state, created_at, updated_at)
        VALUES ('home', 'Home', 'z2m/home', 'online', '2026-07-15T12:00:00+00:00',
                '2026-07-15T12:00:00+00:00')
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
    for i in range(3):
        db.conn.execute(
            """
            INSERT INTO topology_snapshots (
                snapshot_id, network_id, captured_at, requested_by, status,
                router_count, end_device_count, link_count, warning_acknowledged, error
            ) VALUES (?, 'home', ?, 'manual', 'complete', 0, 0, 0, 0, NULL)
            """,
            (f"snap-{i}", f"2026-07-15T1{i}:00:00+00:00"),
        )
    db.conn.execute(
        """
        INSERT INTO metric_samples (
            network_id, ieee_address, metric_name, metric_value, sampled_at
        ) VALUES ('home', '0xAA', 'linkquality', 100, '2026-07-15T12:00:00+00:00')
        """
    )
    db.conn.execute(
        """
        INSERT INTO availability_changes (
            network_id, ieee_address, from_state, to_state, changed_at
        ) VALUES ('home', '0xAA', 'online', 'offline', '2026-07-15T11:30:00+00:00')
        """
    )
    db.conn.commit()

    query = build_incident_collection_query(order="recent", limit=50)
    first_sql, first_params = repo._incident_collection_page_sql(query, include_cursor=False)
    assert db.conn.execute(first_sql, first_params).fetchall()
    # Cursor continuation path (same SQL builder with include_cursor).
    from zigbeelens.storage.incident_collection import (
        IncidentCollectionCursor,
        encode_incident_collection_cursor,
    )

    token = encode_incident_collection_cursor(
        IncidentCollectionCursor(
            version=2,
            updated_at="2026-07-15T12:00:00+00:00",
            incident_id="inc-1",
            filter_signature=query.filter_signature,
            lifecycle_rank=None,
        )
    )
    query2 = build_incident_collection_query(order="recent", limit=50, cursor=token)
    cur_sql, cur_params = repo._incident_collection_page_sql(query2, include_cursor=True)
    db.conn.execute(cur_sql, cur_params).fetchall()

    bulk = repo.get_latest_topology_snapshots_for_networks(["home"])
    assert bulk["home"] is not None
    assert repo.get_latest_topology_snapshot("home") is not None
    assert repo.list_metric_samples("home", "0xAA", limit=20)
    assert repo.list_availability_offline_transitions_since(
        "home", since_iso="2026-07-01T00:00:00+00:00"
    )

    print(
        f"sqlite3.sqlite_version={sqlite3.sqlite_version} "
        f"migration_version={db.migration_version} smoke=ok"
    )
    db.close()
