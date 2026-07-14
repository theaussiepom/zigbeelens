"""Build the redacted summary payload for the native companion panel.

This is a pure, side-effect-free transform of coordinator data into the small
dict the panel frontend renders. It must never include secrets (MQTT
credentials, passwords, tokens, or raw broker URLs) — only safe summary counts,
states, and the user-configured Core URL.

Shared Decision fields are projected from the Dashboard payload only when the
exact companion decision contract is available. Titles/summaries/priority labels
are passed through unchanged from Core.
"""

from __future__ import annotations

from typing import Any

from .coordinator import ZigbeeLensCoordinatorData

MAX_COMPANION_INVESTIGATION_PRIORITIES = 3


def _severity_label(value: Any) -> str:
    """Map Core severity/health values onto the panel's three calm states."""
    text = str(value or "").lower()
    if text in ("healthy", "ok"):
        return "ok"
    if text == "watch":
        return "watch"
    if text in ("incident", "critical"):
        return "incident"
    return "unknown"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _nonempty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _network_name_map(networks: list[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for net in networks:
        if not isinstance(net, dict):
            continue
        nid = _nonempty_str(net.get("id"))
        if not nid:
            continue
        name = _nonempty_str(net.get("name")) or nid
        mapping[nid] = name
    return mapping


def _project_priority(
    raw: Any,
    *,
    network_names: dict[str, str],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    priority = _nonempty_str(raw.get("priority"))
    title = _nonempty_str(raw.get("title"))
    summary = _nonempty_str(raw.get("summary"))
    if not priority or not title or not summary:
        return None
    network_id = _optional_str(raw.get("network_id"))
    if network_id:
        network_name = network_names.get(network_id) or "Network"
    else:
        network_name = "Network"
    item_id = _optional_str(raw.get("id")) or title
    return {
        "id": item_id,
        "priority": priority,
        "title": title,
        "summary": summary,
        "network_id": network_id,
        "network_name": network_name,
        "latest_supporting_evidence_at": _optional_str(raw.get("latest_supporting_evidence_at")),
    }


def _project_priorities(
    dashboard: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (all_valid, projected_capped, coverage_warning_count)."""
    network_names = _network_name_map(list(dashboard.get("networks") or []))
    raw_priorities = dashboard.get("investigation_priorities") or []
    valid: list[dict[str, Any]] = []
    if isinstance(raw_priorities, list):
        for item in raw_priorities:
            projected = _project_priority(item, network_names=network_names)
            if projected is not None:
                valid.append(projected)
    projected = valid[:MAX_COMPANION_INVESTIGATION_PRIORITIES]
    warnings = dashboard.get("data_coverage_warnings") or []
    warning_count = 0
    if isinstance(warnings, list):
        warning_count = sum(1 for item in warnings if isinstance(item, dict))
    return valid, projected, warning_count


def build_panel_summary(
    data: ZigbeeLensCoordinatorData | None,
    *,
    core_url: str,
    connected: bool,
    last_exception: str | None = None,
) -> dict[str, Any]:
    """Return a redacted summary dict for the companion panel frontend."""
    summary: dict[str, Any] = {
        "connected": bool(connected and data is not None),
        "core_url": core_url,
        "core_version": None,
        "overall_health": "unknown",
        "overall_severity": "unknown",
        "current_finding": None,
        "active_incident_count": 0,
        "watching_incident_count": 0,
        "network_count": 0,
        "device_count": 0,
        "unavailable_devices": 0,
        "router_risks": 0,
        "stale_devices": 0,
        "weak_link_devices": 0,
        "low_battery_devices": 0,
        "collector_connected": False,
        "last_update": None,
        "mock_mode": False,
        "networks": [],
        "error": last_exception if not connected else None,
        "shared_decisions_available": False,
        "decision_contract_version": 0,
        "core_version_compatible": None,
        "investigation_priority_count": 0,
        "investigation_priorities": [],
        "more_investigation_priority_count": 0,
        "data_coverage_warning_count": 0,
    }

    if data is None:
        return summary

    dashboard = data.dashboard or {}
    health = data.health or {}
    snapshot = dashboard.get("health_snapshot") or {}
    collector = health.get("collector") or {}

    summary["core_version"] = data.core_version or str(health.get("version") or "") or None
    summary["shared_decisions_available"] = bool(data.shared_decisions_available)
    summary["decision_contract_version"] = int(data.decision_contract_version or 0)
    summary["core_version_compatible"] = data.core_version_compatible
    summary["overall_severity"] = _severity_label(dashboard.get("overall_severity"))
    summary["overall_health"] = summary["overall_severity"]

    finding = dashboard.get("current_finding") or {}
    summary["current_finding"] = finding.get("summary")

    summary["active_incident_count"] = _safe_int(dashboard.get("active_incident_count"))
    summary["watching_incident_count"] = _safe_int(dashboard.get("watching_incident_count"))
    summary["network_count"] = _safe_int(
        snapshot.get("network_count"), default=len(dashboard.get("networks") or [])
    )
    summary["device_count"] = _safe_int(snapshot.get("device_count"))
    summary["unavailable_devices"] = _safe_int(snapshot.get("unavailable_count"))
    summary["router_risks"] = len(dashboard.get("router_risks") or [])
    summary["stale_devices"] = len(dashboard.get("stale_devices") or [])
    summary["weak_link_devices"] = len(dashboard.get("weak_links") or [])
    summary["low_battery_devices"] = len(dashboard.get("low_batteries") or [])
    summary["collector_connected"] = bool(data.collector_connected)
    summary["mock_mode"] = bool(health.get("mock_mode"))
    summary["last_update"] = dashboard.get("generated_at") or collector.get("last_message_at")

    decision_mode = (
        data.shared_decisions_available is True and data.core_version_compatible is True
    )
    valid_priorities: list[dict[str, Any]] = []
    projected_priorities: list[dict[str, Any]] = []
    if decision_mode:
        valid_priorities, projected_priorities, warning_count = _project_priorities(dashboard)
        summary["investigation_priority_count"] = len(valid_priorities)
        summary["investigation_priorities"] = projected_priorities
        summary["more_investigation_priority_count"] = max(
            len(valid_priorities) - len(projected_priorities), 0
        )
        summary["data_coverage_warning_count"] = warning_count

    per_network_priority_counts: dict[str, int] = {}
    for item in valid_priorities:
        nid = item.get("network_id")
        if isinstance(nid, str) and nid:
            per_network_priority_counts[nid] = per_network_priority_counts.get(nid, 0) + 1

    router_risks = dashboard.get("router_risks") or []
    networks: list[dict[str, Any]] = []
    for net in dashboard.get("networks") or []:
        if not isinstance(net, dict):
            continue
        network_id = net.get("id")
        per_network_router_risks = len(
            [r for r in router_risks if isinstance(r, dict) and r.get("network_id") == network_id]
        )
        network_health = net.get("health") or {}
        net_row: dict[str, Any] = {
            "id": network_id,
            "name": net.get("name") or network_id,
            "bridge_state": str(net.get("bridge_state") or "unknown"),
            "device_count": _safe_int(net.get("device_count")),
            "unavailable_devices": _safe_int(net.get("unavailable_count")),
            "router_risks": per_network_router_risks,
            "health": _severity_label(
                net.get("incident_state")
                or (network_health.get("severity") if isinstance(network_health, dict) else None)
            ),
            "investigation_priority_count": (
                per_network_priority_counts.get(str(network_id), 0)
                if isinstance(network_id, str) and decision_mode
                else 0
            ),
        }
        networks.append(net_row)
    summary["networks"] = networks
    return summary
