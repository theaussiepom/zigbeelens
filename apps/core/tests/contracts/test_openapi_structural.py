"""Structural OpenAPI checks with $ref/allOf resolution (no full snapshot)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import reset_context
from zigbeelens.decisions.types import DecisionPriority, DecisionStatus
from zigbeelens.main import create_app
from zigbeelens.schemas import (
    HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES,
    HomeAssistantEnrichmentRequestV1,
    HomeAssistantEnrichmentResultV1,
    ReportDetailV3,
)


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/components/schemas/")
        name = ref.rsplit("/", 1)[-1]
        assert name in components, name
        return _resolve_schema(components[name], components)
    if "allOf" in schema:
        merged: dict[str, Any] = {"properties": {}, "required": []}
        for part in schema["allOf"]:
            resolved = _resolve_schema(part, components)
            merged["properties"].update(resolved.get("properties") or {})
            merged["required"] = list(
                dict.fromkeys(
                    list(merged.get("required") or []) + list(resolved.get("required") or [])
                )
            )
            for key, value in resolved.items():
                if key not in {"properties", "required"}:
                    merged[key] = value
        return merged
    if "anyOf" in schema:
        # Prefer the first non-null branch.
        for part in schema["anyOf"]:
            if part.get("type") == "null":
                continue
            return _resolve_schema(part, components)
    return schema


@pytest.fixture
def openapi_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {tmp_path / "openapi.sqlite"}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    reset_context()
    with TestClient(create_app(str(config_path))) as client:
        schema = client.get("/openapi.json").json()
    reset_context()
    return schema


def test_openapi_decision_enums_and_required(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    status = _resolve_schema(components["DecisionStatus"], components)
    priority = _resolve_schema(components["DecisionPriority"], components)
    assert set(status["enum"]) == {m.value for m in DecisionStatus}
    assert set(priority["enum"]) == {m.value for m in DecisionPriority}

    badge = _resolve_schema(
        components.get("DeviceDecisionBadge") or components["DecisionBadge"],
        components,
    )
    for key in ("status", "priority", "headline_code", "coverage_label_codes"):
        assert key in badge["required"], key

    summary = _resolve_schema(components["DecisionCountSummary"], components)
    for key in (
        "subject_count",
        "overall_status",
        "highest_priority",
        "status_counts",
        "priority_counts",
        "coverage_warning_count",
    ):
        assert key in summary["required"], key


@pytest.mark.parametrize("prefix", ("/api", "/api/v1"))
def test_snapshot_history_openapi_description_states_layout_requirements(
    openapi_schema: dict,
    prefix: str,
) -> None:
    operation = openapi_schema["paths"][
        f"{prefix}/topology/{{network_id}}/devices/{{ieee_address}}/snapshot-history"
    ]["get"]
    description = " ".join(operation["description"].split())
    assert "recent complete topology captures" in description
    assert (
        "only when both the latest and selected captures have available stored "
        "node/link layouts"
        in description
    )
    assert "Presence differences describe only what two stored layouts observed" in (
        description
    )

    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema["$ref"].endswith("/DeviceSnapshotHistoryDetail")


def test_snapshot_history_openapi_owns_typed_presence_comparison(
    openapi_schema: dict,
) -> None:
    components = openapi_schema["components"]["schemas"]
    detail = _resolve_schema(components["DeviceSnapshotHistoryDetail"], components)
    assert set(detail["required"]) == {
        "network_id",
        "device_ieee",
        "friendly_name",
        "has_current_issue",
        "availability_tracking",
        "latest_snapshot",
        "snapshots",
        "topology_facts",
    }

    tracking = _resolve_schema(
        components["DeviceSnapshotAvailabilityTracking"],
        components,
    )
    assert set(tracking["required"]) == {
        "enabled",
        "earliest_observation_at",
    }

    expected_row_fields = {
        "snapshot_id",
        "captured_at",
        "is_latest",
        "layout_state",
        "is_usable",
        "device_present_in_snapshot",
        "links_for_device_count",
        "route_hints_for_device_count",
        "availability_coverage_status",
        "availability_state_near_snapshot",
        "comparison_to_latest",
    }
    available = _resolve_schema(
        components["DeviceSnapshotHistoryAvailableRow"],
        components,
    )
    limited = _resolve_schema(
        components["DeviceSnapshotHistoryLimitedRow"],
        components,
    )
    assert set(available["required"]) == expected_row_fields
    assert set(limited["required"]) == expected_row_fields

    comparison = _resolve_schema(
        components["DeviceSnapshotComparison"],
        components,
    )
    assert {
        "status",
        "reasons",
        "suggested_checks",
        "device_presence",
        "link_counts",
        "route_hint_counts",
    } == set(comparison["required"])

    presence = _resolve_schema(
        components["DeviceSnapshotPresenceComparison"],
        components,
    )
    assert set(presence["required"]) == {"latest", "selected", "changed"}
    assert all(
        presence["properties"][field]["type"] == "boolean"
        for field in ("latest", "selected", "changed")
    )

    topology_facts = _resolve_schema(
        components["DeviceSnapshotTopologyFacts"],
        components,
    )
    assert set(topology_facts["required"]) == {
        "stale_threshold_hours",
        "device_facts",
        "comparison_facts_by_snapshot_id",
    }
    latest_fact_items = topology_facts["properties"]["device_facts"]["items"]
    assert latest_fact_items["discriminator"]["propertyName"] == "code"
    assert {
        item["$ref"].rsplit("/", 1)[-1] for item in latest_fact_items["oneOf"]
    } == {
        "DeviceSnapshotSeenLatestFact",
        "DeviceSnapshotAbsentLatestFact",
        "DeviceSnapshotHasLatestLinksFact",
        "DeviceSnapshotNoLatestLinksFact",
    }
    comparison_fact_items = topology_facts["properties"][
        "comparison_facts_by_snapshot_id"
    ]["additionalProperties"]["items"]
    assert comparison_fact_items["discriminator"]["propertyName"] == "code"
    assert {
        item["$ref"].rsplit("/", 1)[-1]
        for item in comparison_fact_items["oneOf"]
    } == {
        "DeviceSnapshotSelectedLinksFact",
        "DeviceSnapshotChangedFact",
        "DeviceSnapshotAvailabilityCoverageFact",
    }
    latest_presence_params = _resolve_schema(
        components["DeviceSnapshotLatestPresenceFactParams"],
        components,
    )
    assert set(latest_presence_params["required"]) == {
        "device_ieee",
        "snapshot_id",
    }
    latest_links_params = _resolve_schema(
        components["DeviceSnapshotLatestLinksFactParams"],
        components,
    )
    assert set(latest_links_params["required"]) == {
        "device_ieee",
        "link_count",
    }
    changed_fact_params = _resolve_schema(
        components["DeviceSnapshotChangedFactParams"],
        components,
    )
    assert set(changed_fact_params["required"]) == {
        "device_ieee",
        "comparison_status",
        "snapshot_id",
        "latest_device_present_in_snapshot",
        "selected_device_present_in_snapshot",
        "device_presence_changed",
    }


def test_openapi_report_v3_required_exact(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    assert "ReportDetailV3" in components or "ReportDetail" in components
    report = _resolve_schema(
        components.get("ReportDetailV3") or components["ReportDetail"],
        components,
    )
    expected = set(ReportDetailV3.model_fields)
    assert set(report["required"]) == expected
    assert len(report["required"]) == 20

    domain = _resolve_schema(components["ReportDomainDetailsV3"], components)
    assert set(domain["required"]) == {
        "networks",
        "devices",
        "device_details",
        "router_risks",
        "topology_snapshot_count",
    }

    story = _resolve_schema(components["ReportDeviceStory"], components)
    for key in (
        "network_id",
        "ieee_address",
        "status",
        "priority",
        "headline_code",
        "reasons",
        "limitations",
        "suggested_checks",
        "coverage",
    ):
        assert key in story["required"], key

    redaction = _resolve_schema(components["ReportRedactionStatus"], components)
    for key in (
        "applied",
        "profile",
        "mqtt_credentials",
        "secrets",
        "hostnames",
        "ip_addresses",
        "ieee_addresses_hashed",
        "friendly_names",
        "network_names",
    ):
        assert key in redaction["required"], key

    for banned in (
        "LegacyStoredReportBody",
        "StoredReportVersionKind",
        "ReportDetailV1",
        "ReportDetailV2",
    ):
        assert banned not in components


def test_openapi_home_assistant_enrichment_v1_is_exact(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    request = _resolve_schema(
        components["HomeAssistantEnrichmentRequestV1"],
        components,
    )
    result = _resolve_schema(
        components["HomeAssistantEnrichmentResultV1"],
        components,
    )
    device = _resolve_schema(
        components["HomeAssistantEnrichmentDeviceV1"],
        components,
    )

    assert request["additionalProperties"] is False
    assert set(request["required"]) == set(HomeAssistantEnrichmentRequestV1.model_fields)
    assert request["properties"]["home_assistant_enrichment_contract_version"][
        "const"
    ] == 1
    devices = request["properties"]["devices"]
    assert devices["maxItems"] == HOME_ASSISTANT_ENRICHMENT_MAX_DEVICES
    assert _resolve_schema(devices["items"], components) == device

    assert device["additionalProperties"] is False
    assert set(device["required"]) == {
        "network_id",
        "ieee_address",
        "ha_device_id",
    }
    assert device["properties"]["ieee_address"]["pattern"] == r"^0x[0-9a-f]{16}$"

    assert result["additionalProperties"] is False
    assert set(result["required"]) == set(HomeAssistantEnrichmentResultV1.model_fields)
    assert result["properties"]["home_assistant_enrichment_contract_version"][
        "const"
    ] == 1
    assert result["properties"]["last_push_at"]["format"] == "date-time"

    for prefix in ("/api", "/api/v1"):
        operation = openapi_schema["paths"][f"{prefix}/enrichment/homeassistant"]["post"]
        body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert _resolve_schema(body_schema, components) == request
        assert _resolve_schema(response_schema, components) == result


def test_openapi_incident_and_security(openapi_schema: dict):
    components = openapi_schema["components"]["schemas"]
    paths = openapi_schema["paths"]
    incident = _resolve_schema(components["Incident"], components)
    for key in ("id", "type", "status", "severity", "scope", "confidence", "title"):
        assert key in incident["required"], key

    incidents = paths.get("/api/incidents") or paths.get("/api/v1/incidents")
    assert incidents is not None
    params = incidents["get"].get("parameters") or []
    order = next(p for p in params if p.get("name") == "order")
    order_schema = _resolve_schema(order.get("schema") or {}, components)
    assert set(order_schema["enum"]) == {"lifecycle", "recent"}

    security_schemes = openapi_schema.get("components", {}).get("securitySchemes", {})
    for name, scheme in security_schemes.items():
        assert "remote-user" not in name.lower()
        assert "x-remote-user" not in str(scheme).lower()
    assert "/" not in paths or "get" not in (paths.get("/") or {})
