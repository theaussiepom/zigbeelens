"""Convert raw MQTT messages into normalized internal events."""

from __future__ import annotations

from typing import Any

from zigbeelens.config.models import NetworkConfig
from zigbeelens.mqtt.models import NormalizedMqttEvent, RawMqttMessage, TopicKind
from zigbeelens.mqtt.payload_utils import extract_online_state, redact_payload_text, safe_parse_json
from zigbeelens.mqtt.topics import classify_topic


def normalize_message(
    message: RawMqttMessage,
    networks: list[NetworkConfig],
    *,
    bridge_logs_enabled: bool = True,
) -> list[NormalizedMqttEvent]:
    classification = classify_topic(message.topic, networks)
    if classification is None:
        return []

    redacted = redact_payload_text(message.payload)
    parsed, parse_error = safe_parse_json(message.payload)

    if classification.kind == TopicKind.ignored:
        return []
    if classification.kind == TopicKind.request_topic:
        return []

    if parse_error and classification.kind not in {
        TopicKind.bridge_state,
        TopicKind.device_availability,
    }:
        return [
            NormalizedMqttEvent(
                event_type="parse_error",
                network_id=classification.network_id,
                title="MQTT payload parse error",
                summary=f"Could not parse JSON on {message.topic}",
                severity="watch",
                raw_payload_redacted=redacted,
                parse_error=parse_error,
            )
        ]

    handlers = {
        TopicKind.bridge_state: _normalize_bridge_state,
        TopicKind.bridge_info: _normalize_bridge_info,
        TopicKind.bridge_devices: _normalize_bridge_devices,
        TopicKind.bridge_event: _normalize_bridge_event,
        TopicKind.bridge_logging: _normalize_bridge_logging,
        TopicKind.bridge_health: _normalize_bridge_health,
        TopicKind.device_availability: _normalize_device_availability,
        TopicKind.device_payload: _normalize_device_payload,
        TopicKind.unknown_bridge_topic: _normalize_unknown_bridge,
    }
    handler = handlers.get(classification.kind)
    if handler is None:
        return []

    events = handler(classification, parsed, redacted, message)
    if classification.kind == TopicKind.bridge_logging and not bridge_logs_enabled:
        events = [e for e in events if e.log_level in {"warning", "error"}]
    return events


def _normalize_bridge_state(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    state = _extract_state(parsed)
    if state is None:
        return [
            NormalizedMqttEvent(
                event_type="parse_error",
                network_id=classification.network_id,
                title="Unknown bridge state payload",
                summary=str(parsed)[:200],
                raw_payload_redacted=redacted,
            )
        ]
    return [
        NormalizedMqttEvent(
            event_type="bridge_state_seen",
            network_id=classification.network_id,
            title=f"Bridge state: {state}",
            summary=f"Bridge reported {state}",
            severity="healthy" if state == "online" else "incident",
            bridge_state=state,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_bridge_info(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    info = parsed if isinstance(parsed, dict) else {}
    return [
        NormalizedMqttEvent(
            event_type="bridge_info_seen",
            network_id=classification.network_id,
            title="Bridge info received",
            summary="Coordinator and bridge metadata updated",
            bridge_info=info,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_bridge_devices(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    devices = parsed if isinstance(parsed, list) else []
    return [
        NormalizedMqttEvent(
            event_type="device_inventory_seen",
            network_id=classification.network_id,
            title="Device inventory updated",
            summary=f"{len(devices)} devices in bridge inventory",
            devices=devices,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_bridge_event(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    data = parsed if isinstance(parsed, dict) else {}
    event_type = str(data.get("type", "unknown_bridge_event"))
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    ieee = nested.get("ieee_address") if nested else data.get("ieee_address")
    friendly = nested.get("friendly_name") if nested else None
    status = str(nested.get("status") or "").lower()
    mapping = {
        "device_joined": "device_joined",
        "device_announce": "device_announced",
        "device_leave": "device_left",
        "device_interview": "device_interview_started",
        "pairing": "device_interview_started",
    }
    normalized_type = mapping.get(event_type, "unknown_bridge_event")
    if "interview" in event_type and "failed" in event_type:
        normalized_type = "device_interview_failed"
    elif "interview" in event_type and "successful" in event_type:
        normalized_type = "device_interview_success"
    elif event_type in {"device_interview", "pairing"} or "interview" in event_type:
        if status == "failed":
            normalized_type = "device_interview_failed"
        elif status == "successful":
            normalized_type = "device_interview_success"
        else:
            # in_progress, absent, or unknown status starts/continues interview.
            normalized_type = "device_interview_started"
    return [
        NormalizedMqttEvent(
            event_type=normalized_type,
            network_id=classification.network_id,
            title=f"Bridge event: {event_type}",
            summary=str(data.get("message") or event_type),
            ieee_address=ieee,
            friendly_name=friendly,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_bridge_logging(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    data = parsed if isinstance(parsed, dict) else {"message": str(parsed)}
    level = str(data.get("level", "info")).lower()
    msg = str(data.get("message", ""))
    event_type = "bridge_log_error" if level == "error" else "bridge_log_warning" if level == "warning" else "bridge_log_info"
    severity = "incident" if level == "error" else "watch" if level == "warning" else "healthy"
    return [
        NormalizedMqttEvent(
            event_type=event_type,
            network_id=classification.network_id,
            title=f"Bridge log ({level})",
            summary=msg[:500],
            severity=severity,
            log_level=level,
            log_message=msg,
            raw_payload_redacted=redacted,
        )
    ]


def _normalize_bridge_health(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    return [
        NormalizedMqttEvent(
            event_type="bridge_health_seen",
            network_id=classification.network_id,
            title="Bridge health received",
            summary="Optional bridge health snapshot stored",
            bridge_info=parsed if isinstance(parsed, dict) else {"raw": parsed},
            raw_payload_redacted=redacted,
        )
    ]


def _normalize_device_availability(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    state = _extract_state(parsed)
    if state is None:
        return [
            NormalizedMqttEvent(
                event_type="parse_error",
                network_id=classification.network_id,
                title="Unknown availability payload",
                summary=str(parsed)[:200],
                friendly_name=classification.friendly_name,
                raw_payload_redacted=redacted,
            )
        ]
    return [
        NormalizedMqttEvent(
            event_type="device_availability_seen",
            network_id=classification.network_id,
            title=f"Availability: {classification.friendly_name} → {state}",
            summary=f"Device availability reported as {state}",
            friendly_name=classification.friendly_name,
            availability=state,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_device_payload(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    fields: dict[str, Any] = {}
    if isinstance(parsed, dict):
        for key in ("linkquality", "battery", "last_seen", "state", "voltage"):
            if key in parsed:
                fields[key] = parsed[key]
    return [
        NormalizedMqttEvent(
            event_type="device_payload_seen",
            network_id=classification.network_id,
            title=f"Device payload: {classification.friendly_name}",
            summary="Device telemetry received",
            friendly_name=classification.friendly_name,
            device_fields=fields,
            raw_payload_redacted=redacted,
            emit_dashboard=True,
        )
    ]


def _normalize_unknown_bridge(classification, parsed, redacted, message) -> list[NormalizedMqttEvent]:
    return [
        NormalizedMqttEvent(
            event_type="unknown_bridge_topic",
            network_id=classification.network_id,
            title=f"Unknown bridge topic: {classification.bridge_subtopic}",
            summary="Stored as low-priority bridge observation",
            raw_payload_redacted=redacted,
        )
    ]


def _extract_state(parsed: Any) -> str | None:
    return extract_online_state(parsed)
