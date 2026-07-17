"""Compose immutable NetworkEvidenceContext values (Track 3G).

Loads each required raw evidence collection once via bounded bulk repository
reads, then freezes one context per network. Supplied device rows are used only
when the caller certifies they are the complete network inventory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Mapping

from zigbeelens.decisions.availability_event_groups import (
    shared_availability_event_groups_for_network,
)
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.model_pattern import observed_model_patterns_for_network
from zigbeelens.decisions.router_area import observed_router_areas_for_network
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.decisions.topology_facts import build_network_topology_facts
from zigbeelens.services.network_evidence import (
    NetworkEvidenceCapability,
    NetworkEvidenceContext,
    NetworkEvidenceRequirements,
    _copy_device_row,
    _copy_network_row,
    _freeze_derived,
    _freeze_row,
    _freeze_rows,
    _freeze_rows_by_key,
    expand_requirements,
)
from zigbeelens.storage.repository import DeviceRow, NetworkRow, Repository
from zigbeelens.topology.device_compare import (
    MAX_SNAPSHOT_HISTORY,
    load_device_snapshot_history_network_context,
)
from zigbeelens.topology.device_stats import aggregate_device_stats
from zigbeelens.topology.history import (
    aggregate_historical_evidence,
    aggregate_last_known_links,
)
from zigbeelens.topology.investigations import (
    aggregate_investigations,
    issue_device_ieees_from_state,
)
from zigbeelens.topology.passive_hints import (
    PASSIVE_HINT_LOOKBACK_DAYS,
    aggregate_passive_hints,
)


def _require_aware(reference_now: datetime) -> datetime:
    if reference_now.tzinfo is None:
        raise ValueError("reference_now must be timezone-aware")
    return reference_now.astimezone(timezone.utc)


def _needs_snapshot_window(requirements: NetworkEvidenceRequirements) -> bool:
    return bool(
        requirements
        & {
            NetworkEvidenceCapability.snapshot_history,
            NetworkEvidenceCapability.historical_links,
            NetworkEvidenceCapability.last_known_links,
            NetworkEvidenceCapability.device_stats,
            NetworkEvidenceCapability.passive_hints,
        }
    )


def _needs_latest_topology(requirements: NetworkEvidenceRequirements) -> bool:
    return bool(
        requirements
        & {
            NetworkEvidenceCapability.latest_topology,
            NetworkEvidenceCapability.snapshot_history,
            NetworkEvidenceCapability.historical_links,
            NetworkEvidenceCapability.last_known_links,
            NetworkEvidenceCapability.passive_hints,
            NetworkEvidenceCapability.device_stats,
            NetworkEvidenceCapability.investigations,
            NetworkEvidenceCapability.topology_facts,
            NetworkEvidenceCapability.coverage,
            NetworkEvidenceCapability.router_areas,
        }
    )


def _needs_availability_obs(requirements: NetworkEvidenceRequirements) -> bool:
    return NetworkEvidenceCapability.availability_observations in requirements


def _needs_devices(requirements: NetworkEvidenceRequirements) -> bool:
    return NetworkEvidenceCapability.devices in requirements


def _graph_counts_from_context_evidence(
    *,
    latest_links: tuple[Mapping[str, Any], ...] | None,
    historical: Mapping[str, Any] | None,
    last_known: Mapping[str, Any] | None,
    passive: Mapping[str, Any] | None,
) -> dict[str, Any]:
    links = list(latest_links or ())
    latest_neighbor_pairs = {
        tuple(sorted((str(link["source_ieee"]).lower(), str(link["target_ieee"]).lower())))
        for link in links
        if str(link.get("source_ieee") or "").lower()
        != str(link.get("target_ieee") or "").lower()
    }
    latest_route_edges = sum(
        1
        for link in links
        if link.get("route_count") is not None and int(link["route_count"]) > 0
    )
    historical_neighbors = list((historical or {}).get("historical_neighbors") or [])
    historical_routes = list((historical or {}).get("historical_routes") or [])
    last_known_links = list((last_known or {}).get("last_known_links") or [])
    passive_available = (passive or {}).get("available_count")
    passive_hints = list((passive or {}).get("hints") or [])
    return {
        "latest_snapshot_neighbor_edges": len(latest_neighbor_pairs),
        "latest_snapshot_route_edges": latest_route_edges,
        "historical_neighbor_edges": len(historical_neighbors),
        "historical_route_edges": len(historical_routes),
        "recent_missing_link_count_total": len(historical_neighbors) + len(historical_routes),
        "last_known_link_count": len(last_known_links),
        "passive_hint_count_available": passive_available,
        "passive_hint_count_total": len(passive_hints),
    }


def compose_network_evidence_contexts(
    repo: Repository,
    network_ids: list[str] | tuple[str, ...],
    *,
    reference_now: datetime,
    requirements_by_network: Mapping[str, NetworkEvidenceRequirements],
    network_rows_by_id: Mapping[str, NetworkRow] | None = None,
    complete_device_rows_by_network: Mapping[
        str, list[DeviceRow] | tuple[DeviceRow, ...]
    ]
    | None = None,
    stale_after_hours: int | None = None,
) -> Mapping[str, NetworkEvidenceContext]:
    """Build one immutable NetworkEvidenceContext per network ID.

    ``complete_device_rows_by_network`` may be supplied only when the caller
    certifies that each list is the complete factual inventory for that network.
    Subject/response subsets must not be passed here.
    """
    reference_now = _require_aware(reference_now)
    ordered_ids = list(dict.fromkeys(nid for nid in network_ids if nid))
    if not ordered_ids:
        return MappingProxyType({})

    reqs: dict[str, NetworkEvidenceRequirements] = {}
    for network_id in ordered_ids:
        req = expand_requirements(
            frozenset(requirements_by_network.get(network_id, frozenset()))
        )
        reqs[network_id] = req
        if complete_device_rows_by_network and network_id in complete_device_rows_by_network:
            for row in complete_device_rows_by_network[network_id]:
                if row.network_id != network_id:
                    raise ValueError(
                        f"DeviceRow network_id {row.network_id!r} does not match "
                        f"expected {network_id!r}"
                    )

    networks_needing_devices = [nid for nid in ordered_ids if _needs_devices(reqs[nid])]
    networks_needing_latest = [
        nid for nid in ordered_ids if _needs_latest_topology(reqs[nid])
    ]
    networks_needing_window = [
        nid for nid in ordered_ids if _needs_snapshot_window(reqs[nid])
    ]
    networks_needing_topo = list(
        dict.fromkeys([*networks_needing_latest, *networks_needing_window])
    )
    networks_needing_avail = [
        nid for nid in ordered_ids if _needs_availability_obs(reqs[nid])
    ]
    networks_needing_earliest = [
        nid
        for nid in ordered_ids
        if NetworkEvidenceCapability.earliest_availability in reqs[nid]
    ]
    networks_needing_ha = [
        nid for nid in ordered_ids if NetworkEvidenceCapability.ha_areas in reqs[nid]
    ]

    if network_rows_by_id is None:
        loaded_networks = {
            row.id: _copy_network_row(row)
            for row in repo.get_networks_by_ids(ordered_ids)
        }
    else:
        loaded_networks = {
            nid: _copy_network_row(row) for nid, row in network_rows_by_id.items()
        }

    device_map: dict[str, list[DeviceRow]] = {}
    if networks_needing_devices:
        missing_device_networks = [
            nid
            for nid in networks_needing_devices
            if complete_device_rows_by_network is None
            or nid not in complete_device_rows_by_network
        ]
        bulk_devices = (
            repo.list_devices_for_networks(missing_device_networks)
            if missing_device_networks
            else {}
        )
        for nid in networks_needing_devices:
            if (
                complete_device_rows_by_network is not None
                and nid in complete_device_rows_by_network
            ):
                device_map[nid] = [
                    _copy_device_row(row)
                    for row in complete_device_rows_by_network[nid]
                ]
            else:
                device_map[nid] = [
                    _copy_device_row(row) for row in bulk_devices.get(nid, [])
                ]

    snapshots_by_network: dict[str, list[dict[str, Any]]] = {}
    if networks_needing_topo:
        snapshots_by_network = repo.list_topology_snapshots_for_networks(
            networks_needing_topo
        )

    snapshot_ids_for_links: list[str] = []
    snapshot_ids_for_nodes: list[str] = []
    latest_by_network: dict[str, dict[str, Any] | None] = {}
    for network_id in networks_needing_topo:
        snapshots = snapshots_by_network.get(network_id, [])
        latest = next(
            (dict(snap) for snap in snapshots if snap.get("status") == "complete"),
            None,
        )
        latest_by_network[network_id] = latest
        needs_window = network_id in networks_needing_window
        link_ids: list[str] = []
        if needs_window:
            for snap in snapshots:
                if snap.get("status") == "complete":
                    sid = str(snap["snapshot_id"])
                    if sid not in link_ids:
                        link_ids.append(sid)
        elif latest is not None:
            link_ids = [str(latest["snapshot_id"])]
        node_ids = link_ids[:MAX_SNAPSHOT_HISTORY] if needs_window else list(link_ids)
        if latest is not None:
            latest_id = str(latest["snapshot_id"])
            if latest_id not in link_ids:
                link_ids.append(latest_id)
            if latest_id not in node_ids:
                node_ids.append(latest_id)
        for sid in link_ids:
            if sid not in snapshot_ids_for_links:
                snapshot_ids_for_links.append(sid)
        for sid in node_ids:
            if sid not in snapshot_ids_for_nodes:
                snapshot_ids_for_nodes.append(sid)

    links_by_snapshot: dict[str, list[dict[str, Any]]] = {}
    nodes_by_snapshot: dict[str, list[dict[str, Any]]] = {}
    if snapshot_ids_for_links:
        links_by_snapshot = repo.list_topology_links_for_snapshots(snapshot_ids_for_links)
    if snapshot_ids_for_nodes:
        nodes_by_snapshot = repo.list_topology_nodes_for_snapshots(snapshot_ids_for_nodes)

    avail_by_network: dict[str, list[dict[str, Any]]] = {}
    if networks_needing_avail:
        cutoff = (reference_now - timedelta(days=PASSIVE_HINT_LOOKBACK_DAYS)).isoformat()
        avail_by_network = repo.list_availability_changes_for_networks_since(
            networks_needing_avail, cutoff
        )

    earliest_by_network: dict[str, str | None] = {}
    if networks_needing_earliest:
        earliest_by_network = repo.get_earliest_availability_change_at_for_networks(
            networks_needing_earliest
        )

    ha_by_network: dict[str, bool] = {}
    if networks_needing_ha:
        ha_by_network = repo.network_has_usable_ha_area_assignments_for_networks(
            networks_needing_ha
        )

    contexts: dict[str, NetworkEvidenceContext] = {}
    for network_id in ordered_ids:
        requirements = reqs[network_id]
        loaded: set[NetworkEvidenceCapability] = set()
        snapshots = (
            snapshots_by_network.get(network_id)
            if network_id in snapshots_by_network
            else None
        )
        latest = latest_by_network.get(network_id) if snapshots is not None else None
        needs_window = NetworkEvidenceCapability.snapshot_history in requirements or (
            network_id in networks_needing_window
        )
        complete = (
            tuple(
                _freeze_row(snap)
                for snap in (snapshots or [])
                if snap.get("status") == "complete"
            )
            if snapshots is not None and needs_window
            else (
                tuple([_freeze_row(latest)])
                if snapshots is not None and latest is not None
                else (() if snapshots is not None else None)
            )
        )

        network_links: dict[str, list[dict[str, Any]]] | None = None
        network_nodes: dict[str, list[dict[str, Any]]] | None = None
        latest_nodes: tuple[Mapping[str, Any], ...] | None = None
        latest_links: tuple[Mapping[str, Any], ...] | None = None
        if snapshots is not None:
            network_links = {}
            network_nodes = {}
            relevant_ids = (
                [str(snap["snapshot_id"]) for snap in snapshots]
                if needs_window
                else ([str(latest["snapshot_id"])] if latest is not None else [])
            )
            for sid in relevant_ids:
                if sid in links_by_snapshot:
                    network_links[sid] = [dict(row) for row in links_by_snapshot[sid]]
                if sid in nodes_by_snapshot:
                    network_nodes[sid] = [dict(row) for row in nodes_by_snapshot[sid]]
            if latest is not None:
                latest_id = str(latest["snapshot_id"])
                latest_nodes = _freeze_rows(network_nodes.get(latest_id, []))
                latest_links = _freeze_rows(network_links.get(latest_id, []))
            else:
                latest_nodes = ()
                latest_links = ()
            if NetworkEvidenceCapability.latest_topology in requirements:
                loaded.add(NetworkEvidenceCapability.latest_topology)
            if NetworkEvidenceCapability.snapshot_history in requirements:
                loaded.add(NetworkEvidenceCapability.snapshot_history)

        device_rows_tuple: tuple[DeviceRow, ...] | None = None
        devices_by_ieee: Mapping[str, DeviceRow] | None = None
        if network_id in device_map:
            device_rows_tuple = tuple(device_map[network_id])
            devices_by_ieee = MappingProxyType(
                {row.ieee_address.lower(): row for row in device_rows_tuple}
            )
            loaded.add(NetworkEvidenceCapability.devices)

        availability_tuple: tuple[Mapping[str, Any], ...] | None = None
        if network_id in avail_by_network:
            availability_tuple = _freeze_rows(avail_by_network[network_id])
            loaded.add(NetworkEvidenceCapability.availability_observations)

        earliest_at: str | None = None
        tracking_enabled: bool | None = None
        if NetworkEvidenceCapability.earliest_availability in requirements:
            earliest_at = earliest_by_network.get(network_id)
            tracking_enabled = availability_tracking_enabled_now(
                repo,
                network_id,
                earliest_availability_at=earliest_at,
                devices=device_map.get(network_id),
            )
            loaded.add(NetworkEvidenceCapability.earliest_availability)

        ha_areas: bool | None = None
        if NetworkEvidenceCapability.ha_areas in requirements:
            ha_areas = ha_by_network.get(network_id, False)
            loaded.add(NetworkEvidenceCapability.ha_areas)

        historical: Mapping[str, Any] | None = None
        last_known: Mapping[str, Any] | None = None
        snap_history_ctx: Any | None = None
        if snapshots is not None and network_links is not None:
            snap_list = list(snapshots) if needs_window else (
                [latest] if latest is not None else []
            )
            links_map = {sid: list(rows) for sid, rows in network_links.items()}
            latest_node_rows = [dict(row) for row in (latest_nodes or ())]
            if NetworkEvidenceCapability.historical_links in requirements:
                historical = MappingProxyType(
                    dict(
                        aggregate_historical_evidence(
                            repo,
                            network_id,
                            now=reference_now,
                            snapshots=snap_list,
                            links_by_snapshot_id=links_map,
                            latest_snapshot=latest,
                            latest_nodes=latest_node_rows,
                        )
                    )
                )
                loaded.add(NetworkEvidenceCapability.historical_links)
            if NetworkEvidenceCapability.last_known_links in requirements:
                last_known = MappingProxyType(
                    dict(
                        aggregate_last_known_links(
                            repo,
                            network_id,
                            snapshots=snap_list,
                            links_by_snapshot_id=links_map,
                            latest_snapshot=latest,
                            latest_nodes=latest_node_rows,
                        )
                    )
                )
                loaded.add(NetworkEvidenceCapability.last_known_links)
            if NetworkEvidenceCapability.snapshot_history in requirements:
                snap_history_ctx = load_device_snapshot_history_network_context(
                    repo,
                    network_id,
                    snapshots=snap_list,
                    links_by_snapshot_id=links_map,
                    earliest_availability_at=earliest_at,
                    earliest_availability_supplied=(
                        NetworkEvidenceCapability.earliest_availability in requirements
                    ),
                    devices=list(device_rows_tuple or ()),
                )

        avail_rows = (
            [dict(row) for row in availability_tuple]
            if availability_tuple is not None
            else None
        )
        device_list = list(device_rows_tuple) if device_rows_tuple is not None else None

        passive: Mapping[str, Any] | None = None
        if NetworkEvidenceCapability.passive_hints in requirements:
            passive = MappingProxyType(
                dict(
                    aggregate_passive_hints(
                        repo,
                        network_id,
                        now=reference_now,
                        devices=device_list,
                        availability_rows=avail_rows,
                        snapshots=list(snapshots or []),
                        links_by_snapshot_id={
                            sid: list(rows)
                            for sid, rows in (network_links or {}).items()
                        },
                        latest_snapshot=latest,
                    )
                )
            )
            loaded.add(NetworkEvidenceCapability.passive_hints)

        shared: Any | None = None
        if NetworkEvidenceCapability.shared_availability in requirements:
            shared = _freeze_derived(
                shared_availability_event_groups_for_network(
                    repo,
                    network_id,
                    now=reference_now,
                    devices=device_list,
                    availability_rows=avail_rows,
                )
            )
            loaded.add(NetworkEvidenceCapability.shared_availability)

        models: Any | None = None
        if NetworkEvidenceCapability.model_patterns in requirements:
            models = _freeze_derived(
                observed_model_patterns_for_network(
                    repo,
                    network_id,
                    now=reference_now,
                    devices=device_list,
                    availability_rows=avail_rows,
                )
            )
            loaded.add(NetworkEvidenceCapability.model_patterns)

        routers: Any | None = None
        if NetworkEvidenceCapability.router_areas in requirements:
            devices = list(device_rows_tuple or ())
            issue_ieees = issue_device_ieees_from_state(devices)
            assert historical is not None
            assert last_known is not None
            assert passive is not None
            routers = _freeze_derived(
                observed_router_areas_for_network(
                    repo,
                    network_id,
                    devices=devices,
                    latest_links=[dict(row) for row in (latest_links or ())],
                    history=dict(historical),
                    last_known_links=list(last_known.get("last_known_links") or []),
                    passive_hints=list(passive.get("hints") or []),
                    issue_device_ieees=issue_ieees,
                )
            )
            loaded.add(NetworkEvidenceCapability.router_areas)

        stats: Mapping[str, Any] | None = None
        if NetworkEvidenceCapability.device_stats in requirements:
            stats = MappingProxyType(
                dict(
                    aggregate_device_stats(
                        repo,
                        network_id,
                        now=reference_now,
                        snapshots=list(snapshots or []),
                        links_by_snapshot_id={
                            sid: list(rows)
                            for sid, rows in (network_links or {}).items()
                        },
                        availability_rows=avail_rows,
                    )
                )
            )
            loaded.add(NetworkEvidenceCapability.device_stats)

        investigations: Mapping[str, Any] | None = None
        if NetworkEvidenceCapability.investigations in requirements:
            assert historical is not None
            assert last_known is not None
            assert passive is not None
            assert shared is not None
            assert models is not None
            assert routers is not None
            investigations = MappingProxyType(
                dict(
                    aggregate_investigations(
                        repo,
                        network_id,
                        history=dict(historical),
                        passive_hints=list(passive.get("hints") or []),
                        shared_availability_events=list(shared.groups),
                        observed_router_areas=list(routers.areas),
                        observed_model_patterns=list(models.patterns),
                        last_known_links=list(last_known.get("last_known_links") or []),
                        now=reference_now,
                        devices=device_list,
                        latest_snapshot=latest,
                        latest_nodes=[dict(row) for row in (latest_nodes or ())],
                        latest_links=[dict(row) for row in (latest_links or ())],
                        availability_rows=avail_rows,
                    )
                )
            )
            loaded.add(NetworkEvidenceCapability.investigations)

        topology_facts: Any | None = None
        coverage: Any | None = None
        context_stale = (
            stale_after_hours
            if (
                NetworkEvidenceCapability.topology_facts in requirements
                or NetworkEvidenceCapability.coverage in requirements
            )
            else None
        )
        if (
            NetworkEvidenceCapability.topology_facts in requirements
            or NetworkEvidenceCapability.coverage in requirements
        ):
            counts = _graph_counts_from_context_evidence(
                latest_links=latest_links,
                historical=historical,
                last_known=last_known,
                passive=passive,
            )
            topology_facts = _freeze_derived(
                build_network_topology_facts(
                    latest_snapshot=dict(latest) if latest is not None else None,
                    nodes=[dict(row) for row in (latest_nodes or ())],
                    links=[dict(row) for row in (latest_links or ())],
                    counts=counts,
                    stale_after_hours=stale_after_hours,
                    now=reference_now,
                )
            )
            if NetworkEvidenceCapability.topology_facts in requirements:
                loaded.add(NetworkEvidenceCapability.topology_facts)
            if NetworkEvidenceCapability.coverage in requirements:
                coverage = _freeze_derived(
                    build_network_topology_coverage(
                        list(topology_facts or ()),
                        tracking_enabled_now=bool(tracking_enabled),
                        has_known_devices=bool(device_rows_tuple),
                        has_usable_ha_area_assignments=bool(ha_areas),
                    )
                )
                loaded.add(NetworkEvidenceCapability.coverage)

        # Record every expanded requirement that was requested.
        for capability in requirements:
            if capability not in loaded:
                # Raw empty loads still count as loaded when the read path ran.
                if (
                    capability == NetworkEvidenceCapability.devices
                    and device_rows_tuple is not None
                ):
                    loaded.add(capability)
                elif (
                    capability == NetworkEvidenceCapability.availability_observations
                    and availability_tuple is not None
                ):
                    loaded.add(capability)
                elif capability == NetworkEvidenceCapability.earliest_availability:
                    loaded.add(capability)
                elif capability == NetworkEvidenceCapability.ha_areas and ha_areas is not None:
                    loaded.add(capability)
                elif (
                    capability == NetworkEvidenceCapability.latest_topology
                    and snapshots is not None
                ):
                    loaded.add(capability)
                elif (
                    capability == NetworkEvidenceCapability.snapshot_history
                    and snapshots is not None
                    and needs_window
                ):
                    loaded.add(capability)

        missing = requirements - loaded
        if missing:
            raise RuntimeError(
                f"NetworkEvidenceContext for {network_id!r} failed to load "
                f"required capabilities: {sorted(c.value for c in missing)}"
            )

        contexts[network_id] = NetworkEvidenceContext(
            network_id=network_id,
            reference_now=reference_now,
            loaded_capabilities=frozenset(loaded),
            network_row=loaded_networks.get(network_id),
            device_rows=device_rows_tuple,
            devices_by_ieee=devices_by_ieee,
            topology_snapshots=(
                _freeze_rows(snapshots)
                if snapshots is not None and needs_window
                else (
                    _freeze_rows([latest])
                    if snapshots is not None and latest is not None
                    else (() if snapshots is not None else None)
                )
            ),
            complete_topology_snapshots=complete,
            latest_usable_snapshot=(
                _freeze_row(latest) if latest is not None else None
            ),
            nodes_by_snapshot_id=_freeze_rows_by_key(network_nodes),
            links_by_snapshot_id=_freeze_rows_by_key(network_links),
            latest_nodes=latest_nodes,
            latest_links=latest_links,
            availability_changes=availability_tuple,
            earliest_availability_at=earliest_at,
            availability_tracking_enabled=tracking_enabled,
            network_has_usable_ha_areas=ha_areas,
            stale_after_hours=context_stale,
            historical_evidence=historical,
            last_known_links=last_known,
            snapshot_history_context=snap_history_ctx,
            passive_hints=passive,
            shared_availability=shared,
            model_patterns=models,
            router_areas=routers,
            device_stats=stats,
            investigations=investigations,
            network_topology_facts=topology_facts,
            network_topology_coverage=coverage,
        )

    return MappingProxyType(contexts)


def compose_network_evidence_context(
    repo: Repository,
    network_id: str,
    *,
    reference_now: datetime,
    requirements: NetworkEvidenceRequirements,
    network_row: NetworkRow | None = None,
    complete_device_rows: list[DeviceRow] | tuple[DeviceRow, ...] | None = None,
    stale_after_hours: int | None = None,
) -> NetworkEvidenceContext:
    """Build one NetworkEvidenceContext for a single network."""
    network_rows_by_id = {network_id: network_row} if network_row is not None else None
    complete_by_network = (
        {network_id: list(complete_device_rows)}
        if complete_device_rows is not None
        else None
    )
    contexts = compose_network_evidence_contexts(
        repo,
        [network_id],
        reference_now=reference_now,
        requirements_by_network={network_id: requirements},
        network_rows_by_id=network_rows_by_id,
        complete_device_rows_by_network=complete_by_network,
        stale_after_hours=stale_after_hours,
    )
    if network_id not in contexts:
        raise LookupError(f"unknown network_id: {network_id}")
    return contexts[network_id]
