"""AvailabilityRepository and MetricRepository access-layer tests."""

from __future__ import annotations

from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "availability-metric-access.sqlite")
    db.migrate()
    repo = Repository(db)
    cfg = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "availability-metric-access.sqlite")),
    )
    repo.sync_networks(cfg.networks)
    repo.upsert_device(
        network_id="home",
        ieee_address="0x01",
        friendly_name="Sensor",
        device_type="EndDevice",
        power_source="Battery",
    )
    return repo


def test_availability_repository_delegates_insert_and_list_since(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.availability.insert_availability_change("home", "0x01", "online", "offline")

    via_repo = repo.list_availability_changes_since("home", "1970-01-01T00:00:00+00:00")
    via_access = repo.availability.list_availability_changes_since(
        "home", "1970-01-01T00:00:00+00:00"
    )

    assert via_access == via_repo
    assert len(via_access) == 1
    assert via_access[0]["to_state"] == "offline"


def test_availability_repository_delegates_earliest_and_per_device_list(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.availability.insert_availability_change("home", "0x01", "online", "offline")

    assert (
        repo.availability.get_earliest_availability_change_at("home")
        == repo.get_earliest_availability_change_at("home")
    )
    assert repo.availability.list_availability_changes("home", "0x01") == repo.list_availability_changes(
        "home", "0x01"
    )


def test_availability_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.availability is repo.availability


def test_metric_repository_delegates_insert_and_list(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.metrics.insert_metric_sample("home", "0x01", "linkquality", 120.0)
    repo.metrics.insert_metric_sample("home", "0x01", "battery", 85.0)

    via_repo = repo.list_metric_samples("home", "0x01")
    via_access = repo.metrics.list_metric_samples("home", "0x01")

    assert via_access == via_repo
    assert len(via_access) == 2


def test_metric_repository_cached_on_repository_instance(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.metrics is repo.metrics
