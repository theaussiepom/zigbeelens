"""Parse Zigbee2MQTT network map responses defensively."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from zigbeelens.mqtt.payload_utils import redact_payload_text


@dataclass
class ParsedTopologyNode:
    ieee_address: str
    friendly_name: str | None
    node_type: str
    depth: int | None = None
    lqi: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTopologyLink:
    source_ieee: str
    target_ieee: str
    source_type: str | None = None
    target_type: str | None = None
    linkquality: int | None = None
    depth: int | None = None
    relationship: str | None = None
    # Number of route-table entries reported on this link (Zigbee2MQTT raw
    # maps attach the source's routes whose next hop is the target). None
    # means the payload carried no routes information — unknown, not zero.
    route_count: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTopology:
    nodes: list[ParsedTopologyNode] = field(default_factory=list)
    links: list[ParsedTopologyLink] = field(default_factory=list)
    router_count: int = 0
    end_device_count: int = 0
    link_count: int = 0
    raw_redacted: dict[str, Any] = field(default_factory=dict)


def _normalize_ieee(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if not text.startswith("0x"):
        text = f"0x{text}"
    return text


def _link_endpoint_ieee(link_raw: dict[str, Any], *keys: str) -> str | None:
    """Extract an endpoint IEEE from the several shapes Z2M has used.

    Raw network maps report both a nested object (``source: {ieeeAddr: …}``)
    and deprecated flat fields (``sourceIeeeAddr``).
    """
    for key in keys:
        value = link_raw.get(key)
        if isinstance(value, dict):
            value = value.get("ieeeAddr") or value.get("ieee_address")
        ieee = _normalize_ieee(value)
        if ieee:
            return ieee
    return None


def _unwrap_networkmap_envelope(parsed: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a Z2M bridge response envelope if present.

    Real ``bridge/response/networkmap`` payloads look like
    ``{"data": {"type": "raw", "value": {"nodes": …, "links": …}}, "status": "ok"}``.
    Bare maps (``{"nodes": …, "links": …}``) are returned unchanged.
    """
    if "nodes" in parsed or "links" in parsed:
        return parsed
    data = parsed.get("data")
    if isinstance(data, dict):
        value = data.get("value")
        if isinstance(value, dict):
            return value
    return parsed


def _node_type(raw: dict[str, Any]) -> str:
    for key in ("type", "device_type"):
        if raw.get(key):
            return str(raw[key])
    return "Unknown"


# Neighbour-table relationship codes used by zigbee-herdsman raw maps.
_RELATIONSHIP_LABELS = {
    "0": "Parent",
    "1": "Child",
    "2": "Sibling",
    "3": "Unknown relationship",
    "4": "Previous child",
}


def _relationship_label(value: Any) -> str | None:
    """Return a readable neighbour relationship, keeping unknown codes as-is."""
    if value is None:
        return None
    text = str(value)
    return _RELATIONSHIP_LABELS.get(text, text)


def _route_count(link_raw: dict[str, Any]) -> int | None:
    """Count route-table entries on a link; None when routes are not reported."""
    routes = link_raw.get("routes")
    if isinstance(routes, list):
        return len(routes)
    return None


def parse_networkmap_payload(payload: bytes | str | dict[str, Any]) -> ParsedTopology:
    if isinstance(payload, (bytes, bytearray)):
        text = payload.decode("utf-8", errors="replace")
        parsed, _ = _safe_json(text)
    elif isinstance(payload, str):
        parsed, _ = _safe_json(payload)
    else:
        parsed = payload

    if not isinstance(parsed, dict):
        return ParsedTopology(raw_redacted={"error": "invalid_payload"})

    parsed = _unwrap_networkmap_envelope(parsed)

    redacted_text = redact_payload_text(
        json.dumps(parsed).encode("utf-8") if not isinstance(payload, (bytes, str)) else payload
    )
    try:
        raw_redacted = json.loads(redacted_text) if redacted_text else {}
    except json.JSONDecodeError:
        raw_redacted = {"payload": redacted_text[:500]}

    nodes: list[ParsedTopologyNode] = []
    links: list[ParsedTopologyLink] = []
    node_types: dict[str, str] = {}

    nodes_section = parsed.get("nodes")
    if isinstance(nodes_section, dict):
        for ieee_key, node_raw in nodes_section.items():
            if not isinstance(node_raw, dict):
                continue
            ieee = _normalize_ieee(node_raw.get("ieee_address") or ieee_key)
            if not ieee:
                continue
            node_type = _node_type(node_raw)
            node_types[ieee] = node_type
            nodes.append(
                ParsedTopologyNode(
                    ieee_address=ieee,
                    friendly_name=node_raw.get("friendly_name") or node_raw.get("friendlyName"),
                    node_type=node_type,
                    depth=_int_or_none(node_raw.get("depth")),
                    lqi=_int_or_none(node_raw.get("lqi") or node_raw.get("linkquality")),
                    raw_json=node_raw,
                )
            )
    elif isinstance(nodes_section, list):
        for node_raw in nodes_section:
            if not isinstance(node_raw, dict):
                continue
            ieee = _normalize_ieee(
                node_raw.get("ieee_address")
                or node_raw.get("ieeeAddress")
                or node_raw.get("ieeeAddr")
            )
            if not ieee:
                continue
            node_type = _node_type(node_raw)
            node_types[ieee] = node_type
            nodes.append(
                ParsedTopologyNode(
                    ieee_address=ieee,
                    friendly_name=node_raw.get("friendly_name") or node_raw.get("friendlyName"),
                    node_type=node_type,
                    depth=_int_or_none(node_raw.get("depth")),
                    lqi=_int_or_none(node_raw.get("lqi") or node_raw.get("linkquality")),
                    raw_json=node_raw,
                )
            )

    links_section = parsed.get("links") or parsed.get("routes") or []
    if isinstance(links_section, list):
        for link_raw in links_section:
            if not isinstance(link_raw, dict):
                continue
            source = _link_endpoint_ieee(
                link_raw, "source", "sourceIeeeAddress", "sourceIeeeAddr"
            )
            target = _link_endpoint_ieee(
                link_raw, "target", "targetIeeeAddress", "targetIeeeAddr"
            )
            if not source or not target:
                continue
            links.append(
                ParsedTopologyLink(
                    source_ieee=source,
                    target_ieee=target,
                    source_type=node_types.get(source) or link_raw.get("source_type"),
                    target_type=node_types.get(target) or link_raw.get("target_type"),
                    linkquality=_int_or_none(link_raw.get("linkquality") or link_raw.get("lqi")),
                    depth=_int_or_none(link_raw.get("depth")),
                    relationship=_relationship_label(link_raw.get("relationship")),
                    route_count=_route_count(link_raw),
                    raw_json=link_raw,
                )
            )

    router_count = sum(1 for n in nodes if n.node_type.lower() in ("router", "coordinator"))
    end_device_count = sum(1 for n in nodes if "end" in n.node_type.lower())

    return ParsedTopology(
        nodes=nodes,
        links=links,
        router_count=router_count,
        end_device_count=end_device_count,
        link_count=len(links),
        raw_redacted=raw_redacted if isinstance(raw_redacted, dict) else {"payload": raw_redacted},
    )


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data, None
        return None, "expected_object"
    except json.JSONDecodeError as err:
        return None, str(err)
