"""Exact Home Assistant enrichment contract and replacement tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.enrichment import ha as ha_module
from zigbeelens.enrichment.ha import (
    apply_ha_enrichment,
    area_cluster_for_devices,
    clear_ha_enrichment,
)
from zigbeelens.schemas import (
    HOME_ASSISTANT_ENRICHMENT_CONTRACT_VERSION,
    HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES,
    HomeAssistantEnrichmentRequestV1,
    HomeAssistantEnrichmentResultV1,
)
from zigbeelens.storage.repository import Repository

IEEE_1 = "0x00124b0024abcd01"
IEEE_2 = "0x00124b0024abcd02"
IEEE_MISSING = "0x00124b0024abcdff"
ACCEPTED_AT = "2026-07-23T01:02:03+00:00"


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "ha.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks([NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")])
    repo.upsert_device(
        network_id="home",
        ieee_address=IEEE_1,
        friendly_name="Laundry Plug",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repo.upsert_device(
        network_id="home",
        ieee_address=IEEE_2,
        friendly_name="Lamp",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
    )
    return repo


def _device(
    *,
    network_id: str = "home",
    ieee_address: str = IEEE_1,
    ha_device_id: str = "ha-device-1",
    ha_device_name: str | None = "Laundry Plug",
    area_id: str | None = "laundry",
    area_name: str | None = "Laundry",
    entity_id: str | None = "switch.laundry_plug",
) -> dict:
    return {
        "network_id": network_id,
        "ieee_address": ieee_address,
        "ha_device_id": ha_device_id,
        "ha_device_name": ha_device_name,
        "area_id": area_id,
        "area_name": area_name,
        "entity_id": entity_id,
    }


def _request(*devices: dict) -> HomeAssistantEnrichmentRequestV1:
    return HomeAssistantEnrichmentRequestV1.model_validate(
        {
            "home_assistant_enrichment_contract_version": (
                HOME_ASSISTANT_ENRICHMENT_CONTRACT_VERSION
            ),
            "devices": list(devices),
        }
    )


def test_exact_request_schema_normalizes_strings_and_ieee():
    request = _request(
        _device(
            network_id=" home ",
            ieee_address="  0X00124B0024ABCD01 ",
            ha_device_id=" ha-device-1 ",
            ha_device_name=" Kitchen Lamp ",
            area_id=" ",
            area_name=" Kitchen ",
            entity_id=" light.kitchen ",
        )
    )
    device = request.devices[0]
    assert device.network_id == "home"
    assert device.ieee_address == IEEE_1
    assert device.ha_device_id == "ha-device-1"
    assert device.ha_device_name == "Kitchen Lamp"
    assert device.area_id is None
    assert device.area_name == "Kitchen"
    assert device.entity_id == "light.kitchen"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "home_assistant_enrichment_contract_version": True,
            "devices": [],
        },
        {
            "home_assistant_enrichment_contract_version": "1",
            "devices": [],
        },
        {
            "home_assistant_enrichment_contract_version": 2,
            "devices": [],
        },
        {
            "home_assistant_enrichment_contract_version": 1,
            "devices": [_device(ieee_address="0x1234")],
        },
        {
            "home_assistant_enrichment_contract_version": 1,
            "devices": [_device(ha_device_id=" ")],
        },
        {
            "home_assistant_enrichment_contract_version": 1,
            "devices": [{**_device(), "unexpected": "field"}],
        },
        {
            "home_assistant_enrichment_contract_version": 1,
            "devices": [_device(area_name={"nested": "object"})],
        },
        {
            "home_assistant_enrichment_contract_version": 1,
            "devices": [],
            "unexpected": "field",
        },
    ],
)
def test_exact_request_schema_rejects_malformed_or_unknown_input(payload: dict):
    with pytest.raises(ValidationError):
        HomeAssistantEnrichmentRequestV1.model_validate(payload)


def test_exact_request_schema_rejects_duplicate_normalized_identity():
    with pytest.raises(ValidationError, match="duplicate Home Assistant enrichment identity"):
        _request(
            _device(),
            _device(
                ieee_address="0X00124B0024ABCD01",
                ha_device_id="other-ha-device",
            ),
        )


@pytest.mark.parametrize(
    ("second_device", "message"),
    [
        (
            _device(
                ieee_address=IEEE_2,
                entity_id="light.lamp",
            ),
            "device registry ID",
        ),
        (
            _device(
                ieee_address=IEEE_2,
                ha_device_id="ha-device-2",
                entity_id=" switch.laundry_plug ",
            ),
            "representative entity ID",
        ),
    ],
)
def test_exact_request_schema_rejects_cross_identity_registry_ownership_conflicts(
    second_device: dict,
    message: str,
):
    with pytest.raises(ValidationError, match=message):
        _request(_device(), second_device)


def test_exact_request_schema_allows_missing_representative_entities():
    request = _request(
        _device(entity_id=None),
        _device(
            ieee_address=IEEE_2,
            ha_device_id="ha-device-2",
            entity_id=None,
        ),
    )

    assert [device.entity_id for device in request.devices] == [None, None]


def test_exact_request_schema_rejects_oversized_snapshot():
    devices = [
        _device(
            ieee_address=f"0x{index:016x}",
            ha_device_id=f"ha-{index}",
        )
        for index in range(HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES + 1)
    ]
    with pytest.raises(ValidationError):
        _request(*devices)


def test_exact_result_schema_rejects_boolean_count():
    with pytest.raises(ValidationError):
        HomeAssistantEnrichmentResultV1.model_validate(
            {
                "home_assistant_enrichment_contract_version": 1,
                "submitted": True,
                "matched": 1,
                "unmatched": 0,
                "ambiguous": 0,
                "stored": 1,
                "last_push_at": ACCEPTED_AT,
            }
        )


@pytest.mark.parametrize(
    "last_push_at",
    [
        "not-a-timestamp",
        "2026-07-23T01:02:03",
    ],
)
def test_exact_result_schema_rejects_invalid_or_naive_timestamp(last_push_at: str):
    with pytest.raises(ValidationError, match="timezone-aware ISO timestamp"):
        HomeAssistantEnrichmentResultV1.model_validate(
            {
                "home_assistant_enrichment_contract_version": 1,
                "submitted": 1,
                "matched": 1,
                "unmatched": 0,
                "ambiguous": 0,
                "stored": 1,
                "last_push_at": last_push_at,
            }
        )


def test_exact_result_schema_preserves_aware_timestamp_string():
    last_push_at = "2026-07-23T11:02:03.123456+10:00"
    result = HomeAssistantEnrichmentResultV1.model_validate(
        {
            "home_assistant_enrichment_contract_version": 1,
            "submitted": 1,
            "matched": 1,
            "unmatched": 0,
            "ambiguous": 0,
            "stored": 1,
            "last_push_at": last_push_at,
        }
    )

    assert result.last_push_at == last_push_at
    assert result.model_dump(mode="json")["last_push_at"] == last_push_at


def test_exact_match_returns_factual_counts_and_one_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: ACCEPTED_AT)
    result = apply_ha_enrichment(
        repo,
        _request(
            _device(),
            _device(
                ieee_address=IEEE_MISSING,
                ha_device_id="ha-missing",
                ha_device_name="Missing",
                entity_id="sensor.missing",
            ),
        ),
    )
    assert result.model_dump(mode="json") == {
        "home_assistant_enrichment_contract_version": 1,
        "submitted": 2,
        "matched": 1,
        "unmatched": 1,
        "ambiguous": 0,
        "stored": 1,
        "last_push_at": ACCEPTED_AT,
    }
    row = repo.get_ha_device_enrichment("home", IEEE_1)
    assert row is not None
    assert row["ha_device_id"] == "ha-device-1"
    assert row["match_confidence"] == "high"
    assert row["updated_at"] == ACCEPTED_AT
    status = repo.get_ha_enrichment_status()
    assert status["last_push_at"] == ACCEPTED_AT
    assert status["matched_devices"] == 1


def test_invalid_generated_timestamp_preserves_previous_snapshot_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: ACCEPTED_AT)
    apply_ha_enrichment(repo, _request(_device(area_name="Original")))
    before_row = repo.get_ha_device_enrichment("home", IEEE_1)
    before_status = repo.get_ha_enrichment_status()

    monkeypatch.setattr(
        ha_module,
        "utc_now_iso",
        lambda: "2026-07-23T02:00:00",
    )
    with pytest.raises(ValidationError, match="timezone-aware ISO timestamp"):
        apply_ha_enrichment(
            repo,
            _request(
                _device(
                    ieee_address=IEEE_2,
                    ha_device_id="ha-device-2",
                    entity_id="light.lamp",
                )
            ),
        )

    assert repo.get_ha_device_enrichment("home", IEEE_1) == before_row
    assert repo.get_ha_device_enrichment("home", IEEE_2) is None
    assert repo.get_ha_enrichment_status() == before_status


def test_complete_empty_snapshot_clears_previous_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: ACCEPTED_AT)
    apply_ha_enrichment(repo, _request(_device()))

    result = apply_ha_enrichment(repo, _request())

    assert result.submitted == result.matched == result.stored == 0
    assert result.unmatched == result.ambiguous == 0
    assert repo.get_ha_device_enrichment("home", IEEE_1) is None
    status = repo.get_ha_enrichment_status()
    assert status["enabled"] == 1
    assert status["matched_devices"] == 0
    assert status["last_push_at"] == ACCEPTED_AT


def test_transaction_failure_preserves_previous_snapshot_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _repo(tmp_path)
    accepted_times = iter(
        ["2026-07-23T01:00:00+00:00", "2026-07-23T02:00:00+00:00"]
    )
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: next(accepted_times))
    apply_ha_enrichment(repo, _request(_device(area_name="Original")))
    before_row = repo.get_ha_device_enrichment("home", IEEE_1)
    before_status = repo.get_ha_enrichment_status()
    original_update = repo.update_ha_enrichment_status

    def fail_after_status_write(**kwargs) -> None:
        original_update(**kwargs)
        raise RuntimeError("injected status failure")

    monkeypatch.setattr(repo, "update_ha_enrichment_status", fail_after_status_write)
    with pytest.raises(RuntimeError, match="injected status failure"):
        apply_ha_enrichment(
            repo,
            _request(
                _device(
                    ieee_address=IEEE_2,
                    ha_device_id="ha-device-2",
                    area_name="Replacement",
                )
            ),
        )

    assert repo.get_ha_device_enrichment("home", IEEE_1) == before_row
    assert repo.get_ha_device_enrichment("home", IEEE_2) is None
    assert repo.get_ha_enrichment_status() == before_status


def test_exact_identity_never_selects_other_network_or_uses_ha_name(
    tmp_path: Path,
):
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

    exact = apply_ha_enrichment(
        repo,
        _request(
            _device(
                network_id="home2",
                ieee_address=ieee,
                ha_device_name="Device home",
            )
        ),
    )
    assert exact.matched == 1
    assert repo.get_ha_device_enrichment("home", ieee) is None
    assert repo.get_ha_device_enrichment("home2", ieee) is not None

    no_name_fallback = apply_ha_enrichment(
        repo,
        _request(
            _device(
                network_id="missing-network",
                ieee_address=ieee,
                ha_device_name="Device home",
            )
        ),
    )
    assert no_name_fallback.matched == 0
    assert no_name_fallback.unmatched == 1
    assert no_name_fallback.stored == 0
    assert repo.get_ha_device_enrichment("home", ieee) is None
    assert repo.get_ha_device_enrichment("home2", ieee) is None


def test_area_cluster_evidence(tmp_path: Path):
    repo = _repo(tmp_path)
    apply_ha_enrichment(
        repo,
        _request(
            _device(),
            _device(
                ieee_address=IEEE_2,
                ha_device_id="ha-device-2",
                ha_device_name="Lamp",
                entity_id="light.lamp",
            ),
        ),
    )
    cluster = area_cluster_for_devices(repo, "home", [IEEE_1, IEEE_2])
    assert cluster["matched"] == 2
    assert cluster["area_count"] == 1


def test_explicit_clear_resets_rows_and_status(tmp_path: Path):
    repo = _repo(tmp_path)
    apply_ha_enrichment(repo, _request(_device()))
    clear_ha_enrichment(repo)
    assert repo.get_ha_device_enrichment("home", IEEE_1) is None
    status = repo.get_ha_enrichment_status()
    assert status["enabled"] == 0
    assert status["matched_devices"] == 0
    assert status["last_push_at"] is None
    assert status["source"] is None


def test_route_validation_failure_preserves_last_accepted_snapshot(
    mock_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = mock_client.app.state.ctx.repo
    repo.upsert_device(
        network_id="home",
        ieee_address=IEEE_1,
        friendly_name="Laundry Plug",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: ACCEPTED_AT)
    accepted = mock_client.post(
        "/api/v1/enrichment/homeassistant",
        json=_request(_device()).model_dump(mode="json"),
    )
    assert accepted.status_code == 200
    before_row = repo.get_ha_device_enrichment("home", IEEE_1)
    before_status = repo.get_ha_enrichment_status()

    malformed = _request(
        _device(ieee_address=IEEE_2, ha_device_id="ha-device-2")
    ).model_dump(mode="json")
    malformed["devices"][0]["unexpected"] = "forbidden"
    rejected = mock_client.post("/api/enrichment/homeassistant", json=malformed)

    assert rejected.status_code == 422
    assert repo.get_ha_device_enrichment("home", IEEE_1) == before_row
    assert repo.get_ha_device_enrichment("home", IEEE_2) is None
    assert repo.get_ha_enrichment_status() == before_status


@pytest.mark.parametrize("conflict_kind", ["ha_device_id", "entity_id"])
def test_route_registry_ownership_conflict_preserves_last_accepted_snapshot(
    mock_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    conflict_kind: str,
):
    repo = mock_client.app.state.ctx.repo
    for ieee_address, name in (
        (IEEE_1, "Laundry Plug"),
        (IEEE_2, "Lamp"),
    ):
        repo.upsert_device(
            network_id="home",
            ieee_address=ieee_address,
            friendly_name=name,
            device_type="Router",
            power_source="Mains",
            interview_state="successful",
        )
    monkeypatch.setattr(ha_module, "utc_now_iso", lambda: ACCEPTED_AT)
    accepted = mock_client.post(
        "/api/v1/enrichment/homeassistant",
        json=_request(_device(area_name="Original")).model_dump(mode="json"),
    )
    assert accepted.status_code == 200
    before_row = repo.get_ha_device_enrichment("home", IEEE_1)
    before_status = repo.get_ha_enrichment_status()

    first = _device(ha_device_name="Rejected replacement")
    second = _device(
        ieee_address=IEEE_2,
        ha_device_id="ha-device-2",
        ha_device_name="Rejected second row",
        entity_id="light.lamp",
    )
    second[conflict_kind] = first[conflict_kind]
    rejected = mock_client.post(
        "/api/v1/enrichment/homeassistant",
        json={
            "home_assistant_enrichment_contract_version": 1,
            "devices": [first, second],
        },
    )

    assert rejected.status_code == 422
    assert repo.get_ha_device_enrichment("home", IEEE_1) == before_row
    assert repo.get_ha_device_enrichment("home", IEEE_2) is None
    assert repo.get_ha_enrichment_status() == before_status


def test_production_route_storage_device_and_report_projection_lifecycle(
    live_client: TestClient,
):
    """Core half of the production E2E: exact route through public projections."""
    repo = live_client.app.state.ctx.repo
    shared_ieee = "0x00124b0024abc999"
    repo.upsert_device(
        network_id="home",
        ieee_address=shared_ieee,
        friendly_name="z2m_kitchen_lamp",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repo.upsert_device(
        network_id="home2",
        ieee_address=shared_ieee,
        friendly_name="z2m_office_lamp",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )

    accepted = live_client.post(
        "/api/v1/enrichment/homeassistant",
        json=_request(
            _device(
                network_id="home",
                ieee_address=shared_ieee,
                ha_device_id="ha-registry-kitchen",
                ha_device_name="Kitchen Lamp",
                area_id="area-kitchen",
                area_name="Kitchen",
                entity_id="light.kitchen_lamp",
            )
        ).model_dump(mode="json"),
    )
    assert accepted.status_code == 200
    assert accepted.json()["stored"] == 1

    items = live_client.get("/api/devices").json()["items"]
    home = next(
        item
        for item in items
        if (item["network_id"], item["ieee_address"]) == ("home", shared_ieee)
    )
    home2 = next(
        item
        for item in items
        if (item["network_id"], item["ieee_address"]) == ("home2", shared_ieee)
    )
    assert home["friendly_name"] == "z2m_kitchen_lamp"
    assert home["home_assistant_name"] == "Kitchen Lamp"
    assert home["home_assistant_area_name"] == "Kitchen"
    assert home["ha_area"] == "Kitchen"
    assert home2["friendly_name"] == "z2m_office_lamp"
    assert home2["home_assistant_name"] is None
    assert home2["home_assistant_area_name"] is None

    detail = live_client.get(f"/api/devices/home/{shared_ieee}").json()
    assert detail["friendly_name"] == "z2m_kitchen_lamp"
    assert detail["home_assistant_name"] == "Kitchen Lamp"
    assert detail["home_assistant_area_name"] == "Kitchen"
    assert detail["ha_area"] == "Kitchen"

    standard_report = live_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": "home",
            "device": shared_ieee,
            "profile": "standard",
        },
    ).json()
    report_device = standard_report["domain_details"]["devices"][0]
    assert report_device["friendly_name"] == "z2m_kitchen_lamp"
    assert report_device["home_assistant_name"] == "Kitchen Lamp"
    assert report_device["home_assistant_area_name"] == "Kitchen"
    assert report_device["ieee_address"].startswith("ieee_")

    public_safe = live_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": "home",
            "device": shared_ieee,
            "profile": "public_safe",
        },
    ).json()
    public_blob = json.dumps(public_safe)
    for prohibited in (
        shared_ieee,
        "Kitchen Lamp",
        "Kitchen",
        "area-kitchen",
        "ha-registry-kitchen",
        "light.kitchen_lamp",
    ):
        assert prohibited not in public_blob
    public_device = public_safe["domain_details"]["devices"][0]
    assert public_device["home_assistant_name"].startswith("device_")
    assert public_device["home_assistant_area_name"].startswith("area_")

    renamed = live_client.post(
        "/api/enrichment/homeassistant",
        json=_request(
            _device(
                network_id="home",
                ieee_address=shared_ieee,
                ha_device_id="ha-registry-kitchen",
                ha_device_name="Dining Pendant",
                area_id="area-dining",
                area_name="Dining",
                entity_id="light.kitchen_lamp",
            )
        ).model_dump(mode="json"),
    )
    assert renamed.status_code == 200
    renamed_detail = live_client.get(f"/api/devices/home/{shared_ieee}").json()
    assert renamed_detail["friendly_name"] == "z2m_kitchen_lamp"
    assert renamed_detail["home_assistant_name"] == "Dining Pendant"
    assert renamed_detail["home_assistant_area_name"] == "Dining"
    renamed_report = live_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": "home",
            "device": shared_ieee,
            "profile": "standard",
        },
    ).json()
    renamed_report_device = renamed_report["domain_details"]["devices"][0]
    assert renamed_report_device["home_assistant_name"] == "Dining Pendant"
    assert renamed_report_device["home_assistant_area_name"] == "Dining"

    removed = live_client.post(
        "/api/v1/enrichment/homeassistant",
        json=_request().model_dump(mode="json"),
    )
    assert removed.status_code == 200
    fallback = live_client.get(f"/api/devices/home/{shared_ieee}").json()
    assert fallback["friendly_name"] == "z2m_kitchen_lamp"
    assert fallback["home_assistant_name"] is None
    assert fallback["home_assistant_area_name"] is None
    assert fallback["ha_area"] is None
    removed_report = live_client.get(
        "/api/reports/preview",
        params={
            "scope": "device",
            "network_id": "home",
            "device": shared_ieee,
            "profile": "standard",
        },
    ).json()
    removed_report_device = removed_report["domain_details"]["devices"][0]
    assert removed_report_device["friendly_name"] == "z2m_kitchen_lamp"
    assert removed_report_device["home_assistant_name"] is None
    assert removed_report_device["home_assistant_area_name"] is None
