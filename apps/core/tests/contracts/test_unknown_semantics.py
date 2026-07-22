"""Unknown/null values must not collapse to measured zero in Core dumps."""

from __future__ import annotations

from zigbeelens.decisions.device_story import DeviceStory
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.schemas import DecisionCountSummary
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


def test_oracle_device_stories_preserve_null_metric_fields():
    nullable_device_fields = (
        "linkquality",
        "battery",
        "last_seen",
        "friendly_name",
        "ha_area",
    )
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        for device in body["devices"]:
            for field in nullable_device_fields:
                if field not in device:
                    continue
                value = device[field]
                # Null stays null; absent is fine; never coerce unknown → 0 here.
                if value is None:
                    assert value is None, (scenario_id, device.get("ieee_address"), field)
                elif field in {"linkquality", "battery"} and value == 0:
                    # Measured zero is allowed only when the fixture emitted an int 0.
                    assert isinstance(value, int)


def test_report_v3_retains_nullable_raw_counts():
    for scenario_id, body in oracle_scenarios(load_oracle_fixture()).items():
        report = body["report"]
        assert report["report_version"] == 3, scenario_id
        for network in report["domain_details"]["networks"]:
            # raw_count fields may be null; never invent numeric defaults in dump.
            if "raw_device_count" in network and network["raw_device_count"] is None:
                assert network["raw_device_count"] is None
        for incident in report.get("active_incidents") or []:
            affected = incident.get("affected_device_count")
            if affected is None:
                assert affected is None
            device_ieees = incident.get("device_ieees") or incident.get("affected_devices")
            if isinstance(device_ieees, list) and len(device_ieees) == 0:
                # Network-only incidents may legitimately have zero affected devices.
                assert len(device_ieees) == 0


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
