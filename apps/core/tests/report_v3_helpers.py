"""Helpers for report tests after the v3 decision-only contract."""

from __future__ import annotations

from typing import Any

from zigbeelens.schemas import ReportDetail, ReportDomainDetails


def _domain(detail: ReportDetail | dict[str, Any]) -> ReportDomainDetails | dict[str, Any]:
    if isinstance(detail, dict):
        return detail.get("domain_details") or {}
    domain = detail.domain_details
    if isinstance(domain, ReportDomainDetails):
        return domain
    if isinstance(domain, dict):
        return domain
    return {}


def _domain_list(domain: ReportDomainDetails | dict[str, Any], key: str):
    if isinstance(domain, ReportDomainDetails):
        return getattr(domain, key) or []
    return domain.get(key) or []


def report_networks(detail: ReportDetail | dict[str, Any]):
    networks = _domain_list(_domain(detail), "networks")
    if networks:
        return networks
    if isinstance(detail, dict):
        return detail.get("networks") or []
    return detail.networks


def report_devices(detail: ReportDetail | dict[str, Any]):
    devices = _domain_list(_domain(detail), "devices")
    if devices:
        return devices
    if isinstance(detail, dict):
        return detail.get("devices") or []
    return detail.devices


def report_device_details(detail: ReportDetail | dict[str, Any]):
    details = _domain_list(_domain(detail), "device_details")
    if details:
        return details
    if isinstance(detail, dict):
        return detail.get("device_details") or []
    return detail.device_details


def report_router_risks(detail: ReportDetail | dict[str, Any]):
    risks = _domain_list(_domain(detail), "router_risks")
    if risks:
        return risks
    if isinstance(detail, dict):
        return detail.get("router_risks") or []
    return detail.router_risks


def report_timeline(detail: ReportDetail | dict[str, Any]):
    if isinstance(detail, dict):
        return detail.get("events_or_timeline") or detail.get("timeline") or []
    if detail.events_or_timeline:
        return detail.events_or_timeline
    return detail.timeline


def report_active_incidents(detail: ReportDetail | dict[str, Any]):
    """Active (non-resolved) incidents from the canonical incidents list."""
    if isinstance(detail, dict):
        incidents = detail.get("incidents") or detail.get("active_incidents") or []
        out = []
        for inc in incidents:
            status = inc.get("status") if isinstance(inc, dict) else getattr(inc, "status", None)
            value = getattr(status, "value", status)
            if value != "resolved":
                out.append(inc)
        return out
    return [inc for inc in detail.incidents if str(inc.status.value) != "resolved"]
