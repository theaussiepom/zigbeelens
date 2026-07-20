"""Build the redacted summary payload for the native companion panel.

This is a pure, side-effect-free transform of coordinator data into the small
dict the panel frontend renders. It must never include secrets (MQTT
credentials, passwords, tokens, or raw broker URLs) — only safe summary counts,
states, and the user-configured Core URL.

Shared Decision fields are projected from the Dashboard payload only when the
exact companion decision contract v2 is available. Titles/summaries/priority
labels are passed through unchanged from Core.
"""

from __future__ import annotations

from typing import Any

from .compatibility import nonneg_int_not_bool
from .coordinator import ZigbeeLensCoordinatorData
from .core_origin import InvalidCoreOrigin, canonicalize_core_origin

MAX_COMPANION_INVESTIGATION_PRIORITIES = 3


def _safe_core_url(core_url: str) -> str:
    try:
        return canonicalize_core_origin(core_url)
    except InvalidCoreOrigin:
        return ""


def _safe_int(value: Any, default: int | None = None) -> int | None:
    parsed = nonneg_int_not_bool(value)
    return parsed if parsed is not None else default


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
        "core_url": _safe_core_url(core_url),
        "core_version": None,
        "overall_decision_status": None,
        "decision_summary": None,
        "active_incident_count": None,
        "watching_incident_count": None,
        "network_count": None,
        "device_count": None,
        "unavailable_devices": None,
        "router_risks": None,
        "collector_connected": False,
        "last_update": None,
        "mock_mode": False,
        "networks": [],
        "error": last_exception if not connected else None,
        "shared_decisions_available": False,
        "decision_contract_version": 0,
        "decision_contract_compatible": False,
        "core_update_required": False,
        "core_version_compatible": None,
        "investigation_priority_count": None,
        "investigation_priorities": [],
        "more_investigation_priority_count": None,
        "data_coverage_warning_count": None,
    }

    if data is None:
        return summary

    dashboard = data.dashboard or {}
    health = data.health or {}
    collector = health.get("collector") or {}

    summary["core_version"] = data.core_version or str(health.get("version") or "") or None
    summary["shared_decisions_available"] = bool(data.shared_decisions_available)
    summary["decision_contract_version"] = int(data.decision_contract_version or 0)
    summary["decision_contract_compatible"] = bool(data.shared_decisions_available)
    summary["core_update_required"] = bool(
        connected
        and data is not None
        and not data.shared_decisions_available
        and data.core_version_compatible is not False
    )
    summary["core_version_compatible"] = data.core_version_compatible

    summary["collector_connected"] = bool(data.collector_connected)
    summary["mock_mode"] = bool(health.get("mock_mode"))
    summary["last_update"] = dashboard.get("generated_at") or collector.get("last_message_at")

    decision_mode = data.shared_decisions_available is True
    if decision_mode:
        summary["active_incident_count"] = _safe_int(dashboard.get("active_incident_count"))
        summary["watching_incident_count"] = _safe_int(dashboard.get("watching_incident_count"))
        summary["network_count"] = _safe_int(dashboard.get("network_count"))
        summary["device_count"] = _safe_int(dashboard.get("device_count"))
        summary["unavailable_devices"] = _safe_int(dashboard.get("unavailable_device_count"))
        router_risks = dashboard.get("router_risks")
        summary["router_risks"] = (
            len(router_risks) if isinstance(router_risks, list) else None
        )
    valid_priorities: list[dict[str, Any]] = []
    projected_priorities: list[dict[str, Any]] = []
    if decision_mode:
        decision_summary = dashboard.get("decision_summary")
        if isinstance(decision_summary, dict):
            summary["decision_summary"] = {
                "subject_count": _safe_int(decision_summary.get("subject_count")),
                "overall_status": _optional_str(decision_summary.get("overall_status")),
                "highest_priority": _optional_str(decision_summary.get("highest_priority")),
                "status_counts": (
                    decision_summary.get("status_counts")
                    if isinstance(decision_summary.get("status_counts"), dict)
                    else {}
                ),
                "priority_counts": (
                    decision_summary.get("priority_counts")
                    if isinstance(decision_summary.get("priority_counts"), dict)
                    else {}
                ),
                "coverage_warning_count": _safe_int(
                    decision_summary.get("coverage_warning_count")
                ),
            }
            summary["overall_decision_status"] = summary["decision_summary"]["overall_status"]
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

    networks: list[dict[str, Any]] = []
    if decision_mode:
        for net in dashboard.get("networks") or []:
            if not isinstance(net, dict):
                continue
            network_id = net.get("id")
            decision = net.get("decision") if isinstance(net.get("decision"), dict) else {}
            decision_summary = (
                net.get("decision_summary") if isinstance(net.get("decision_summary"), dict) else {}
            )
            net_row: dict[str, Any] = {
                "id": network_id,
                "name": net.get("name") or network_id,
                "bridge_state": str(net.get("bridge_state") or "unknown"),
                "device_count": _safe_int(net.get("device_count")),
                "unavailable_devices": _safe_int(net.get("unavailable_count")),
                "decision_status": (
                    _optional_str(decision.get("status"))
                    or _optional_str(decision_summary.get("overall_status"))
                ),
                "investigation_priority_count": (
                    per_network_priority_counts.get(str(network_id), 0)
                    if isinstance(network_id, str)
                    else 0
                ),
            }
            networks.append(net_row)
    summary["networks"] = networks
    return summary
