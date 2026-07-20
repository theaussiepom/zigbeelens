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
    validate_decision_count_summary,
)


def _valid_dashboard(**overrides) -> dict:
    payload = {
        "active_incident_count": 0,
        "watching_incident_count": 0,
        "device_count": 1,
        "unavailable_device_count": 0,
        "network_count": 1,
        "decision_summary": {
            "subject_count": 1,
            "overall_status": "watch",
            "highest_priority": "low",
            "status_counts": {"watch": 1},
            "priority_counts": {"low": 1},
            "coverage_warning_count": 0,
        },
        "investigation_priorities": [],
        "data_coverage_warnings": [],
        "networks": [
            {
                "id": "home",
                "name": "Home",
                "device_count": 1,
                "unavailable_count": 0,
                "active_incident_count": 0,
                "decision": {
                    "status": "watch",
                    "priority": "low",
                    "headline_code": "network_watch",
                    "coverage_label_codes": [],
                },
                "decision_summary": {
                    "subject_count": 1,
                    "overall_status": "watch",
                    "highest_priority": "low",
                    "status_counts": {"watch": 1},
                    "priority_counts": {"low": 1},
                    "coverage_warning_count": 0,
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def _contract_payload(
    *,
    version: object = 2,
    shared: object = True,
    companion: object = True,
    decision_only: object = True,
    report_v3: object = True,
    decision_mqtt: object = True,
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
            "report_contract_v3": report_v3,
            "decision_mqtt_summary": decision_mqtt,
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
    assert decision_contract_version({"decision_contract_version": "2"}) == 0
    assert decision_contract_version({"decision_contract_version": 0}) == 0
    assert decision_contract_version(None) == 0
    assert decision_contract_version({}) == 0
    assert decision_contract_version({"decision_contract_version": None}) == 0
    assert decision_contract_version({"decision_contract_version": True}) == 0
    assert decision_contract_version({"decision_contract_version": False}) == 0
    assert decision_contract_version({"decision_contract_version": 1.0}) == 0
    assert decision_contract_version({"decision_contract_version": 2.0}) == 0
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
    assert supports_companion_decisions(_contract_payload(version="2")) is False
    assert supports_companion_decisions(_contract_payload(version=3)) is False
    assert supports_companion_decisions(_contract_payload(shared=False)) is False
    assert supports_companion_decisions(_contract_payload(shared=1)) is False
    assert supports_companion_decisions(_contract_payload(companion="true")) is False
    assert supports_companion_decisions(_contract_payload(decision_only=False)) is False
    assert supports_companion_decisions(_contract_payload(report_v3=False)) is False
    assert supports_companion_decisions(_contract_payload(report_v3=1)) is False
    assert supports_companion_decisions(_contract_payload(decision_mqtt=False)) is False
    assert supports_companion_decisions(_contract_payload(decision_mqtt="true")) is False
    assert supports_companion_decisions(_contract_payload(legacy_health=True)) is False
    # Missing / null / string / 0 must not pass as "not True" for legacy flag.
    for legacy in (None, "false", 0, 1, "False"):
        payload = _contract_payload()
        payload["capabilities"]["legacy_health_lens_payloads"] = legacy
        assert supports_companion_decisions(payload) is False
    missing_legacy = _contract_payload()
    del missing_legacy["capabilities"]["legacy_health_lens_payloads"]
    assert supports_companion_decisions(missing_legacy) is False
    for name in (
        "shared_decisions",
        "companion_decision_summary",
        "decision_only_diagnostic_payloads",
        "report_contract_v3",
        "decision_mqtt_summary",
    ):
        payload = _contract_payload()
        del payload["capabilities"][name]
        assert supports_companion_decisions(payload) is False
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
    assert dashboard_decision_payload_valid(_valid_dashboard()) is True
    assert (
        dashboard_decision_payload_valid(
            {"investigation_priorities": [], "data_coverage_warnings": []}
        )
        is False
    )
    assert (
        dashboard_decision_payload_valid(
            _valid_dashboard(
                decision_summary={
                    "subject_count": 1,
                    "overall_status": "watch",
                    "highest_priority": "low",
                    "status_counts": {"watch": 2},
                    "priority_counts": {"low": 1},
                    "coverage_warning_count": 0,
                }
            )
        )
        is False
    )
    assert validate_decision_count_summary({"subject_count": True}) is False
    assert validate_decision_count_summary({"subject_count": 1, "overall_status": "nope"}) is False
    assert (
        validate_decision_count_summary(
            {
                "subject_count": 0,
                "overall_status": "no_notable_change",
                "highest_priority": "none",
                "status_counts": {},
                "priority_counts": {},
                "coverage_warning_count": 0,
            }
        )
        is False
    )
    assert (
        validate_decision_count_summary(
            {
                "subject_count": 2,
                "overall_status": "watch",
                "highest_priority": "high",
                "status_counts": {"watch": 1, "review_first": 1},
                "priority_counts": {"high": 1, "low": 1},
                "coverage_warning_count": 0,
            }
        )
        is False
    )


def test_validate_decision_badge_known_coverage_labels():
    from zigbeelens.compatibility import validate_decision_badge

    valid = {
        "status": "watch",
        "priority": "low",
        "headline_code": "network_watch",
        "coverage_label_codes": ["availability_tracking_off"],
    }
    assert validate_decision_badge(valid) is True
    assert (
        validate_decision_badge({**valid, "coverage_label_codes": ["future_label"]})
        is False
    )
    assert validate_decision_badge({**valid, "coverage_label_codes": [1]}) is False
    assert validate_decision_badge({**valid, "coverage_label_codes": [None]}) is False
    assert validate_decision_badge({**valid, "coverage_label_codes": [{}]}) is False
    missing = dict(valid)
    del missing["coverage_label_codes"]
    assert validate_decision_badge(missing) is False
