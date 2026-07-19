"""Factual active-incident severity for network and report projections.

Describes open/watching incident rows only. Mirrors current-finding precedence:
open before watching, then stored severity rank. Resolved rows never participate.
Bridge health and device health flags never invent an active incident severity.
"""

from __future__ import annotations

from typing import Any, Mapping

from zigbeelens.schemas import Incident, IncidentStatus, Severity

_SEVERITY_RANK = {
    Severity.critical.value: 0,
    Severity.incident.value: 1,
    Severity.watch.value: 2,
    Severity.healthy.value: 3,
}


def _row_lifecycle(row: dict[str, Any] | Incident) -> str:
    if isinstance(row, Incident):
        return row.status.value
    return str(row.get("lifecycle_state") or "")


def _row_severity(row: dict[str, Any] | Incident) -> str:
    if isinstance(row, Incident):
        return row.severity.value
    return str(row.get("severity") or Severity.watch.value)


def _row_id(row: dict[str, Any] | Incident) -> str:
    if isinstance(row, Incident):
        return row.id
    return str(row["id"])


def pick_active_incident_severity(
    active_rows: list[dict[str, Any]] | list[Incident] | tuple,
) -> Severity | None:
    """Return stored severity of the top current active incident, or None."""
    rows = list(active_rows)
    if not rows:
        return None
    top = sorted(
        rows,
        key=lambda row: (
            0 if _row_lifecycle(row) == IncidentStatus.open.value else 1,
            _SEVERITY_RANK.get(_row_severity(row), 9),
        ),
    )[0]
    return Severity(_row_severity(top))


def active_severity_by_network_id(
    active_rows: list[dict[str, Any]] | list[Incident] | tuple,
    networks_by_incident_id: Mapping[str, tuple[str, ...]],
    network_ids: tuple[str, ...] | list[str],
) -> dict[str, Severity]:
    """Per-network current active severity from incident_networks membership."""
    result: dict[str, Severity] = {}
    for network_id in network_ids:
        rows_for_net = [
            row
            for row in active_rows
            if network_id in networks_by_incident_id.get(_row_id(row), ())
        ]
        severity = pick_active_incident_severity(rows_for_net)
        if severity is not None:
            result[network_id] = severity
    return result


def mock_networks_by_incident_id(
    incidents: list[Incident],
) -> dict[str, tuple[str, ...]]:
    return {inc.id: tuple(inc.network_ids) for inc in incidents}
