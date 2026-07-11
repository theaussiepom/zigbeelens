"""Persistence repositories — no API or MQTT logic."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import cached_property
from typing import TYPE_CHECKING, Any

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database

if TYPE_CHECKING:
    from zigbeelens.storage.access.availability import AvailabilityRepository
    from zigbeelens.storage.access.devices import DeviceRepository
    from zigbeelens.storage.access.metrics import MetricRepository
    from zigbeelens.storage.access.network import NetworkRepository
    from zigbeelens.storage.access.topology import TopologyRepository


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_topology_links(links: list[Any]) -> list[Any]:
    """Collapse duplicate source→target rows from raw maps.

    Zigbee2MQTT can report the same directed neighbour entry more than once.
    The DB primary key is (snapshot_id, source_ieee, target_ieee), so keep the
    row with stronger route evidence, then higher LQI.
    """
    best: dict[tuple[str, str], Any] = {}
    for link in links:
        key = (link.source_ieee, link.target_ieee)
        prev = best.get(key)
        if prev is None:
            best[key] = link
            continue
        prev_routes = prev.route_count or 0
        new_routes = link.route_count or 0
        prev_lqi = prev.linkquality if prev.linkquality is not None else -1
        new_lqi = link.linkquality if link.linkquality is not None else -1
        if new_routes > prev_routes or (new_routes == prev_routes and new_lqi > prev_lqi):
            best[key] = link
    return list(best.values())


@dataclass
class NetworkRow:
    id: str
    name: str
    base_topic: str
    bridge_state: str


@dataclass
class DeviceRow:
    network_id: str
    ieee_address: str
    friendly_name: str
    device_type: str
    power_source: str
    manufacturer: str | None
    model: str | None
    interview_state: str
    availability: str = "unknown"
    last_seen: str | None = None
    last_payload_at: str | None = None
    linkquality: int | None = None
    battery: int | None = None


@dataclass
class ReportRow:
    id: str
    format: str
    summary: str
    body_json: str | None
    body_markdown: str | None
    redaction_json: str
    generated_at: str
    scope: str = "full"
    redaction_profile: str = "standard"
    metadata_json: str = "{}"


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @cached_property
    def topology(self) -> "TopologyRepository":
        from zigbeelens.storage.access.topology import TopologyRepository

        return TopologyRepository(self)

    @cached_property
    def networks(self) -> "NetworkRepository":
        from zigbeelens.storage.access.network import NetworkRepository

        return NetworkRepository(self)

    @cached_property
    def devices(self) -> "DeviceRepository":
        from zigbeelens.storage.access.devices import DeviceRepository

        return DeviceRepository(self)

    @cached_property
    def availability(self) -> "AvailabilityRepository":
        from zigbeelens.storage.access.availability import AvailabilityRepository

        return AvailabilityRepository(self)

    @cached_property
    def metrics(self) -> "MetricRepository":
        from zigbeelens.storage.access.metrics import MetricRepository

        return MetricRepository(self)

    def sync_networks(self, networks: list[NetworkConfig]) -> None:
        now = utc_now_iso()
        for net in networks:
            self.db.conn.execute(
                """
                INSERT INTO networks (id, name, base_topic, bridge_state, created_at, updated_at)
                VALUES (?, ?, ?, 'unknown', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    base_topic = excluded.base_topic,
                    updated_at = excluded.updated_at
                """,
                (net.id, net.name, net.base_topic, now, now),
            )
        self.db.conn.commit()

    def list_networks(self) -> list[NetworkRow]:
        cur = self.db.conn.execute(
            "SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name"
        )
        return [NetworkRow(**dict(row)) for row in cur.fetchall()]

    def get_network(self, network_id: str) -> NetworkRow | None:
        cur = self.db.conn.execute(
            "SELECT id, name, base_topic, bridge_state FROM networks WHERE id = ?",
            (network_id,),
        )
        row = cur.fetchone()
        return NetworkRow(**dict(row)) if row else None

    def count_devices(self) -> int:
        cur = self.db.conn.execute("SELECT COUNT(*) FROM devices")
        return int(cur.fetchone()[0])

    def count_events(self) -> int:
        cur = self.db.conn.execute("SELECT COUNT(*) FROM events")
        return int(cur.fetchone()[0])

    def has_collected_data(self) -> bool:
        if self.count_devices() > 0:
            return True
        cur = self.db.conn.execute("SELECT COUNT(*) FROM bridge_snapshots")
        if int(cur.fetchone()[0]) > 0:
            return True
        cur = self.db.conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type NOT IN ('parse_error')"
        )
        return int(cur.fetchone()[0]) > 0

    def update_network_bridge_state(self, network_id: str, bridge_state: str) -> None:
        self.db.conn.execute(
            "UPDATE networks SET bridge_state = ?, updated_at = ? WHERE id = ?",
            (bridge_state, utc_now_iso(), network_id),
        )
        self.db.conn.commit()

    def get_network_last_mqtt_activity_at(self, network_id: str) -> str | None:
        """Latest observed MQTT activity for a network (devices, bridge snapshots)."""
        cur = self.db.conn.execute(
            """
            SELECT MAX(ts) FROM (
                SELECT last_payload_at AS ts
                FROM device_current_state
                WHERE network_id = ? AND last_payload_at IS NOT NULL
                UNION ALL
                SELECT last_seen AS ts
                FROM device_current_state
                WHERE network_id = ? AND last_seen IS NOT NULL
                UNION ALL
                SELECT captured_at AS ts
                FROM bridge_snapshots
                WHERE network_id = ?
            )
            """,
            (network_id, network_id, network_id),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None

    def insert_bridge_snapshot(
        self,
        *,
        network_id: str,
        bridge_state: str | None,
        coordinator_ieee: str | None = None,
        channel: int | None = None,
        pan_id: str | None = None,
        extended_pan_id: str | None = None,
        payload_json: str | None = None,
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO bridge_snapshots (
                network_id, bridge_state, coordinator_ieee, channel, pan_id,
                extended_pan_id, payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                network_id,
                bridge_state,
                coordinator_ieee,
                channel,
                pan_id,
                extended_pan_id,
                payload_json,
                utc_now_iso(),
            ),
        )
        self.db.conn.commit()

    def upsert_device(
        self,
        *,
        network_id: str,
        ieee_address: str,
        friendly_name: str,
        device_type: str,
        power_source: str,
        manufacturer: str | None = None,
        model: str | None = None,
        interview_state: str = "unknown",
    ) -> None:
        now = utc_now_iso()
        self.db.conn.execute(
            """
            INSERT INTO devices (
                network_id, ieee_address, friendly_name, device_type, power_source,
                manufacturer, model, interview_state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(network_id, ieee_address) DO UPDATE SET
                friendly_name = excluded.friendly_name,
                device_type = excluded.device_type,
                power_source = excluded.power_source,
                manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer),
                model = COALESCE(excluded.model, devices.model),
                interview_state = excluded.interview_state,
                updated_at = excluded.updated_at
            """,
            (
                network_id,
                ieee_address,
                friendly_name,
                device_type,
                power_source,
                manufacturer,
                model,
                interview_state,
                now,
                now,
            ),
        )
        self.db.conn.commit()

    def ensure_device_current_state(self, network_id: str, ieee_address: str) -> None:
        self.db.conn.execute(
            """
            INSERT OR IGNORE INTO device_current_state (network_id, ieee_address)
            VALUES (?, ?)
            """,
            (network_id, ieee_address),
        )
        self.db.conn.commit()

    def update_device_current_state(
        self,
        *,
        network_id: str,
        ieee_address: str,
        availability: str | None = None,
        last_seen: str | None = None,
        last_payload_at: str | None = None,
        linkquality: int | None = None,
        battery: int | None = None,
    ) -> None:
        self.ensure_device_current_state(network_id, ieee_address)
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if availability is not None:
            fields.append("availability = ?")
            values.append(availability)
        if last_seen is not None:
            fields.append("last_seen = ?")
            values.append(last_seen)
        if last_payload_at is not None:
            fields.append("last_payload_at = ?")
            values.append(last_payload_at)
        if linkquality is not None:
            fields.append("linkquality = ?")
            values.append(linkquality)
        if battery is not None:
            fields.append("battery = ?")
            values.append(battery)
        values.extend([network_id, ieee_address])
        self.db.conn.execute(
            f"UPDATE device_current_state SET {', '.join(fields)} WHERE network_id = ? AND ieee_address = ?",
            values,
        )
        self.db.conn.commit()

    def get_device_availability(self, network_id: str, ieee_address: str) -> str | None:
        cur = self.db.conn.execute(
            "SELECT availability FROM device_current_state WHERE network_id = ? AND ieee_address = ?",
            (network_id, ieee_address),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def insert_device_snapshot(
        self,
        *,
        network_id: str,
        ieee_address: str,
        availability: str | None,
        last_seen: str | None,
        last_payload_at: str | None,
        linkquality: int | None,
        battery: int | None,
        payload_json: str | None,
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO device_snapshots (
                network_id, ieee_address, availability, last_seen, last_payload_at,
                linkquality, battery, payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                network_id,
                ieee_address,
                availability,
                last_seen,
                last_payload_at,
                linkquality,
                battery,
                payload_json,
                utc_now_iso(),
            ),
        )
        self.db.conn.commit()

    def insert_metric_sample(
        self, network_id: str, ieee_address: str, metric_name: str, metric_value: float
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (network_id, ieee_address, metric_name, metric_value, utc_now_iso()),
        )
        self.db.conn.commit()

    def insert_event(
        self,
        *,
        event_id: str,
        network_id: str | None,
        ieee_address: str | None,
        event_type: str,
        severity: str,
        title: str,
        summary: str,
        payload_json: str | None = None,
        incident_id: str | None = None,
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO events (
                id, network_id, ieee_address, event_type, severity, title, summary,
                incident_id, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                network_id,
                ieee_address,
                event_type,
                severity,
                title,
                summary,
                incident_id,
                payload_json,
                utc_now_iso(),
            ),
        )
        self.db.conn.commit()

    def insert_availability_change(
        self, network_id: str, ieee_address: str, from_state: str, to_state: str
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO availability_changes (network_id, ieee_address, from_state, to_state, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (network_id, ieee_address, from_state, to_state, utc_now_iso()),
        )
        self.db.conn.commit()

    def get_devices_by_friendly_name_in_network(
        self, network_id: str, friendly_name: str
    ) -> list[DeviceRow]:
        cur = self.db.conn.execute(
            """
            SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source,
                   d.manufacturer, d.model, d.interview_state,
                   COALESCE(s.availability, 'unknown') AS availability,
                   s.last_seen, s.last_payload_at, s.linkquality, s.battery
            FROM devices d
            LEFT JOIN device_current_state s
              ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address
            WHERE d.network_id = ? AND d.friendly_name = ?
            """,
            (network_id, friendly_name),
        )
        return [DeviceRow(**dict(row)) for row in cur.fetchall()]

    def store_unresolved(
        self, network_id: str, friendly_name: str, message_kind: str, payload_json: str | None
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO unresolved_device_messages (network_id, friendly_name, message_kind, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (network_id, friendly_name, message_kind, payload_json),
        )
        self.db.conn.commit()

    def reconcile_unresolved(self, network_id: str) -> None:
        cur = self.db.conn.execute(
            "SELECT id, friendly_name, message_kind, payload_json FROM unresolved_device_messages WHERE network_id = ?",
            (network_id,),
        )
        rows = cur.fetchall()
        for row in rows:
            matches = self.get_devices_by_friendly_name_in_network(network_id, row["friendly_name"])
            if len(matches) != 1:
                continue
            device = matches[0]
            if row["message_kind"] == "device_payload" and row["payload_json"]:
                from zigbeelens.mqtt.payload_utils import safe_parse_json

                parsed, _ = safe_parse_json(row["payload_json"])
                fields = parsed if isinstance(parsed, dict) else {}
                self.update_device_current_state(
                    network_id=device.network_id,
                    ieee_address=device.ieee_address,
                    last_payload_at=utc_now_iso(),
                    last_seen=fields.get("last_seen"),
                    linkquality=fields.get("linkquality"),
                    battery=fields.get("battery"),
                )
            if row["message_kind"] == "device_availability" and row["payload_json"]:
                from zigbeelens.mqtt.payload_utils import extract_online_state, safe_parse_json

                parsed, _ = safe_parse_json(row["payload_json"])
                state = extract_online_state(parsed)
                if state:
                    self.update_device_current_state(
                        network_id=device.network_id,
                        ieee_address=device.ieee_address,
                        availability=state,
                    )
            self.db.conn.execute(
                "DELETE FROM unresolved_device_messages WHERE id = ?", (row["id"],)
            )
        self.db.conn.commit()

    def update_collector_status(
        self,
        *,
        enabled: bool,
        connected: bool,
        subscribed_topics_count: int,
        last_message_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self.db.conn.execute(
            """
            UPDATE collector_status SET
                enabled = ?,
                connected = ?,
                subscribed_topics_count = ?,
                last_message_at = COALESCE(?, last_message_at),
                last_error = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                int(enabled),
                int(connected),
                subscribed_topics_count,
                last_message_at,
                last_error,
                utc_now_iso(),
            ),
        )
        self.db.conn.commit()

    def get_collector_status(self) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            """
            SELECT enabled, connected, subscribed_topics_count, last_message_at, last_error
            FROM collector_status WHERE id = 1
            """
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def count_devices_for_network(self, network_id: str) -> int:
        cur = self.db.conn.execute(
            "SELECT COUNT(*) FROM devices WHERE network_id = ?", (network_id,)
        )
        return int(cur.fetchone()[0])

    def count_unavailable_for_network(self, network_id: str) -> int:
        cur = self.db.conn.execute(
            """
            SELECT COUNT(*) FROM device_current_state
            WHERE network_id = ? AND availability = 'offline'
            """,
            (network_id,),
        )
        return int(cur.fetchone()[0])

    def get_latest_bridge_snapshot(self, network_id: str) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            """
            SELECT coordinator_ieee, channel, pan_id, extended_pan_id, payload_json, captured_at
            FROM bridge_snapshots WHERE network_id = ?
            ORDER BY captured_at DESC LIMIT 1
            """,
            (network_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_devices(self, network_id: str | None = None) -> list[DeviceRow]:
        query = """
            SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source,
                   d.manufacturer, d.model, d.interview_state,
                   COALESCE(s.availability, 'unknown') AS availability,
                   s.last_seen, s.last_payload_at, s.linkquality, s.battery
            FROM devices d
            LEFT JOIN device_current_state s
              ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address
        """
        if network_id:
            cur = self.db.conn.execute(
                query + " WHERE d.network_id = ? ORDER BY d.friendly_name",
                (network_id,),
            )
        else:
            cur = self.db.conn.execute(query + " ORDER BY d.network_id, d.friendly_name")
        return [DeviceRow(**dict(row)) for row in cur.fetchall()]

    def get_device(self, network_id: str, ieee_address: str) -> DeviceRow | None:
        cur = self.db.conn.execute(
            """
            SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source,
                   d.manufacturer, d.model, d.interview_state,
                   COALESCE(s.availability, 'unknown') AS availability,
                   s.last_seen, s.last_payload_at, s.linkquality, s.battery
            FROM devices d
            LEFT JOIN device_current_state s
              ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address
            WHERE d.network_id = ? AND d.ieee_address = ?
            """,
            (network_id, ieee_address),
        )
        row = cur.fetchone()
        return DeviceRow(**dict(row)) if row else None

    def get_devices_by_friendly_name(self, friendly_name: str) -> list[DeviceRow]:
        """Return all devices matching a friendly name (may span networks)."""
        cur = self.db.conn.execute(
            """
            SELECT network_id, ieee_address, friendly_name, device_type, power_source,
                   manufacturer, model, interview_state
            FROM devices WHERE friendly_name = ?
            """,
            (friendly_name,),
        )
        return [DeviceRow(**dict(row)) for row in cur.fetchall()]

    def list_events(self, network_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if network_id:
            cur = self.db.conn.execute(
                """
                SELECT id, network_id, ieee_address, event_type, severity, title, summary,
                       incident_id, occurred_at
                FROM events WHERE network_id = ?
                ORDER BY occurred_at DESC LIMIT ?
                """,
                (network_id, limit),
            )
        else:
            cur = self.db.conn.execute(
                """
                SELECT id, network_id, ieee_address, event_type, severity, title, summary,
                       incident_id, occurred_at
                FROM events ORDER BY occurred_at DESC LIMIT ?
                """,
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]

    def list_incidents(self, status_filter: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT id, incident_type, lifecycle_state, severity, scope, confidence,
                   title, summary, explanation, evidence_json, counter_evidence_json,
                   limitations_json, opened_at, updated_at, resolved_at, dedup_key
            FROM incidents
        """
        params: list[Any] = []
        if status_filter:
            placeholders = ",".join("?" for _ in status_filter)
            query += f" WHERE lifecycle_state IN ({placeholders})"
            params.extend(status_filter)
        query += " ORDER BY CASE lifecycle_state WHEN 'open' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END, updated_at DESC"
        cur = self.db.conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def list_active_incidents(self) -> list[dict[str, Any]]:
        return self.list_incidents(status_filter=("open", "watching"))

    def get_incident_by_dedup_key(self, dedup_key: str) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            """
            SELECT id, incident_type, lifecycle_state, severity, scope, confidence,
                   title, summary, explanation, evidence_json, counter_evidence_json,
                   limitations_json, opened_at, updated_at, resolved_at, dedup_key
            FROM incidents
            WHERE dedup_key = ? AND lifecycle_state IN ('open', 'watching')
            ORDER BY updated_at DESC LIMIT 1
            """,
            (dedup_key,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def insert_incident(
        self,
        *,
        incident_id: str,
        dedup_key: str,
        incident_type: str,
        lifecycle_state: str,
        severity: str,
        scope: str,
        confidence: str,
        title: str,
        summary: str,
        explanation: str,
        evidence: list[str],
        counter_evidence: list[str],
        limitations: list[str],
        opened_at: str,
        updated_at: str,
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO incidents (
                id, dedup_key, incident_type, lifecycle_state, severity, scope, confidence,
                title, summary, explanation, evidence_json, counter_evidence_json,
                limitations_json, opened_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                dedup_key,
                incident_type,
                lifecycle_state,
                severity,
                scope,
                confidence,
                title,
                summary,
                explanation,
                json.dumps(evidence),
                json.dumps(counter_evidence),
                json.dumps(limitations),
                opened_at,
                updated_at,
            ),
        )
        self.db.conn.commit()

    def update_incident(
        self,
        *,
        incident_id: str,
        lifecycle_state: str | None = None,
        severity: str | None = None,
        confidence: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        explanation: str | None = None,
        evidence: list[str] | None = None,
        counter_evidence: list[str] | None = None,
        limitations: list[str] | None = None,
        resolved_at: str | None = ...,  # type: ignore[assignment]
        updated_at: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [updated_at or utc_now_iso()]
        if lifecycle_state is not None:
            fields.append("lifecycle_state = ?")
            values.append(lifecycle_state)
        if severity is not None:
            fields.append("severity = ?")
            values.append(severity)
        if confidence is not None:
            fields.append("confidence = ?")
            values.append(confidence)
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if explanation is not None:
            fields.append("explanation = ?")
            values.append(explanation)
        if evidence is not None:
            fields.append("evidence_json = ?")
            values.append(json.dumps(evidence))
        if counter_evidence is not None:
            fields.append("counter_evidence_json = ?")
            values.append(json.dumps(counter_evidence))
        if limitations is not None:
            fields.append("limitations_json = ?")
            values.append(json.dumps(limitations))
        if resolved_at is not ...:
            fields.append("resolved_at = ?")
            values.append(resolved_at)
        values.append(incident_id)
        self.db.conn.execute(
            f"UPDATE incidents SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        self.db.conn.commit()

    def replace_incident_devices(self, incident_id: str, devices) -> None:
        from zigbeelens.diagnostics.incidents.models import AffectedDevice

        self.db.conn.execute("DELETE FROM incident_devices WHERE incident_id = ?", (incident_id,))
        for device in devices:
            if not isinstance(device, AffectedDevice):
                continue
            self.db.conn.execute(
                """
                INSERT INTO incident_devices (incident_id, network_id, ieee_address, role)
                VALUES (?, ?, ?, ?)
                """,
                (incident_id, device.network_id, device.ieee_address, device.role),
            )
        self.db.conn.commit()

    def list_offline_transitions_since(
        self, network_id: str, since_iso: str
    ) -> dict[str, str]:
        cur = self.db.conn.execute(
            """
            SELECT ieee_address, changed_at
            FROM availability_changes
            WHERE network_id = ? AND to_state = 'offline' AND changed_at >= ?
            ORDER BY changed_at ASC
            """,
            (network_id, since_iso),
        )
        result: dict[str, str] = {}
        for row in cur.fetchall():
            result[row["ieee_address"]] = row["changed_at"]
        return result

    def list_incidents_for_device(self, network_id: str, ieee_address: str) -> list[str]:
        cur = self.db.conn.execute(
            """
            SELECT DISTINCT i.id
            FROM incidents i
            JOIN incident_devices d ON d.incident_id = i.id
            WHERE d.network_id = ? AND d.ieee_address = ?
              AND i.lifecycle_state IN ('open', 'watching')
            ORDER BY i.updated_at DESC
            """,
            (network_id, ieee_address),
        )
        return [row[0] for row in cur.fetchall()]

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            """
            SELECT id, incident_type, lifecycle_state, severity, scope, confidence,
                   title, summary, explanation, evidence_json, counter_evidence_json,
                   limitations_json, opened_at, updated_at, resolved_at, dedup_key
            FROM incidents WHERE id = ?
            """,
            (incident_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_incident_devices(self, incident_id: str) -> list[dict[str, str]]:
        cur = self.db.conn.execute(
            """
            SELECT incident_id, network_id, ieee_address, role
            FROM incident_devices WHERE incident_id = ?
            """,
            (incident_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def save_report(
        self,
        *,
        report_id: str | None,
        format: str,
        summary: str,
        body: dict[str, Any],
        markdown: str | None = None,
        redaction: dict[str, Any] | None = None,
        scope: str = "full",
        redaction_profile: str = "standard",
        metadata: dict[str, Any] | None = None,
    ) -> ReportRow:
        rid = report_id or str(uuid.uuid4())
        generated_at = utc_now_iso()
        redaction_json = json.dumps(redaction or {})
        body_json = json.dumps(body)
        metadata_json = json.dumps(metadata or {})
        self.db.conn.execute(
            """
            INSERT INTO reports (
                id, format, redaction_json, summary, body_json, body_markdown,
                generated_at, scope, redaction_profile, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                format,
                redaction_json,
                summary,
                body_json,
                markdown,
                generated_at,
                scope,
                redaction_profile,
                metadata_json,
            ),
        )
        self.db.conn.commit()
        return ReportRow(
            id=rid,
            format=format,
            summary=summary,
            body_json=body_json,
            body_markdown=markdown,
            redaction_json=redaction_json,
            generated_at=generated_at,
            scope=scope,
            redaction_profile=redaction_profile,
            metadata_json=metadata_json,
        )

    _REPORT_COLUMNS = (
        "id, format, summary, body_json, body_markdown, redaction_json, "
        "generated_at, scope, redaction_profile, metadata_json"
    )

    def get_report(self, report_id: str) -> ReportRow | None:
        cur = self.db.conn.execute(
            f"SELECT {self._REPORT_COLUMNS} FROM reports WHERE id = ?",
            (report_id,),
        )
        row = cur.fetchone()
        return ReportRow(**dict(row)) if row else None

    def list_reports(self, limit: int = 50) -> list[ReportRow]:
        cur = self.db.conn.execute(
            f"SELECT {self._REPORT_COLUMNS} FROM reports "
            "ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        )
        return [ReportRow(**dict(row)) for row in cur.fetchall()]

    def delete_report(self, report_id: str) -> bool:
        cur = self.db.conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        self.db.conn.commit()
        return cur.rowcount > 0

    def count_availability_changes_in_window(
        self, network_id: str, ieee_address: str, window_hours: int
    ) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=window_hours)
        ).isoformat()
        cur = self.db.conn.execute(
            """
            SELECT COUNT(*) FROM availability_changes
            WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?
            """,
            (network_id, ieee_address, cutoff),
        )
        return int(cur.fetchone()[0])

    def list_availability_changes(
        self, network_id: str, ieee_address: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        cur = self.db.conn.execute(
            """
            SELECT from_state, to_state, changed_at
            FROM availability_changes
            WHERE network_id = ? AND ieee_address = ?
            ORDER BY changed_at DESC LIMIT ?
            """,
            (network_id, ieee_address, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_earliest_availability_change_at(self, network_id: str) -> str | None:
        """Timestamp of the first recorded availability transition for a
        network, or None when no availability history exists. Read-only;
        used to describe availability tracking coverage honestly."""
        cur = self.db.conn.execute(
            """
            SELECT MIN(changed_at) FROM availability_changes
            WHERE network_id = ?
            """,
            (network_id,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None

    def list_availability_changes_since(
        self, network_id: str, since_iso: str
    ) -> list[dict[str, Any]]:
        """All availability transitions for a network since a cutoff,
        oldest first. Read-only passive data already recorded by MQTT
        ingestion; used for passive-derived investigation hints."""
        cur = self.db.conn.execute(
            """
            SELECT ieee_address, from_state, to_state, changed_at
            FROM availability_changes
            WHERE network_id = ? AND changed_at >= ?
            ORDER BY changed_at ASC
            """,
            (network_id, since_iso),
        )
        return [dict(row) for row in cur.fetchall()]

    def list_active_incident_device_addresses(self, network_id: str) -> list[str]:
        """IEEE addresses linked to open/watching incidents in a network."""
        cur = self.db.conn.execute(
            """
            SELECT DISTINCT d.ieee_address
            FROM incident_devices d
            JOIN incidents i ON i.id = d.incident_id
            WHERE d.network_id = ? AND i.lifecycle_state IN ('open', 'watching')
            """,
            (network_id,),
        )
        return [row[0] for row in cur.fetchall()]

    def list_metric_samples(
        self, network_id: str, ieee_address: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        cur = self.db.conn.execute(
            """
            SELECT metric_name, metric_value, sampled_at
            FROM metric_samples
            WHERE network_id = ? AND ieee_address = ?
            ORDER BY sampled_at DESC LIMIT ?
            """,
            (network_id, ieee_address, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def insert_health_snapshot(
        self,
        *,
        scope: str,
        network_id: str | None,
        ieee_address: str | None,
        primary: str,
        severity: str,
        confidence: str,
        summary: str,
        flags: list[str],
        evidence: list[str],
        counter_evidence: list[str],
        limitations: list[str],
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO health_snapshots (
                scope, network_id, ieee_address, primary_health, severity, confidence,
                summary, flags_json, evidence_json, counter_evidence_json, limitations_json,
                captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope,
                network_id,
                ieee_address,
                primary,
                severity,
                confidence,
                summary,
                json.dumps(flags),
                json.dumps(evidence),
                json.dumps(counter_evidence),
                json.dumps(limitations),
                utc_now_iso(),
            ),
        )
        self.db.conn.commit()

    def get_latest_health_snapshot(
        self, scope: str, network_id: str | None, ieee_address: str | None = None
    ) -> dict[str, Any] | None:
        query = """
            SELECT primary_health, severity, confidence, summary, flags_json,
                   evidence_json, counter_evidence_json, limitations_json, captured_at
            FROM health_snapshots
            WHERE scope = ?
        """
        params: list[Any] = [scope]
        if network_id is not None:
            query += " AND network_id = ?"
            params.append(network_id)
        if scope == "device":
            query += " AND ieee_address = ?"
            params.append(ieee_address)
        else:
            query += " AND ieee_address IS NULL"
        query += " ORDER BY captured_at DESC LIMIT 1"
        cur = self.db.conn.execute(query, params)
        row = cur.fetchone()
        if not row:
            return None
        data = dict(row)
        payload = {
            "primary": data["primary_health"],
            "severity": data["severity"],
            "summary": data.get("summary") or "",
            "flags": json.loads(data.get("flags_json") or "[]"),
        }
        data["fingerprint"] = json.dumps(payload, sort_keys=True)
        return data

    # --- Topology snapshots ---

    def create_topology_snapshot(
        self,
        *,
        snapshot_id: str,
        network_id: str,
        requested_by: str,
        status: str,
        warning_acknowledged: bool = False,
        error: str | None = None,
    ) -> None:
        self.db.conn.execute(
            """
            INSERT INTO topology_snapshots (
                snapshot_id, network_id, captured_at, requested_by, status,
                warning_acknowledged, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                network_id,
                utc_now_iso(),
                requested_by,
                status,
                1 if warning_acknowledged else 0,
                error,
            ),
        )
        self.db.conn.commit()

    def update_topology_snapshot(
        self,
        snapshot_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if not fields:
            return
        values.append(snapshot_id)
        self.db.conn.execute(
            f"UPDATE topology_snapshots SET {', '.join(fields)} WHERE snapshot_id = ?",
            values,
        )
        self.db.conn.commit()

    def store_topology_parsed(self, snapshot_id: str, network_id: str, parsed, *, status: str) -> None:
        from zigbeelens.topology.parser import ParsedTopology

        assert isinstance(parsed, ParsedTopology)
        stored_links = _dedupe_topology_links(parsed.links)
        link_count = len(stored_links)
        self.db.conn.execute(
            """
            UPDATE topology_snapshots SET
                status = ?,
                raw_redacted_json = ?,
                parsed_json = ?,
                router_count = ?,
                end_device_count = ?,
                link_count = ?,
                error = NULL
            WHERE snapshot_id = ?
            """,
            (
                status,
                json.dumps(parsed.raw_redacted),
                json.dumps(
                    {
                        "router_count": parsed.router_count,
                        "end_device_count": parsed.end_device_count,
                        "link_count": link_count,
                    }
                ),
                parsed.router_count,
                parsed.end_device_count,
                link_count,
                snapshot_id,
            ),
        )
        self.db.conn.execute("DELETE FROM topology_nodes WHERE snapshot_id = ?", (snapshot_id,))
        self.db.conn.execute("DELETE FROM topology_links WHERE snapshot_id = ?", (snapshot_id,))
        for node in parsed.nodes:
            self.db.conn.execute(
                """
                INSERT INTO topology_nodes (
                    snapshot_id, network_id, ieee_address, friendly_name, node_type, depth, lqi, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    network_id,
                    node.ieee_address,
                    node.friendly_name,
                    node.node_type,
                    node.depth,
                    node.lqi,
                    json.dumps(node.raw_json),
                ),
            )
        for link in stored_links:
            self.db.conn.execute(
                """
                INSERT INTO topology_links (
                    snapshot_id, network_id, source_ieee, target_ieee, source_type, target_type,
                    linkquality, depth, relationship, route_count, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    network_id,
                    link.source_ieee,
                    link.target_ieee,
                    link.source_type,
                    link.target_type,
                    link.linkquality,
                    link.depth,
                    link.relationship,
                    link.route_count,
                    json.dumps(link.raw_json),
                ),
            )
        self.db.conn.commit()

    def enforce_topology_retention(self, network_id: str, max_snapshots: int) -> None:
        cur = self.db.conn.execute(
            """
            SELECT snapshot_id FROM topology_snapshots
            WHERE network_id = ?
            ORDER BY captured_at DESC
            """,
            (network_id,),
        )
        rows = [row[0] for row in cur.fetchall()]
        for snapshot_id in rows[max_snapshots:]:
            self.delete_topology_snapshot(snapshot_id)

    def delete_topology_snapshot(self, snapshot_id: str) -> None:
        self.db.conn.execute("DELETE FROM topology_links WHERE snapshot_id = ?", (snapshot_id,))
        self.db.conn.execute("DELETE FROM topology_nodes WHERE snapshot_id = ?", (snapshot_id,))
        self.db.conn.execute("DELETE FROM topology_snapshots WHERE snapshot_id = ?", (snapshot_id,))
        self.db.conn.commit()

    def _has_table(self, name: str) -> bool:
        cur = self.db.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return cur.fetchone() is not None

    def get_latest_topology_snapshot(self, network_id: str) -> dict[str, Any] | None:
        if not self._has_table("topology_snapshots"):
            return None
        cur = self.db.conn.execute(
            """
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count, warning_acknowledged, error
            FROM topology_snapshots
            WHERE network_id = ? AND status = 'complete'
            ORDER BY captured_at DESC LIMIT 1
            """,
            (network_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_topology_snapshots(self, network_id: str) -> list[dict[str, Any]]:
        cur = self.db.conn.execute(
            """
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count, warning_acknowledged, error
            FROM topology_snapshots
            WHERE network_id = ?
            ORDER BY captured_at DESC
            """,
            (network_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_topology_snapshot(self, network_id: str, snapshot_id: str) -> dict[str, Any] | None:
        cur = self.db.conn.execute(
            """
            SELECT snapshot_id, network_id, captured_at, requested_by, status,
                   router_count, end_device_count, link_count, warning_acknowledged, error,
                   raw_redacted_json, parsed_json
            FROM topology_snapshots
            WHERE network_id = ? AND snapshot_id = ?
            """,
            (network_id, snapshot_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_topology_nodes(self, snapshot_id: str) -> list[dict[str, Any]]:
        cur = self.db.conn.execute(
            """
            SELECT ieee_address, friendly_name, node_type, depth, lqi
            FROM topology_nodes WHERE snapshot_id = ?
            ORDER BY node_type, ieee_address
            """,
            (snapshot_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def list_topology_links(self, snapshot_id: str) -> list[dict[str, Any]]:
        cur = self.db.conn.execute(
            """
            SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth,
                   relationship, route_count
            FROM topology_links WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_topology_node_name(self, snapshot_id: str, ieee_address: str) -> str | None:
        cur = self.db.conn.execute(
            "SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?",
            (snapshot_id, ieee_address),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def list_topology_children(self, snapshot_id: str, router_ieee: str) -> list[str]:
        cur = self.db.conn.execute(
            """
            SELECT target_ieee FROM topology_links
            WHERE snapshot_id = ? AND source_ieee = ?
            """,
            (snapshot_id, router_ieee),
        )
        return [row[0] for row in cur.fetchall()]

    def get_topology_parent_router(self, snapshot_id: str, ieee_address: str) -> str | None:
        cur = self.db.conn.execute(
            """
            SELECT source_ieee FROM topology_links
            WHERE snapshot_id = ? AND target_ieee = ?
            LIMIT 1
            """,
            (snapshot_id, ieee_address),
        )
        row = cur.fetchone()
        if not row:
            return None
        source = row[0]
        cur2 = self.db.conn.execute(
            "SELECT node_type FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?",
            (snapshot_id, source),
        )
        node = cur2.fetchone()
        if node and str(node[0]).lower() in {"router", "coordinator"}:
            return source
        return None

    def find_devices_by_ieee(self, ieee_address: str) -> list[DeviceRow]:
        cur = self.db.conn.execute(
            """
            SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source,
                   d.manufacturer, d.model, d.interview_state,
                   COALESCE(s.availability, 'unknown') AS availability,
                   s.last_seen, s.last_payload_at, s.linkquality, s.battery
            FROM devices d
            LEFT JOIN device_current_state s
              ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address
            WHERE d.ieee_address = ?
            """,
            (ieee_address,),
        )
        return [DeviceRow(**dict(row)) for row in cur.fetchall()]

    def get_device_by_friendly_name(self, network_id: str, friendly_name: str) -> DeviceRow | None:
        matches = self.get_devices_by_friendly_name_in_network(network_id, friendly_name)
        return matches[0] if matches else None

    # --- HA enrichment ---

    def get_ha_enrichment_status(self) -> dict[str, Any]:
        if not self._has_table("ha_enrichment_status"):
            return {"enabled": 0, "matched_devices": 0}
        cur = self.db.conn.execute(
            "SELECT enabled, last_push_at, matched_devices, source FROM ha_enrichment_status WHERE id = 1"
        )
        row = cur.fetchone()
        return dict(row) if row else {"enabled": 0, "matched_devices": 0}

    def update_ha_enrichment_status(
        self,
        *,
        enabled: bool,
        matched_devices: int,
        source: str | None,
        last_push_at: str | None = None,
    ) -> None:
        self.db.conn.execute(
            """
            UPDATE ha_enrichment_status
            SET enabled = ?, matched_devices = ?, source = ?, last_push_at = ?
            WHERE id = 1
            """,
            (1 if enabled else 0, matched_devices, source, last_push_at),
        )
        self.db.conn.commit()

    def replace_ha_device_enrichment(self, matches) -> None:
        from zigbeelens.enrichment.ha import MatchResult

        self.db.conn.execute("DELETE FROM ha_device_enrichment")
        now = utc_now_iso()
        for match in matches:
            assert isinstance(match, MatchResult)
            self.db.conn.execute(
                """
                INSERT INTO ha_device_enrichment (
                    network_id, ieee_address, ha_device_id, ha_device_name,
                    area_id, area_name, entity_id, match_confidence, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match.network_id,
                    match.ieee_address,
                    match.ha_device_id,
                    match.ha_device_name,
                    match.area_id,
                    match.area_name,
                    match.entity_id,
                    match.match_confidence,
                    now,
                ),
            )
        self.db.conn.commit()

    def clear_ha_device_enrichment(self) -> None:
        self.db.conn.execute("DELETE FROM ha_device_enrichment")
        self.db.conn.execute(
            "UPDATE ha_enrichment_status SET enabled = 0, matched_devices = 0, source = NULL WHERE id = 1"
        )
        self.db.conn.commit()

    def get_ha_device_enrichment(self, network_id: str, ieee_address: str) -> dict[str, Any] | None:
        if not self._has_table("ha_device_enrichment"):
            return None
        cur = self.db.conn.execute(
            """
            SELECT network_id, ieee_address, ha_device_id, ha_device_name,
                   area_id, area_name, entity_id, match_confidence, updated_at
            FROM ha_device_enrichment
            WHERE network_id = ? AND ieee_address = ?
            """,
            (network_id, ieee_address),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def purge_collected_data_before(self, cutoff_iso: str) -> dict[str, int]:
        """Remove collected telemetry older than *cutoff_iso* (UTC ISO timestamp)."""
        counts: dict[str, int] = {}

        def _delete(table: str, where: str) -> None:
            cur = self.db.conn.execute(f"DELETE FROM {table} WHERE {where}", (cutoff_iso,))
            counts[table] = cur.rowcount

        _delete("metric_samples", "sampled_at < ?")
        _delete("availability_changes", "changed_at < ?")
        _delete("device_snapshots", "captured_at < ?")
        _delete("bridge_snapshots", "captured_at < ?")
        _delete("health_snapshots", "captured_at < ?")
        _delete("events", "occurred_at < ?")
        _delete("reports", "generated_at < ?")
        if self._has_table("unresolved_device_messages"):
            _delete("unresolved_device_messages", "received_at < ?")

        cur = self.db.conn.execute(
            """
            DELETE FROM incidents
            WHERE lifecycle_state = 'resolved'
              AND resolved_at IS NOT NULL
              AND resolved_at < ?
            """,
            (cutoff_iso,),
        )
        counts["incidents_resolved"] = cur.rowcount

        if self._has_table("topology_snapshots"):
            cur = self.db.conn.execute(
                """
                SELECT snapshot_id FROM topology_snapshots
                WHERE captured_at < ?
                """,
                (cutoff_iso,),
            )
            stale_ids = [row[0] for row in cur.fetchall()]
            for snapshot_id in stale_ids:
                self.delete_topology_snapshot(snapshot_id)
            counts["topology_snapshots"] = len(stale_ids)

        self.db.conn.commit()
        return counts
