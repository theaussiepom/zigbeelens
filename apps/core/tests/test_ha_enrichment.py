"""Home Assistant enrichment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.enrichment.ha import apply_ha_enrichment, area_cluster_for_devices, clear_ha_enrichment
from zigbeelens.storage.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "ha.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    repo.upsert_device(
        network_id="home",
        ieee_address="0x00124b0024abcd01",
        friendly_name="Laundry Plug",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repo.upsert_device(
        network_id="home",
        ieee_address="0x00124b0024abcd02",
        friendly_name="Lamp",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    return repo


def test_match_by_ieee_high_confidence(tmp_path: Path):
    repo = _repo(tmp_path)
    result = apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "network_id": "home",
                    "ieee_address": "0x00124b0024abcd01",
                    "ha_device_name": "Laundry Plug",
                    "area_name": "Laundry",
                }
            ]
        },
    )
    assert result["matched_devices"] == 1
    row = repo.get_ha_device_enrichment("home", "0x00124b0024abcd01")
    assert row["match_confidence"] == "high"
    assert row["area_name"] == "Laundry"


def test_rejects_oversized_payload(tmp_path: Path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        apply_ha_enrichment(repo, {"devices": [{} for _ in range(6000)]})


def test_area_cluster_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "network_id": "home",
                    "ieee_address": "0x00124b0024abcd01",
                    "area_name": "Laundry",
                },
                {
                    "network_id": "home",
                    "ieee_address": "0x00124b0024abcd02",
                    "area_name": "Laundry",
                },
            ]
        },
    )
    cluster = area_cluster_for_devices(
        repo, "home", ["0x00124b0024abcd01", "0x00124b0024abcd02"]
    )
    assert cluster["matched"] == 2
    assert cluster["area_count"] == 1


def test_clear_enrichment(tmp_path: Path):
    repo = _repo(tmp_path)
    apply_ha_enrichment(
        repo,
        {"devices": [{"network_id": "home", "ieee_address": "0x00124b0024abcd01", "area_name": "X"}]},
    )
    clear_ha_enrichment(repo)
    status = repo.get_ha_enrichment_status()
    assert status["enabled"] == 0


def test_match_by_ieee_without_network_id(tmp_path: Path):
    repo = _repo(tmp_path)
    result = apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "ieee_address": "0x00124b0024abcd01",
                    "ha_device_name": "Laundry Plug",
                    "area_name": "Laundry",
                }
            ]
        },
    )
    assert result["matched_devices"] == 1
    row = repo.get_ha_device_enrichment("home", "0x00124b0024abcd01")
    assert row["match_confidence"] == "high"


def test_match_by_ieee_without_current_state_row(tmp_path: Path):
    repo = _repo(tmp_path)
    result = apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "ieee_address": "0x00124b0024abcd02",
                    "area_name": "Office",
                }
            ]
        },
    )
    assert result["matched_devices"] == 1
    row = repo.get_ha_device_enrichment("home", "0x00124b0024abcd02")
    assert row["match_confidence"] == "high"


def test_find_devices_by_ieee_multi_network(tmp_path: Path):
    db = Database(tmp_path / "multi.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(
        [
            NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt"),
            NetworkConfig(id="home2", name="Home 2", base_topic="zigbee2mqtt-home2"),
        ]
    )
    ieee = "0x00124b0024abcd99"
    for network_id in ("home", "home2"):
        repo.upsert_device(
            network_id=network_id,
            ieee_address=ieee,
            friendly_name=f"Device {network_id}",
            device_type="Router",
            power_source="Mains",
            interview_state="successful",
        )
    matches = repo.find_devices_by_ieee(ieee)
    assert len(matches) == 2
    assert {m.network_id for m in matches} == {"home", "home2"}
