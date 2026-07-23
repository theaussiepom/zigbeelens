"""Optional Home Assistant area/device enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zigbeelens.schemas import (
    HOME_ASSISTANT_ENRICHMENT_CONTRACT_VERSION,
    HomeAssistantEnrichmentDeviceV1,
    HomeAssistantEnrichmentRequestV1,
    HomeAssistantEnrichmentResultV1,
)
from zigbeelens.storage.repository import Repository, utc_now_iso


@dataclass
class MatchResult:
    network_id: str
    ieee_address: str
    ha_device_id: str
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


def apply_ha_enrichment(
    repo: Repository,
    request: HomeAssistantEnrichmentRequestV1,
) -> HomeAssistantEnrichmentResultV1:
    """Accept one fully validated complete snapshot and replace stored enrichment."""
    if not isinstance(request, HomeAssistantEnrichmentRequestV1):
        raise TypeError("request must be HomeAssistantEnrichmentRequestV1")

    # Resolve every row before opening the replacement transaction. An absent
    # exact Core identity is factual unmatched input, not a validation failure.
    matches: list[MatchResult] = []
    unmatched = 0
    for device in request.devices:
        match = _match_device(repo, device)
        if match is None:
            unmatched += 1
        else:
            matches.append(match)

    last_push_at = utc_now_iso()
    result = HomeAssistantEnrichmentResultV1(
        home_assistant_enrichment_contract_version=(
            HOME_ASSISTANT_ENRICHMENT_CONTRACT_VERSION
        ),
        submitted=len(request.devices),
        matched=len(matches),
        unmatched=unmatched,
        ambiguous=0,
        stored=len(matches),
        last_push_at=last_push_at,
    )
    with repo.transaction():
        repo.replace_ha_device_enrichment(matches, updated_at=last_push_at)
        repo.update_ha_enrichment_status(
            enabled=True,
            matched_devices=len(matches),
            source="homeassistant",
            last_push_at=last_push_at,
        )

    return result


def clear_ha_enrichment(repo: Repository) -> None:
    with repo.transaction():
        repo.clear_ha_device_enrichment()
        repo.update_ha_enrichment_status(
            enabled=False,
            matched_devices=0,
            source=None,
            last_push_at=None,
        )


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


def _match_device(
    repo: Repository,
    device: HomeAssistantEnrichmentDeviceV1,
) -> MatchResult | None:
    """Match exact V1 identity only; user-assigned names are metadata, never identity."""
    if repo.get_device(device.network_id, device.ieee_address) is None:
        return None
    return _result(device)


def _result(device: HomeAssistantEnrichmentDeviceV1) -> MatchResult:
    return MatchResult(
        network_id=device.network_id,
        ieee_address=device.ieee_address,
        ha_device_id=device.ha_device_id,
        ha_device_name=device.ha_device_name,
        area_id=device.area_id,
        area_name=device.area_name,
        entity_id=device.entity_id,
        match_confidence="high",
    )
