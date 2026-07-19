"""Tests for Lens family presentation-layer health buckets."""

from fastapi.testclient import TestClient

from zigbeelens.diagnostics.device_health import classify_device
from zigbeelens.diagnostics.models import DeviceHealthContext
from zigbeelens.presentation.lens_buckets import lens_presentation_for_health
from zigbeelens.schemas import (
    Availability,
    BridgeState,
    Confidence,
    DeviceDecisionBadge,
    DeviceHealth,
    DeviceHealthPrimary,
    DeviceSummary,
    DeviceType,
    InterviewState,
    PowerSource,
    Severity,
)


def _health(
    primary: DeviceHealthPrimary,
    *,
    flags: list[DeviceHealthPrimary] | None = None,
    limitations: list[str] | None = None,
    severity: Severity = Severity.watch,
) -> DeviceHealth:
    return DeviceHealth(
        primary=primary,
        severity=severity,
        confidence=Confidence.medium,
        evidence=["test evidence"],
        limitations=limitations or [],
        flags=flags or [primary],
    )


def test_healthy_device_maps_to_healthy_bucket():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.healthy, flags=[DeviceHealthPrimary.healthy], severity=Severity.healthy),
        availability=Availability.online,
    )
    assert pres["lens_bucket"] == "healthy"
    assert pres["lens_bucket_label"] == "Healthy"


def test_unavailable_device_maps_to_unavailable_bucket():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.unavailable, severity=Severity.incident),
        availability=Availability.offline,
    )
    assert pres["lens_bucket"] == "unavailable"
    assert "Unavailable" in pres["lens_bucket_reason"]


def test_router_risk_maps_to_needs_attention():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.router_risk),
        availability=Availability.online,
    )
    assert pres["lens_bucket"] == "needs_attention"
    assert "Router risk" in pres["lens_reasons"]


def test_recent_flapping_maps_to_recently_unstable():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.recently_unstable),
        availability=Availability.online,
    )
    assert pres["lens_bucket"] == "recently_unstable"


def test_low_battery_maps_to_needs_attention():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.low_battery),
        availability=Availability.online,
    )
    assert pres["lens_bucket"] == "needs_attention"


def test_unknown_insufficient_data_maps_to_diagnostics_limited():
    pres = lens_presentation_for_health(
        _health(
            DeviceHealthPrimary.unknown,
            limitations=["ZigbeeLens has not observed enough history yet"],
        ),
        availability=Availability.unknown,
    )
    assert pres["lens_bucket"] == "diagnostics_limited"


def test_incident_affected_escalates_to_needs_attention():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.recently_unstable),
        availability=Availability.online,
        incident_affected=True,
    )
    assert pres["lens_bucket"] == "needs_attention"


def test_bridge_offline_limits_observation():
    pres = lens_presentation_for_health(
        _health(DeviceHealthPrimary.stale_reporting),
        availability=Availability.unknown,
        bridge_state=BridgeState.offline,
    )
    assert pres["lens_bucket"] == "diagnostics_limited"


def test_presentation_does_not_change_health_engine_output():
    ctx = DeviceHealthContext(
        network_id="home",
        ieee_address="0xabc",
        friendly_name="sensor",
        device_type="EndDevice",
        power_source="Battery",
        interview_state="successful",
        availability="offline",
        last_seen=None,
        last_payload_at=None,
        linkquality=None,
        battery=None,
    )
    from zigbeelens.config.models import DiagnosticsConfig

    result = classify_device(ctx, DiagnosticsConfig())
    assert result.primary.value == "unavailable"
    pres = lens_presentation_for_health(
        DeviceHealth(
            primary=DeviceHealthPrimary(result.primary.value),
            severity=Severity(result.severity.value),
            confidence=Confidence(result.confidence.value),
            evidence=result.evidence,
            limitations=result.limitations,
            flags=[DeviceHealthPrimary(f.value) for f in result.flags],
        ),
        availability=Availability.offline,
    )
    assert pres["lens_bucket"] == "unavailable"


def test_dashboard_excludes_lens_bucket_fields(mock_client: TestClient):
    res = mock_client.get("/api/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert "top_affected_devices" not in body
    devices = mock_client.get("/api/devices").json()["items"]
    assert devices, "expected mock scenario devices"
    device = devices[0]
    assert "health" not in device
    assert "lens_bucket" not in device
    assert "lens_bucket_label" not in device
    assert "lens_reasons" not in device
    assert device["decision"]["status"]


def test_v1_dashboard_excludes_lens_bucket_fields(mock_client: TestClient):
    res = mock_client.get("/api/v1/dashboard")
    assert res.status_code == 200
    assert "top_affected_devices" not in res.json()
    devices = mock_client.get("/api/v1/devices").json()["items"]
    assert devices
    assert "lens_bucket" not in devices[0]
    assert devices[0]["decision"]["status"]


def test_device_detail_is_decision_only(mock_client: TestClient):
    device = mock_client.get("/api/devices").json()["items"][0]
    path = f"/api/devices/{device['network_id']}/{device['ieee_address']}"
    detail = mock_client.get(path).json()
    assert detail["decision"]["status"] == device["decision"]["status"]
    assert "health" not in detail
    assert "diagnostic" not in detail
    assert "lens_bucket" not in detail


def test_enrich_device_summary_removed_from_public_contract():
    """Lens enrich helper remains internal; public DeviceSummary has no lens fields."""
    summary = DeviceSummary(
        network_id="home",
        ieee_address="0x1",
        friendly_name="test",
        device_type=DeviceType.EndDevice,
        power_source=PowerSource.Battery,
        availability=Availability.online,
        interview_state=InterviewState.successful,
        decision=DeviceDecisionBadge(
            status="worth_reviewing",
            priority="high",
            headline_code="device_router_risk",
            coverage_label_codes=[],
        ),
    )
    assert not hasattr(summary, "lens_bucket")
    assert "health" not in summary.model_fields
