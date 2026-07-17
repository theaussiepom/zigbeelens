"""Exact incident ↔ network identity helpers (Track 3F).

Network associations are factual. Dedup-key parsing is used only for
deterministic backfill of known identity formats; runtime report scoping
reads the normalized incident_networks relation.
"""

from __future__ import annotations

from typing import Iterable

from zigbeelens.diagnostics.incidents.models import IncidentType

_SINGLE_NETWORK_TYPES = frozenset(
    {
        IncidentType.bridge_offline.value,
        IncidentType.network_wide_instability.value,
        IncidentType.correlated_device_unavailability.value,
        IncidentType.stale_reporting_cluster.value,
        IncidentType.low_battery_cluster.value,
        IncidentType.interview_failure.value,
        IncidentType.unknown_pattern.value,
    }
)

_DEVICE_NETWORK_TYPES = frozenset(
    {
        IncidentType.single_device_unavailable.value,
        IncidentType.router_risk.value,
    }
)


def network_ids_from_dedup_key(
    dedup_key: str | None,
    *,
    known_network_ids: Iterable[str],
) -> tuple[str, ...]:
    """Parse exact network IDs from a known dedup_key format.

    Returns only identities that match a known network id exactly.
    Ambiguous or unrecognised keys yield an empty tuple (do not invent).
    """
    if not dedup_key or ":" not in dedup_key:
        return ()
    known = {nid for nid in known_network_ids if nid}
    if not known:
        return ()

    incident_type, _, remainder = dedup_key.partition(":")
    if not remainder:
        return ()

    if incident_type == IncidentType.multi_network_instability.value:
        # Format: multi_network_instability:n1,n2,... (sorted at write time)
        candidates = [part for part in remainder.split(",") if part]
        matched = [nid for nid in candidates if nid in known]
        # Require every candidate segment to be a known network — otherwise
        # identity is not fully proven (e.g. renamed/removed network).
        if len(matched) != len(candidates):
            return ()
        return tuple(sorted(set(matched)))

    if incident_type in _SINGLE_NETWORK_TYPES:
        if remainder in known:
            return (remainder,)
        return ()

    if incident_type in _DEVICE_NETWORK_TYPES:
        # Format: type:network_id:ieee — network_id may itself contain characters
        # but never ':' in ZigbeeLens network ids. Prefer longest known match
        # that is an exact prefix before the final ':ieee' segment.
        best: str | None = None
        for network_id in known:
            prefix = f"{network_id}:"
            if remainder.startswith(prefix) and remainder[len(prefix) :]:
                if best is None or len(network_id) > len(best):
                    best = network_id
        return (best,) if best else ()

    return ()


def backfill_incident_networks_from_dedup_keys(conn) -> int:
    """Insert proven multi-network dedup associations. Idempotent.

    Single-network and device forms are handled in migration SQL. Multi-network
    keys need Python parsing so comma-separated IDs stay exact.
    """
    network_ids = [row[0] for row in conn.execute("SELECT id FROM networks").fetchall()]
    cur = conn.execute(
        """
        SELECT id, dedup_key FROM incidents
        WHERE incident_type = ?
        """,
        (IncidentType.multi_network_instability.value,),
    )
    inserted = 0
    for row in cur.fetchall():
        incident_id = row[0] if not hasattr(row, "keys") else row["id"]
        dedup_key = row[1] if not hasattr(row, "keys") else row["dedup_key"]
        for network_id in network_ids_from_dedup_key(
            dedup_key, known_network_ids=network_ids
        ):
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO incident_networks (incident_id, network_id)
                VALUES (?, ?)
                """,
                (incident_id, network_id),
            )
            if conn.total_changes > before:
                inserted += 1
    return inserted
