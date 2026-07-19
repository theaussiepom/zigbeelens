"""Compatibility helpers for Core version and decision contract."""

from __future__ import annotations

from zigbeelens.compatibility import (
    DECISION_CONTRACT_VERSION,
    SUPPORTED_DECISION_CONTRACT_VERSIONS,
    core_version_compatible,
    dashboard_decision_payload_valid,
    decision_contract_version,
    parse_core_version,
    supports_companion_decisions,
)


def _contract_payload(
    *,
    version: object = 2,
    shared: object = True,
    companion: object = True,
    decision_only: object = True,
    legacy_health: object = False,
    surfaces: object | None = None,
) -> dict:
    if surfaces is None:
        surfaces = {
            "dashboard_decision_summary": True,
            "dashboard_investigation_priorities": True,
            "dashboard_data_coverage_warnings": True,
            "network_decision_badges": True,
            "device_decision_badges": True,
            "device_story": True,
            "report_device_stories": True,
        }
    return {
        "product": "zigbeelens",
        "decision_contract_version": version,
        "capabilities": {
            "shared_decisions": shared,
            "companion_decision_summary": companion,
            "decision_only_diagnostic_payloads": decision_only,
            "legacy_health_lens_payloads": legacy_health,
        },
        "decision_surfaces": surfaces,
    }


def test_parse_core_version_handles_suffixes():
    assert parse_core_version("0.1.13") == (0, 1, 13)
    assert parse_core_version("0.1.13-edge") == (0, 1, 13)
    assert parse_core_version("1.2.3+build") == (1, 2, 3)
    assert parse_core_version("") is None
    assert parse_core_version(None) is None


def test_core_version_compatible_unknown_is_soft_ok():
    assert core_version_compatible(None) is True
    assert core_version_compatible("not-a-version") is True
    assert core_version_compatible("0.0.9") is False
    assert core_version_compatible("0.1.0") is True


def test_decision_contract_version_strict_parsing():
    assert decision_contract_version({"decision_contract_version": 2}) == 2
    assert decision_contract_version({"decision_contract_version": "2"}) == 2
    assert decision_contract_version({"decision_contract_version": 0}) == 0
    assert decision_contract_version(None) == 0
    assert decision_contract_version({}) == 0
    assert decision_contract_version({"decision_contract_version": None}) == 0
    assert decision_contract_version({"decision_contract_version": True}) == 0
    assert decision_contract_version({"decision_contract_version": False}) == 0
    assert decision_contract_version({"decision_contract_version": 1.0}) == 0
    assert decision_contract_version({"decision_contract_version": 1.5}) == 0
    assert decision_contract_version({"decision_contract_version": -1}) == 0
    assert decision_contract_version({"decision_contract_version": "-1"}) == 0
    assert decision_contract_version({"decision_contract_version": ""}) == 0
    assert decision_contract_version({"decision_contract_version": "  "}) == 0
    assert decision_contract_version({"decision_contract_version": "1x"}) == 0
    assert decision_contract_version({"decision_contract_version": object()}) == 0
    assert decision_contract_version({"decision_contract_version": []}) == 0
    assert decision_contract_version({"decision_contract_version": {}}) == 0


def test_supports_companion_decisions_exact_contract_v2():
    assert DECISION_CONTRACT_VERSION == 2
    assert SUPPORTED_DECISION_CONTRACT_VERSIONS == frozenset({2})
    assert supports_companion_decisions(None) is False
    assert supports_companion_decisions({}) is False
    assert supports_companion_decisions(_contract_payload(version=0)) is False
    assert supports_companion_decisions(_contract_payload(version=1)) is False
    assert supports_companion_decisions(_contract_payload()) is True
    assert supports_companion_decisions(_contract_payload(version="2")) is True
    assert supports_companion_decisions(_contract_payload(version=3)) is False
    assert supports_companion_decisions(_contract_payload(shared=False)) is False
    assert supports_companion_decisions(_contract_payload(shared=1)) is False
    assert supports_companion_decisions(_contract_payload(companion="true")) is False
    assert supports_companion_decisions(_contract_payload(decision_only=False)) is False
    assert supports_companion_decisions(_contract_payload(legacy_health=True)) is False
    assert supports_companion_decisions(_contract_payload(surfaces={})) is False
    assert (
        supports_companion_decisions(
            _contract_payload(
                surfaces={
                    "dashboard_decision_summary": True,
                    "dashboard_investigation_priorities": True,
                    "dashboard_data_coverage_warnings": False,
                    "network_decision_badges": True,
                    "device_decision_badges": True,
                }
            )
        )
        is False
    )
    malformed = _contract_payload()
    malformed["decision_surfaces"] = "nope"
    assert supports_companion_decisions(malformed) is False


def test_dashboard_decision_payload_valid_v2():
    assert dashboard_decision_payload_valid(None) is False
    assert dashboard_decision_payload_valid({}) is False
    assert (
        dashboard_decision_payload_valid(
            {
                "decision_summary": {
                    "overall_status": "watch",
                    "status_counts": {"watch": 1},
                },
                "investigation_priorities": [],
                "data_coverage_warnings": [],
            }
        )
        is True
    )
    assert (
        dashboard_decision_payload_valid(
            {"investigation_priorities": [], "data_coverage_warnings": []}
        )
        is False
    )
    assert (
        dashboard_decision_payload_valid(
            {
                "decision_summary": {"overall_status": "watch"},
                "investigation_priorities": [],
                "data_coverage_warnings": [],
            }
        )
        is False
    )
