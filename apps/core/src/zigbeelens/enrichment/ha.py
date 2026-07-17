"""Optional Home Assistant area/device enrichment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from zigbeelens.storage.repository import Repository, utc_now_iso

IEEE_RE = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
MAX_DEVICES = 5000


@dataclass
class MatchResult:
    network_id: str
    ieee_address: str
    ha_device_id: str | None
    ha_device_name: str | None
    area_id: str | None
    area_name: str | None
    entity_id: str | None
    match_confidence: str


def enrichment_status_dict(repo: Repository) -> dict[str, Any]:
    row = repo.get_ha_enrichment_status()
    return {
        "enabled": bool(row.get("enabled")),
        "last_push_at": row.get("last_push_at"),
        "matched_devices": int(row.get("matched_devices") or 0),
        "source": row.get("source"),
    }


def apply_ha_enrichment(repo: Repository, payload: dict[str, Any]) -> dict[str, Any]:
    devices = payload.get("devices") or []
    if len(devices) > MAX_DEVICES:
        raise ValueError("Enrichment payload too large")

    matches: list[MatchResult] = []
    for device in devices:
        match = _match_device(repo, device)
        if match:
            matches.append(match)

    repo.replace_ha_device_enrichment(matches)
    repo.update_ha_enrichment_status(
        enabled=True,
        matched_devices=len(matches),
        source="homeassistant",
        last_push_at=utc_now_iso(),
    )
    return {
        "matched_devices": len(matches),
        "last_push_at": utc_now_iso(),
    }


def clear_ha_enrichment(repo: Repository) -> None:
    repo.clear_ha_device_enrichment()
    repo.update_ha_enrichment_status(enabled=False, matched_devices=0, source=None)


def area_cluster_for_devices(
    repo: Repository,
    network_id: str,
    ieee_addresses: list[str],
    *,
    enrichment_by_ieee: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    areas: dict[str, list[str]] = {}
    matched = 0
    if enrichment_by_ieee is None and ieee_addresses:
        bulk = repo.list_ha_device_enrichment_for_devices(
            [(network_id, ieee) for ieee in ieee_addresses]
        )
        enrichment_by_ieee = {
            ieee.lower(): row for (_network_id, ieee), row in bulk.items()
        }
    for ieee in ieee_addresses:
        key = str(ieee or "").strip().lower()
        row = (
            enrichment_by_ieee.get(key)
            if enrichment_by_ieee is not None
            else repo.get_ha_device_enrichment(network_id, ieee)
        )
        if not row:
            continue
        if row.get("match_confidence") == "low":
            continue
        matched += 1
        area = row.get("area_name") or "unknown"
        areas.setdefault(area, []).append(ieee)
    return {"matched": matched, "areas": areas, "area_count": len(areas)}


def _match_device(repo: Repository, device: dict[str, Any]) -> MatchResult | None:
    ieee = _extract_ieee(device)
    network_id = device.get("network_id")
    friendly_name = device.get("friendly_name") or device.get("name")

    if ieee and network_id:
        if repo.get_device(network_id, ieee):
            return _result(device, network_id, ieee, "high")
        return None

    if ieee:
        for row in repo.find_devices_by_ieee(ieee):
            return _result(device, row.network_id, row.ieee_address, "high")

    if network_id and friendly_name:
        row = repo.get_device_by_friendly_name(network_id, friendly_name)
        if row:
            return _result(device, row.network_id, row.ieee_address, "medium")

    return None


def _extract_ieee(device: dict[str, Any]) -> str | None:
    for key in ("ieee_address", "ieee"):
        if device.get(key):
            text = str(device[key]).strip().lower()
            if IEEE_RE.match(text):
                return text
    for ident in device.get("identifiers") or []:
        if isinstance(ident, (list, tuple)) and len(ident) == 2:
            domain, value = ident
            if str(domain).lower() in {"zha", "zigbee2mqtt", "zigbee"} and IEEE_RE.match(str(value).lower()):
                return str(value).lower()
    connections = device.get("connections") or []
    for conn in connections:
        if isinstance(conn, (list, tuple)) and len(conn) == 2:
            kind, value = conn
            if str(kind).lower() == "zigbee" and IEEE_RE.match(str(value).lower()):
                return str(value).lower()
    return None


def _result(device: dict[str, Any], network_id: str, ieee: str, confidence: str) -> MatchResult:
    return MatchResult(
        network_id=network_id,
        ieee_address=ieee,
        ha_device_id=device.get("ha_device_id") or device.get("device_id"),
        ha_device_name=device.get("ha_device_name") or device.get("name"),
        area_id=device.get("area_id"),
        area_name=device.get("area_name"),
        entity_id=device.get("entity_id"),
        match_confidence=confidence,
    )
