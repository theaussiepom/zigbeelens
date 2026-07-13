"""Tests for observed router-area evidence facts (Phase 4F-1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from zigbeelens.config.models import AppConfig, ModeConfig, NetworkConfig, StorageConfig
from zigbeelens.db.connection import Database
from zigbeelens.decisions.router_area import (
    ObservedRouterAreaState,
    build_observed_router_areas,
    ha_area_context_for_members,
    observed_router_areas_for_network,
)
from zigbeelens.enrichment.ha import MatchResult, apply_ha_enrichment
from zigbeelens.storage.repository import DeviceRow, Repository

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_PHRASES = [
    "parent router",
    "caused by router",
    "route through router",
    "currently routed",
    "current route",
    "current path",
    "actual path",
    "shared path",
    "coverage area",
    "served by router",
    "root cause",
]


def _device(
    ieee: str,
    *,
    device_type: str = "EndDevice",
    availability: str = "online",
    name: str | None = None,
) -> DeviceRow:
    return DeviceRow(
        network_id="home",
        ieee_address=ieee,
        friendly_name=name or f"Device {ieee}",
        device_type=device_type,
        power_source="Mains",
        manufacturer=None,
        model=None,
        interview_state="successful",
        availability=availability,
        battery=None,
        last_seen=None,
    )


def _link(
    source: str,
    target: str,
    *,
    route_count: int | None = None,
    source_type: str | None = None,
    target_type: str | None = None,
) -> dict:
    return {
        "source_ieee": source,
        "target_ieee": target,
        "source_type": source_type,
        "target_type": target_type,
        "route_count": route_count,
        "linkquality": 100,
        "relationship": None,
    }


def _build(**overrides):
    defaults = dict(
        network_id="home",
        devices=[],
        latest_links=[],
        historical_neighbors=None,
        historical_routes=None,
        last_known_links=None,
        passive_hints=None,
        issue_device_ieees=None,
        ha_area_context_by_router=None,
    )
    defaults.update(overrides)
    return build_observed_router_areas(**defaults)


def _assert_no_forbidden_phrases(payload: object) -> None:
    text = json.dumps(payload, default=str).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, phrase


def test_empty_network_produces_no_observed_areas():
    result = _build()
    assert result.state is ObservedRouterAreaState.no_observed_areas
    assert result.areas == []


def test_router_with_latest_adjacency_produces_one_area():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
    )
    assert result.state is ObservedRouterAreaState.observed_areas_available
    assert len(result.areas) == 1
    area = result.areas[0]
    assert area.area_id == "home:0xr1"
    assert area.router_ieee == "0xr1"
    assert area.latest_neighbour_ieees == ["0xa1"]
    assert "0xr1" not in area.member_ieees
    _assert_no_forbidden_phrases(area.model_dump())


def test_end_device_does_not_become_router_area_centre():
    devices = [_device("0xa1"), _device("0xa2")]
    result = _build(devices=devices, latest_links=[_link("0xa1", "0xa2")])
    assert result.state is ObservedRouterAreaState.no_observed_areas


def test_latest_neighbour_and_route_hint_membership_remain_distinct():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1"),
        _device("0xa2"),
        _device("0xa3"),
    ]
    result = _build(
        devices=devices,
        latest_links=[
            _link("0xr1", "0xa1", route_count=2, source_type="Router"),
            _link("0xr1", "0xa2", source_type="Router"),
        ],
        historical_routes=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa3",
                "evidence_class": "historical_route",
                "last_seen_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.latest_neighbour_ieees == ["0xa1", "0xa2"]
    assert area.route_hint_ieees == ["0xa1"]
    assert "0xa3" not in area.latest_neighbour_ieees
    assert "0xa3" not in area.route_hint_ieees
    assert "0xa3" in area.recent_missing_ieees


def test_historical_neighbor_contributes_recent_missing():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        historical_neighbors=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa1",
                "evidence_class": "historical_neighbor",
                "last_seen_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.recent_missing_ieees == ["0xa1"]
    assert "historical_neighbor" in area.evidence_classes
    assert "0xa1" not in area.latest_neighbour_ieees


def test_historical_route_contributes_recent_missing_without_route_hint_claim():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        historical_routes=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa1",
                "evidence_class": "historical_route",
                "last_seen_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.recent_missing_ieees == ["0xa1"]
    assert "historical_route" in area.evidence_classes
    assert area.route_hint_ieees == []


def test_last_known_evidence_stays_in_last_known_ieees_only():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        last_known_links=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa1",
                "evidence_class": "last_known_link",
                "last_reported_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.last_known_ieees == ["0xa1"]
    assert area.latest_neighbour_ieees == []
    assert "last_known_link" in area.evidence_classes


def test_passive_hint_contributes_only_to_passive_hint_ieees():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        passive_hints=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa1",
                "evidence_class": "passive_derived_association",
                "last_seen_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.passive_hint_ieees == ["0xa1"]
    assert area.latest_neighbour_ieees == []
    assert "passive_derived_association" in area.evidence_classes


def test_current_issue_member_appears_in_issue_device_ieees():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xa1", availability="offline"),
    ]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
        issue_device_ieees={"0xa1"},
    )
    area = result.areas[0]
    assert area.issue_device_ieees == ["0xa1"]


def test_evidence_alone_does_not_create_current_issue():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
    )
    assert result.areas[0].issue_device_ieees == []


def test_ha_area_context_describes_members_without_creating_membership(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.upsert_device(
        network_id="home",
        ieee_address="0xa1",
        friendly_name="Kitchen plug",
        device_type="EndDevice",
        power_source="Mains",
    )
    apply_ha_enrichment(
        repo,
        {
            "devices": [
                {
                    "network_id": "home",
                    "ieee_address": "0xa1",
                    "area_name": "Kitchen",
                }
            ]
        },
    )
    devices = [_device("0xr1", device_type="Router"), _device("0xa1"), _device("0xb1")]
    result = observed_router_areas_for_network(
        repo,
        "home",
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
        history={"historical_neighbors": [], "historical_routes": []},
        last_known_links=[],
        passive_hints=[],
        issue_device_ieees=set(),
    )
    area = result.areas[0]
    assert area.member_ieees == ["0xa1"]
    assert area.ha_area_context is not None
    assert area.ha_area_context.areas == {"Kitchen": ["0xa1"]}
    assert "0xb1" not in area.member_ieees


def test_low_confidence_ha_enrichment_is_ignored(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.replace_ha_device_enrichment(
        [
            MatchResult(
                network_id="home",
                ieee_address="0xa1",
                ha_device_id="ha-1",
                ha_device_name="Plug",
                area_id="kitchen",
                area_name="Kitchen",
                entity_id="switch.plug",
                match_confidence="low",
            )
        ]
    )
    context = ha_area_context_for_members(repo, "home", ["0xa1"])
    assert context is None


def test_duplicate_evidence_keeps_union_and_source_specific_sets():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
        passive_hints=[
            {
                "source_ieee": "0xr1",
                "target_ieee": "0xa1",
                "evidence_class": "passive_derived_association",
                "last_seen_at": NOW.isoformat(),
            }
        ],
    )
    area = result.areas[0]
    assert area.member_ieees == ["0xa1"]
    assert area.latest_neighbour_ieees == ["0xa1"]
    assert area.passive_hint_ieees == ["0xa1"]


def test_self_links_are_ignored():
    devices = [_device("0xr1", device_type="Router")]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xr1", source_type="Router")],
    )
    assert result.areas == []


def test_ieee_addresses_are_normalised_and_sorted():
    devices = [
        _device("0xR1", device_type="Router"),
        _device("0xB2"),
        _device("0xA1"),
    ]
    result = _build(
        devices=devices,
        latest_links=[
            _link("0XR1", "0xa1", source_type="Router"),
            _link("0xr1", "0xb2", source_type="Router"),
        ],
    )
    area = result.areas[0]
    assert area.router_ieee == "0xr1"
    assert area.latest_neighbour_ieees == ["0xa1", "0xb2"]


def test_router_without_relevant_evidence_is_omitted():
    devices = [
        _device("0xr1", device_type="Router"),
        _device("0xr2", device_type="Router"),
        _device("0xa1"),
    ]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
    )
    assert [area.router_ieee for area in result.areas] == ["0xr1"]


def test_area_identity_is_stable_when_member_evidence_changes():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1"), _device("0xa2")]
    first = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
    )
    second = _build(
        devices=devices,
        latest_links=[
            _link("0xr1", "0xa1", source_type="Router"),
            _link("0xr1", "0xa2", source_type="Router"),
        ],
    )
    assert first.areas[0].area_id == second.areas[0].area_id == "home:0xr1"
    assert len(first.areas[0].member_ieees) < len(second.areas[0].member_ieees)


def test_missing_optional_evidence_stays_absent_not_a_diagnostic_zero_claim():
    devices = [_device("0xr1", device_type="Router"), _device("0xa1")]
    result = _build(
        devices=devices,
        latest_links=[_link("0xr1", "0xa1", source_type="Router")],
    )
    area = result.areas[0]
    assert area.ha_area_context is None
    assert area.latest_supporting_evidence_at is None
    assert area.route_hint_ieees == []
    assert area.last_known_ieees == []
    assert area.passive_hint_ieees == []
    assert area.params["route_hint_count"] == 0
    assert area.params["route_hint_refs"] == []


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "router-area.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(
        mode=ModeConfig(mock=True),
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")],
        storage=StorageConfig(path=str(tmp_path / "router-area.sqlite")),
    )
    repo.sync_networks(config.networks)
    return repo
