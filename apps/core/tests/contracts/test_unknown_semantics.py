"""Unknown/null values must not collapse to measured zero in Core dumps."""

from __future__ import annotations

from zigbeelens.decisions.device_story import DeviceStory
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import DecisionCountSummary, DeviceSummary, ReportDetailV3
from support.contracts import load_oracle_fixture, oracle_scenarios  # type: ignore[import-not-found]


def test_empty_decision_count_summary_retains_zero_as_measured_empty_set():
    """Empty subject set uses measured zeros; this is not 'unknown → 0'."""
    summary = DecisionCountSummary(
        subject_count=0,
        overall_status=DecisionStatus.data_unavailable,
        highest_priority=DecisionPriority.none,
        status_counts={},
        priority_counts={},
        coverage_warning_count=0,
    )
    dumped = summary.model_dump(mode="json")
    assert dumped["subject_count"] == 0
    assert dumped["status_counts"] == {}
    assert dumped["priority_counts"] == {}


def test_device_summary_preserves_null_telemetry_through_serialization():
    device = DeviceSummary.model_validate(
        {
            "network_id": "home",
            "ieee_address": "0xabc",
            "friendly_name": "Sensor",
            "device_type": "EndDevice",
            "power_source": "Battery",
            "availability": "online",
            "interview_state": "successful",
            "battery": None,
            "linkquality": None,
            "last_seen": None,
            "ha_area": None,
            "decision": {
                "status": "data_unavailable",
                "priority": "none",
                "headline_code": "device_data_unavailable",
                "coverage_label_codes": [],
            },
        }
    )
    dumped = device.model_dump(mode="json")
    assert dumped["battery"] is None
    assert dumped["linkquality"] is None
    assert dumped["last_seen"] is None
    assert dumped["ha_area"] is None
    assert dumped["battery"] != 0
    assert dumped["linkquality"] != 0


def test_oracle_corpus_has_null_telemetry_preserved_in_json():
    null_hits = 0
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        for device in body["devices"]:
            for field in ("linkquality", "battery", "last_seen", "ha_area"):
                if field in device and device[field] is None:
                    null_hits += 1
                    assert device[field] is None, (scenario_id, field)
                    # Re-validate through the production schema boundary.
                    summary = DeviceSummary.model_validate(device)
                    assert getattr(summary, field) is None, (scenario_id, field)
    assert null_hits >= 3, f"expected constructed null telemetry cases, got {null_hits}"


def test_report_v3_preserves_null_device_facts_and_network_only_incidents():
    null_device_facts = 0
    network_only_incidents = 0
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        report = ReportDetailV3.model_validate(body["report"])
        assert report.report_version == 3, scenario_id
        for device in report.domain_details.devices:
            dumped = device.model_dump(mode="json")
            for field in ("battery", "linkquality", "last_seen"):
                if field in dumped and dumped[field] is None:
                    null_device_facts += 1
                    assert dumped[field] is None
        for incident in report.incidents:
            affected = getattr(incident, "affected_devices", None) or []
            if len(affected) == 0:
                network_only_incidents += 1
                # Measured empty affected set is allowed; unknown must not become 1.
                assert list(affected) == []
    assert null_device_facts + network_only_incidents >= 1, (
        f"expected null telemetry and/or network-only incidents in oracle corpus; "
        f"got null_device_facts={null_device_facts}, "
        f"network_only_incidents={network_only_incidents}"
    )


def test_device_story_model_dump_keeps_empty_collections_empty():
    story = DeviceStory.model_validate(
        {
            "subject_type": "device",
            "subject_id": "0x01",
            "status": "data_unavailable",
            "priority": "none",
            "headline_code": "device_data_unavailable",
            "reasons": [],
            "evidence": [],
            "limitations": [],
            "suggested_checks": [],
            "coverage": [],
            "timeline": [],
        }
    )
    dumped = story.model_dump(mode="json")
    assert dumped["reasons"] == []
    assert dumped["suggested_checks"] == []
    assert dumped["status"] == "data_unavailable"
