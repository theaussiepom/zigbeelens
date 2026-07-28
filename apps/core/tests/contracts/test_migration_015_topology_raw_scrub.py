"""Migration 015 — retain typed topology facts without original map dictionaries."""

from __future__ import annotations

import json
from pathlib import Path

from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository
from zigbeelens.topology.parser import parse_networkmap_payload


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


def test_migration_015_scrubs_raw_topology_only(tmp_path: Path) -> None:
    db = Database(tmp_path / "v14_topology.sqlite")
    _apply_migrations_through(db, 14)
    assert db.migration_version == 14

    redacted_snapshot = json.dumps(
        {
            "nodes": {"0x01": {"password": "***", "type": "Coordinator"}},
            "safe_evidence": "retain-me",
        },
        separators=(",", ":"),
    )
    db.conn.execute(
        "INSERT INTO networks (id, name, base_topic) VALUES ('home', 'Home', 'z2m/home')"
    )
    db.conn.execute(
        """
        INSERT INTO topology_snapshots (
            snapshot_id, network_id, captured_at, requested_by, status,
            raw_redacted_json, parsed_json, router_count, end_device_count,
            link_count, warning_acknowledged, error
        ) VALUES (
            'snap-unsafe', 'home', '2026-07-26T12:00:00+00:00', 'manual', 'complete',
            ?, ?, 2, 3, 1, 1, NULL
        )
        """,
        (
            redacted_snapshot,
            json.dumps(
                {
                    "router_count": 2,
                    "end_device_count": 3,
                    "link_count": 1,
                    "password": "snapshot-secret",
                    "original": {"token": "nested-secret"},
                }
            ),
        ),
    )
    db.conn.execute(
        """
        INSERT INTO topology_snapshots (
            snapshot_id, network_id, captured_at, requested_by, status,
            raw_redacted_json, parsed_json
        ) VALUES (
            'snap-pending', 'home', '2026-07-26T12:01:00+00:00',
            'startup_scan', 'pending', '{"safe":"pending"}', NULL
        )
        """
    )
    db.conn.execute(
        """
        INSERT INTO topology_nodes (
            snapshot_id, network_id, ieee_address, friendly_name, node_type,
            depth, lqi, raw_json
        ) VALUES (
            'snap-unsafe', 'home', '0x01', 'Coordinator', 'Coordinator',
            0, 255, '{"password":"node-secret","vendor":{"token":"nested-secret"}}'
        )
        """
    )
    db.conn.execute(
        """
        INSERT INTO topology_links (
            snapshot_id, network_id, source_ieee, target_ieee, source_type,
            target_type, linkquality, depth, relationship, raw_json, route_count
        ) VALUES (
            'snap-unsafe', 'home', '0x01', '0x02', 'Coordinator',
            'EndDevice', 123, 1, 'Child',
            '{"api_key":"link-secret","routes":[{"install_code":"nested-secret"}]}',
            4
        )
        """
    )
    db.conn.commit()

    typed_snapshot_before = tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count,
                   warning_acknowledged, error
            FROM topology_snapshots
            WHERE snapshot_id = 'snap-unsafe'
            """
        ).fetchone()
    )
    typed_node_before = tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, ieee_address, friendly_name,
                   node_type, depth, lqi
            FROM topology_nodes
            """
        ).fetchone()
    )
    typed_link_before = tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, source_ieee, target_ieee,
                   source_type, target_type, linkquality, depth, relationship,
                   route_count
            FROM topology_links
            """
        ).fetchone()
    )

    assert db.migrate() == 15
    assert db.migrate() == 15

    snapshot = db.conn.execute(
        """
        SELECT raw_redacted_json, parsed_json
        FROM topology_snapshots
        WHERE snapshot_id = 'snap-unsafe'
        """
    ).fetchone()
    assert snapshot["raw_redacted_json"] == redacted_snapshot
    assert snapshot["parsed_json"] is None
    pending = db.conn.execute(
        """
        SELECT raw_redacted_json, parsed_json
        FROM topology_snapshots
        WHERE snapshot_id = 'snap-pending'
        """
    ).fetchone()
    assert pending["raw_redacted_json"] == '{"safe":"pending"}'
    assert pending["parsed_json"] is None
    assert {
        row[0] for row in db.conn.execute("SELECT raw_json FROM topology_nodes")
    } == {"{}"}
    assert {
        row[0] for row in db.conn.execute("SELECT raw_json FROM topology_links")
    } == {"{}"}
    assert tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count,
                   warning_acknowledged, error
            FROM topology_snapshots
            WHERE snapshot_id = 'snap-unsafe'
            """
        ).fetchone()
    ) == typed_snapshot_before
    assert tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, ieee_address, friendly_name,
                   node_type, depth, lqi
            FROM topology_nodes
            """
        ).fetchone()
    ) == typed_node_before
    assert tuple(
        db.conn.execute(
            """
            SELECT snapshot_id, network_id, source_ieee, target_ieee,
                   source_type, target_type, linkquality, depth, relationship,
                   route_count
            FROM topology_links
            """
        ).fetchone()
    ) == typed_link_before
    assert db.conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()


def test_new_topology_writes_do_not_retain_original_node_or_link_dicts(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "new_topology.sqlite")
    assert db.migrate() == 15
    repo = Repository(db)
    db.conn.execute(
        "INSERT INTO networks (id, name, base_topic) VALUES ('home', 'Home', 'z2m/home')"
    )
    repo.create_topology_snapshot(
        snapshot_id="snap-new",
        network_id="home",
        requested_by="test",
        status="pending",
    )
    parsed = parse_networkmap_payload(
        {
            "nodes": {
                "0x01": {
                    "type": "Coordinator",
                    "friendly_name": "Coordinator",
                    "password": "node-secret",
                    "vendor": {"token": "nested-node-secret"},
                },
                "0x02": {"type": "EndDevice", "friendly_name": "Sensor"},
            },
            "links": [
                {
                    "source": "0x01",
                    "target": "0x02",
                    "linkquality": 123,
                    "api_key": "link-secret",
                    "routes": [
                        {
                            "destinationAddress": 42,
                            "install_code": "nested-link-secret",
                        }
                    ],
                }
            ],
        }
    )

    assert all(not hasattr(node, "raw_json") for node in parsed.nodes)
    assert all(not hasattr(link, "raw_json") for link in parsed.links)
    repo.store_topology_parsed("snap-new", "home", parsed, status="complete")

    assert {
        row[0] for row in db.conn.execute("SELECT raw_json FROM topology_nodes")
    } == {"{}"}
    assert {
        row[0] for row in db.conn.execute("SELECT raw_json FROM topology_links")
    } == {"{}"}
    snapshot = db.conn.execute(
        """
        SELECT raw_redacted_json, parsed_json, router_count,
               end_device_count, link_count
        FROM topology_snapshots
        WHERE snapshot_id = 'snap-new'
        """
    ).fetchone()
    assert snapshot["parsed_json"] is None
    assert (
        snapshot["router_count"],
        snapshot["end_device_count"],
        snapshot["link_count"],
    ) == (1, 1, 1)
    raw_redacted = snapshot["raw_redacted_json"]
    for secret in (
        "node-secret",
        "nested-node-secret",
        "link-secret",
        "nested-link-secret",
    ):
        assert secret not in raw_redacted
    assert json.loads(raw_redacted)["nodes"]["0x01"]["password"] == "***"
    db.close()
