from pathlib import Path

from zigbeelens.config.models import AppConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def test_migrations_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrate.sqlite"
    db = Database(db_path)
    version1 = db.migrate()
    version2 = db.migrate()
    assert version1 == version2 == 9

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
        "reports",
        "schema_migrations",
    ]:
        assert name in tables
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
    assert db.migrate() == 9
    indexes = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_events_device" in indexes
    assert "idx_events_incident" in indexes
    assert "idx_incident_devices_device" in indexes
    db.close()
