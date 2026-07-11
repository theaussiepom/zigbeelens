"""NetworkRepository and DeviceRepository access-layer tests."""

from __future__ import annotations

from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "network-device-access.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "network-device-access.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    return repo


def test_network_repository_delegates_get_network(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    via_repo = repo.get_network("home")
    via_access = repo.networks.get_network("home")

    assert via_access == via_repo
    assert via_access is not None
    assert via_access.name == "Home"


def test_network_repository_delegates_list_networks(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.networks.list_networks() == repo.list_networks()


def test_network_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.networks is repo.networks


def test_device_repository_delegates_list_devices(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Router",
        device_type="Router",
        power_source="Mains",
    )
    repo.upsert_device(
        network_id="home",
        ieee_address="0x02",
        friendly_name="Sensor",
        device_type="EndDevice",
        power_source="Battery",
    )

    via_repo = repo.list_devices("home")
    via_access = repo.devices.list_devices("home")

    assert via_access == via_repo
    assert len(via_access) == 2


def test_device_repository_delegates_get_device(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Router",
        device_type="Router",
        power_source="Mains",
    )

    via_repo = repo.get_device("home", "0x01")
    via_access = repo.devices.get_device("home", "0x01")

    assert via_access == via_repo
    assert via_access is not None
    assert via_access.friendly_name == "Router"


def test_device_repository_delegates_counts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Router",
        device_type="Router",
        power_source="Mains",
    )

    assert repo.devices.count_devices() == repo.count_devices()
    assert repo.devices.count_devices_for_network("home") == repo.count_devices_for_network("home")


def test_device_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.devices is repo.devices
