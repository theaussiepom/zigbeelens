"""Persist normalized MQTT events and update current state."""

from __future__ import annotations

import logging
import uuid
from typing import Callable

from zigbeelens.config.models import AppConfig
from zigbeelens.mqtt.models import NormalizedMqttEvent
from zigbeelens.storage.repository import Repository

logger = logging.getLogger(__name__)

OnDashboardUpdate = Callable[[str, str], None]
OnHealthRecalc = Callable[[str, str | None], None]


class MqttIngestionService:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        on_dashboard_update: OnDashboardUpdate | None = None,
        on_health_recalc: OnHealthRecalc | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self._on_dashboard_update = on_dashboard_update
        self._on_health_recalc = on_health_recalc

    def ingest(self, event: NormalizedMqttEvent) -> None:
        handlers = {
            "bridge_state_seen": self._handle_bridge_state,
            "bridge_info_seen": self._handle_bridge_info,
            "device_inventory_seen": self._handle_device_inventory,
            "device_payload_seen": self._handle_device_payload,
            "device_availability_seen": self._handle_device_availability,
            "device_joined": self._handle_bridge_device_event,
            "device_announced": self._handle_bridge_device_event,
            "device_left": self._handle_bridge_device_event,
            "device_interview_started": self._handle_bridge_device_event,
            "device_interview_success": self._handle_bridge_device_event,
            "device_interview_failed": self._handle_bridge_device_event,
            "unknown_bridge_event": self._handle_bridge_device_event,
            "bridge_log_warning": self._handle_bridge_log,
            "bridge_log_error": self._handle_bridge_log,
            "bridge_log_info": self._handle_bridge_log,
            "bridge_health_seen": self._handle_bridge_health,
            "parse_error": self._handle_generic_event,
            "unknown_bridge_topic": self._handle_generic_event,
        }
        handler = handlers.get(event.event_type, self._handle_generic_event)
        with self.repo.transaction():
            handler(event)
            self._store_event(event)
        self._recalc_health_for_event(event)
        if event.emit_dashboard and self._on_dashboard_update:
            self._on_dashboard_update("dashboard_updated", event.network_id)

    def _recalc_health(self, network_id: str, ieee_address: str | None = None) -> None:
        if self._on_health_recalc:
            self._on_health_recalc(network_id, ieee_address)

    def _recalc_health_for_event(self, event: NormalizedMqttEvent) -> None:
        if not self._on_health_recalc:
            return
        if event.event_type in {"bridge_state_seen", "bridge_state_changed"}:
            self._recalc_health(event.network_id, None)
        elif event.event_type == "device_inventory_seen":
            self._recalc_health(event.network_id, None)
        elif event.event_type in {
            "device_joined",
            "device_announced",
            "device_left",
        }:
            # Membership changes must refresh the full network snapshot so later
            # incremental evaluate_device calls do not reuse a stale device universe.
            self._recalc_health(event.network_id, None)
        elif event.event_type == "unknown_bridge_event" and event.ieee_address:
            self._recalc_health(event.network_id, None)
        elif event.ieee_address and event.event_type in {
            "device_payload_seen",
            "device_availability_seen",
            "device_availability_changed",
            "device_interview_started",
            "device_interview_success",
            "device_interview_failed",
        }:
            self._recalc_health(event.network_id, event.ieee_address)

    def _store_event(self, event: NormalizedMqttEvent) -> None:
        self.repo.insert_event(
            event_id=str(uuid.uuid4()),
            network_id=event.network_id,
            ieee_address=event.ieee_address,
            event_type=event.event_type,
            severity=event.severity,
            title=event.title,
            summary=event.summary,
            payload_json=event.raw_payload_redacted,
        )

    def _handle_bridge_state(self, event: NormalizedMqttEvent) -> None:
        state = event.bridge_state or "unknown"
        network = self.repo.get_network(event.network_id)
        previous = network.bridge_state if network else None
        self.repo.update_network_bridge_state(event.network_id, state)
        if previous and previous not in {"unknown", state}:
            event.event_type = "bridge_state_changed"
            event.title = f"Bridge state changed: {previous} → {state}"
            event.summary = f"Bridge changed from {previous} to {state}"

    def _handle_bridge_info(self, event: NormalizedMqttEvent) -> None:
        info = event.bridge_info
        coordinator = info.get("coordinator") if isinstance(info.get("coordinator"), dict) else info
        ieee = None
        if isinstance(coordinator, dict):
            ieee = coordinator.get("ieee_address") or coordinator.get("meta", {}).get("ieee_address")
        self.repo.insert_bridge_snapshot(
            network_id=event.network_id,
            bridge_state=None,
            coordinator_ieee=ieee,
            channel=info.get("channel"),
            pan_id=str(info.get("pan_id")) if info.get("pan_id") is not None else None,
            extended_pan_id=str(info.get("ext_pan_id") or info.get("extended_pan_id") or "") or None,
            payload_json=event.raw_payload_redacted,
        )

    def _handle_device_inventory(self, event: NormalizedMqttEvent) -> None:
        for device in event.devices:
            ieee = device.get("ieee_address") or device.get("ieeeAddr")
            if not ieee:
                self.repo.insert_event(
                    event_id=str(uuid.uuid4()),
                    network_id=event.network_id,
                    ieee_address=None,
                    event_type="inventory_warning",
                    severity="watch",
                    title="Device missing IEEE address",
                    summary=str(device.get("friendly_name", "unknown device")),
                )
                continue
            interview = "successful" if device.get("interview_completed") else (
                "failed" if device.get("interview_completed") is False else "unknown"
            )
            if device.get("interviewing"):
                interview = "in_progress"
            self.repo.upsert_device(
                network_id=event.network_id,
                ieee_address=str(ieee),
                friendly_name=str(device.get("friendly_name") or ieee),
                device_type=_map_device_type(device.get("type")),
                power_source=_map_power_source(device.get("power_source")),
                manufacturer=device.get("manufacturer"),
                model=device.get("model") or device.get("model_id"),
                interview_state=interview,
            )
            self.repo.ensure_device_current_state(event.network_id, str(ieee))
        self.repo.reconcile_unresolved(event.network_id)

    def _handle_device_payload(self, event: NormalizedMqttEvent) -> None:
        if not event.friendly_name:
            return
        matches = self.repo.get_devices_by_friendly_name_in_network(
            event.network_id, event.friendly_name
        )
        if len(matches) == 0:
            self.repo.store_unresolved(
                event.network_id, event.friendly_name, "device_payload", event.raw_payload_redacted
            )
            event.event_type = "unresolved_device_payload"
            event.summary = f"No inventory match for {event.friendly_name}"
            return
        if len(matches) > 1:
            event.event_type = "ambiguous_friendly_name"
            event.summary = f"Multiple devices named {event.friendly_name} on network"
            return
        device = matches[0]
        fields = event.device_fields
        from zigbeelens.storage.repository import utc_now_iso

        ts = utc_now_iso()
        self.repo.update_device_current_state(
            network_id=device.network_id,
            ieee_address=device.ieee_address,
            last_payload_at=ts,
            last_seen=fields.get("last_seen") or ts,
            linkquality=fields.get("linkquality"),
            battery=fields.get("battery"),
        )
        if self.config.features.device_payload_history:
            self.repo.insert_device_snapshot(
                network_id=device.network_id,
                ieee_address=device.ieee_address,
                availability=None,
                last_seen=fields.get("last_seen"),
                last_payload_at=ts,
                linkquality=fields.get("linkquality"),
                battery=fields.get("battery"),
                payload_json=event.raw_payload_redacted,
            )
        if fields.get("linkquality") is not None:
            self.repo.metrics.insert_metric_sample(
                device.network_id, device.ieee_address, "linkquality", float(fields["linkquality"])
            )
        if fields.get("battery") is not None:
            self.repo.metrics.insert_metric_sample(
                device.network_id, device.ieee_address, "battery", float(fields["battery"])
            )
        event.ieee_address = device.ieee_address

    def _handle_device_availability(self, event: NormalizedMqttEvent) -> None:
        if not event.friendly_name:
            return
        matches = self.repo.get_devices_by_friendly_name_in_network(
            event.network_id, event.friendly_name
        )
        if len(matches) == 0:
            self.repo.store_unresolved(
                event.network_id,
                event.friendly_name,
                "device_availability",
                event.raw_payload_redacted,
            )
            event.event_type = "unresolved_device_availability"
            return
        if len(matches) > 1:
            event.event_type = "ambiguous_friendly_name"
            return
        device = matches[0]
        new_state = event.availability or "unknown"
        previous = self.repo.get_device_availability(device.network_id, device.ieee_address)
        self.repo.update_device_current_state(
            network_id=device.network_id,
            ieee_address=device.ieee_address,
            availability=new_state,
        )
        if previous and previous != new_state:
            self.repo.availability.insert_availability_change(
                device.network_id, device.ieee_address, previous, new_state
            )
            event.event_type = "device_availability_changed"
        event.ieee_address = device.ieee_address

    def _handle_bridge_device_event(self, event: NormalizedMqttEvent) -> None:
        if not event.ieee_address:
            return
        interview_by_event = {
            "device_interview_started": "in_progress",
            "device_interview_success": "successful",
            "device_interview_failed": "failed",
        }
        existing = self.repo.get_device(event.network_id, event.ieee_address)
        if existing is not None:
            friendly_name = event.friendly_name or existing.friendly_name
            device_type = existing.device_type
            power_source = existing.power_source
            manufacturer = existing.manufacturer
            model = existing.model
            if event.event_type in interview_by_event:
                interview_state = interview_by_event[event.event_type]
            else:
                interview_state = existing.interview_state
        else:
            friendly_name = event.friendly_name or event.ieee_address
            device_type = "Unknown"
            power_source = "Unknown"
            manufacturer = None
            model = None
            interview_state = interview_by_event.get(event.event_type, "unknown")
        self.repo.upsert_device(
            network_id=event.network_id,
            ieee_address=event.ieee_address,
            friendly_name=friendly_name,
            device_type=device_type,
            power_source=power_source,
            manufacturer=manufacturer,
            model=model,
            interview_state=interview_state,
        )
        self.repo.ensure_device_current_state(event.network_id, event.ieee_address)

    def _handle_bridge_log(self, event: NormalizedMqttEvent) -> None:
        return

    def _handle_bridge_health(self, event: NormalizedMqttEvent) -> None:
        self.repo.insert_bridge_snapshot(
            network_id=event.network_id,
            bridge_state=None,
            payload_json=event.raw_payload_redacted,
        )

    def _handle_generic_event(self, event: NormalizedMqttEvent) -> None:
        return


def _map_device_type(value: object) -> str:
    mapping = {
        "Coordinator": "Coordinator",
        "Router": "Router",
        "EndDevice": "EndDevice",
        "GreenPower": "EndDevice",
    }
    return mapping.get(str(value), "Unknown")


def _map_power_source(value: object) -> str:
    text = str(value or "")
    if "Battery" in text:
        return "Battery"
    if "Mains" in text:
        return "Mains"
    return "Unknown"
