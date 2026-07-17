from pathlib import Path

from zigbeelens.config.models import AppConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def _apply_migrations_through(db: Database, through_version: int) -> None:
    """Apply packaged SQL migrations up to through_version only."""
    db.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied = {int(row[0]) for row in db.conn.execute("SELECT version FROM schema_migrations")}
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


def test_migrations_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrate.sqlite"
    db = Database(db_path)
    version1 = db.migrate()
    version2 = db.migrate()
    assert version1 == version2 == 11

    tables = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for name in [
        "networks",
        "devices",
        "events",
        "incidents",
        "incident_networks",
        "reports",
        "schema_migrations",
    ]:
        assert name in tables
    db.close()


def test_upgrade_v10_to_v11_incident_networks_backfill(tmp_path: Path):
    """Real schema-version-10 → 11 upgrade proves exact identity backfill."""
    db = Database(tmp_path / "v10_upgrade.sqlite")
    _apply_migrations_through(db, 10)
    assert db.migration_version == 10
    tables = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "incident_networks" not in tables

    # Prefix-prone configured networks.
    for network_id, name, topic in (
        ("home", "Home", "zigbee2mqtt"),
        ("home2", "Home 2", "zigbee2mqtt-home2"),
        ("office", "Office", "z2m-office"),
    ):
        db.conn.execute(
            "INSERT INTO networks (id, name, base_topic) VALUES (?, ?, ?)",
            (network_id, name, topic),
        )
    db.conn.execute(
        """
        INSERT INTO devices (
            network_id, ieee_address, friendly_name, device_type, power_source, interview_state
        ) VALUES
            ('home', '0xdev1', 'sensor_home', 'EndDevice', 'Battery', 'successful'),
            ('home2', '0xdev2', 'sensor_home2', 'EndDevice', 'Battery', 'successful')
        """
    )

    def _insert_incident(
        incident_id: str,
        *,
        incident_type: str,
        dedup_key: str,
        title: str,
        explanation: str = "stored-interpretation",
    ) -> None:
        db.conn.execute(
            """
            INSERT INTO incidents (
                id, dedup_key, incident_type, lifecycle_state, severity, scope, confidence,
                title, summary, explanation, evidence_json, counter_evidence_json,
                limitations_json, opened_at, updated_at
            ) VALUES (?, ?, ?, 'open', 'incident', 'network', 'high',
                      ?, ?, ?, '[]', '[]', '[]',
                      '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            (incident_id, dedup_key, incident_type, title, title, explanation),
        )

    _insert_incident(
        "inc-device-home",
        incident_type="single_device_unavailable",
        dedup_key="single_device_unavailable:home:0xdev1",
        title="Device home",
    )
    db.conn.execute(
        """
        INSERT INTO incident_devices (incident_id, network_id, ieee_address, role)
        VALUES ('inc-device-home', 'home', '0xdev1', 'affected')
        """
    )
    _insert_incident(
        "inc-bridge-home",
        incident_type="bridge_offline",
        dedup_key="bridge_offline:home",
        title="Bridge home",
    )
    _insert_incident(
        "inc-multi",
        incident_type="multi_network_instability",
        dedup_key="multi_network_instability:home,home2",
        title="Multi",
    )
    _insert_incident(
        "inc-unprovable",
        incident_type="multi_network_instability",
        dedup_key="multi_network_instability:home,ghostnet",
        title="Unprovable",
        explanation="must-remain-absent",
    )
    db.conn.commit()

    before = {
        row["id"]: (
            row["lifecycle_state"],
            row["explanation"],
            row["dedup_key"],
        )
        for row in db.conn.execute(
            "SELECT id, lifecycle_state, explanation, dedup_key FROM incidents"
        )
    }

    assert db.migrate() == 11
    assert "incident_networks" in {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    def networks_for(incident_id: str) -> list[str]:
        return [
            row[0]
            for row in db.conn.execute(
                "SELECT network_id FROM incident_networks WHERE incident_id = ? ORDER BY network_id",
                (incident_id,),
            )
        ]

    assert networks_for("inc-device-home") == ["home"]
    # Exact identity — home must not prefix-match home2.
    assert networks_for("inc-bridge-home") == ["home"]
    assert networks_for("inc-multi") == ["home", "home2"]
    assert networks_for("inc-unprovable") == []

    after = {
        row["id"]: (
            row["lifecycle_state"],
            row["explanation"],
            row["dedup_key"],
        )
        for row in db.conn.execute(
            "SELECT id, lifecycle_state, explanation, dedup_key FROM incidents"
        )
    }
    assert after == before

    # Idempotent migrate + Python multi-network backfill retry path.
    assert db.migrate() == 11
    assert networks_for("inc-multi") == ["home", "home2"]
    assert networks_for("inc-unprovable") == []
    count = db.conn.execute("SELECT COUNT(*) FROM incident_networks").fetchone()[0]
    assert db.migrate() == 11
    assert db.conn.execute("SELECT COUNT(*) FROM incident_networks").fetchone()[0] == count
    db.close()


def test_sync_networks_from_config(tmp_path: Path):
    db = Database(tmp_path / "repo.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        networks=[
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="home2", name="Home 2", base_topic="zigbee2mqtt-home2"),
        ],
        storage=StorageConfig(path=str(tmp_path / "repo.sqlite")),
    )
    repo.sync_networks(config.networks)
    nets = repo.list_networks()
    assert {n.id for n in nets} == {"home", "home2"}


def test_friendly_name_not_globally_unique(tmp_path: Path):
    db = Database(tmp_path / "identity.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(
        [
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="home2", name="Home 2", base_topic="zigbee2mqtt-home2"),
        ]
    )
    db.conn.execute(
        """
        INSERT INTO devices (network_id, ieee_address, friendly_name, device_type, power_source, interview_state)
        VALUES ('home', '0x001', 'motion_sensor', 'EndDevice', 'Battery', 'successful')
        """
    )
    db.conn.execute(
        """
        INSERT INTO devices (network_id, ieee_address, friendly_name, device_type, power_source, interview_state)
        VALUES ('home2', '0x002', 'motion_sensor', 'EndDevice', 'Battery', 'successful')
        """
    )
    db.conn.commit()

    matches = repo.get_devices_by_friendly_name("motion_sensor")
    assert len(matches) == 2
    assert {m.network_id for m in matches} == {"home", "home2"}

    assert repo.get_device("home", "0x001") is not None
    assert repo.get_device("home2", "0x002") is not None
    assert repo.get_device("home", "0x002") is None
    db.close()


def test_composition_read_indexes_exist(tmp_path: Path):
    db = Database(tmp_path / "indexes.sqlite")
    assert db.migrate() == 11
    indexes = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_events_device" in indexes
    assert "idx_events_incident" in indexes
    assert "idx_incident_devices_device" in indexes
    assert "idx_incidents_collection_order" in indexes
    assert "idx_incidents_lifecycle" in indexes
    assert "idx_incident_networks_network" in indexes
    db.close()
