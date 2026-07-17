"""Compose immutable NetworkEvidenceContext values (Track 3G).

Loads each required raw evidence collection once via bounded bulk repository
reads, then freezes one context per network. Derived evidence is attached when
requested; pure derivation from context-owned rows is expanded in later Track
3G commits.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Mapping

from zigbeelens.decisions.model_pattern import observed_model_patterns_for_network
from zigbeelens.decisions.router_area import observed_router_areas_for_network
from zigbeelens.decisions.topology_coverage import build_network_topology_coverage
from zigbeelens.decisions.topology_facts import build_network_topology_facts
from zigbeelens.services.network_evidence import (
    NetworkEvidenceCapability,
    NetworkEvidenceContext,
    NetworkEvidenceRequirements,
    _freeze_row,
    _freeze_rows,
    _freeze_rows_by_key,
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
from zigbeelens.decisions.availability_event_groups import (
    shared_availability_event_groups_for_network,
)


def _require_aware(reference_now: datetime) -> datetime:
    if reference_now.tzinfo is None:
        raise ValueError("reference_now must be timezone-aware")
    return reference_now.astimezone(timezone.utc)


def _needs_topology_raw(requirements: NetworkEvidenceRequirements) -> bool:
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
    return bool(
        requirements
        & {
            NetworkEvidenceCapability.availability_observations,
            NetworkEvidenceCapability.passive_hints,
            NetworkEvidenceCapability.shared_availability,
            NetworkEvidenceCapability.model_patterns,
            NetworkEvidenceCapability.device_stats,
            NetworkEvidenceCapability.investigations,
        }
    )


def _needs_devices(requirements: NetworkEvidenceRequirements) -> bool:
    return bool(
        requirements
        & {
            NetworkEvidenceCapability.devices,
            NetworkEvidenceCapability.snapshot_history,
            NetworkEvidenceCapability.earliest_availability,
            NetworkEvidenceCapability.passive_hints,
            NetworkEvidenceCapability.shared_availability,
            NetworkEvidenceCapability.model_patterns,
            NetworkEvidenceCapability.router_areas,
            NetworkEvidenceCapability.device_stats,
            NetworkEvidenceCapability.investigations,
            NetworkEvidenceCapability.topology_facts,
            NetworkEvidenceCapability.coverage,
        }
    )


def compose_network_evidence_contexts(
    repo: Repository,
    network_ids: list[str] | tuple[str, ...],
    *,
    reference_now: datetime,
    requirements_by_network: Mapping[str, NetworkEvidenceRequirements],
    network_rows_by_id: Mapping[str, NetworkRow] | None = None,
    devices_by_network: Mapping[str, list[DeviceRow] | tuple[DeviceRow, ...]] | None = None,
    stale_after_hours: int | None = None,
) -> Mapping[str, NetworkEvidenceContext]:
    """Build one immutable NetworkEvidenceContext per network ID."""
    reference_now = _require_aware(reference_now)
    ordered_ids = list(dict.fromkeys(nid for nid in network_ids if nid))
    if not ordered_ids:
        return MappingProxyType({})

    # Union requirements and validate device-row ownership when supplied.
    reqs: dict[str, NetworkEvidenceRequirements] = {}
    for network_id in ordered_ids:
        req = frozenset(requirements_by_network.get(network_id, frozenset()))
        reqs[network_id] = req
        if devices_by_network and network_id in devices_by_network:
            for row in devices_by_network[network_id]:
                if row.network_id != network_id:
                    raise ValueError(
                        f"DeviceRow network_id {row.network_id!r} does not match "
                        f"expected {network_id!r}"
                    )

    networks_needing_devices = [nid for nid in ordered_ids if _needs_devices(reqs[nid])]
    networks_needing_topo = [nid for nid in ordered_ids if _needs_topology_raw(reqs[nid])]
    networks_needing_avail = [
        nid for nid in ordered_ids if _needs_availability_obs(reqs[nid])
    ]
    networks_needing_earliest = [
        nid
        for nid in ordered_ids
        if NetworkEvidenceCapability.earliest_availability in reqs[nid]
        or NetworkEvidenceCapability.snapshot_history in reqs[nid]
        or NetworkEvidenceCapability.coverage in reqs[nid]
    ]
    networks_needing_ha = [
        nid for nid in ordered_ids if NetworkEvidenceCapability.ha_areas in reqs[nid]
        or NetworkEvidenceCapability.coverage in reqs[nid]
        or NetworkEvidenceCapability.topology_facts in reqs[nid]
    ]

    # Network rows
    if network_rows_by_id is None:
        loaded_networks = {row.id: row for row in repo.get_networks_by_ids(ordered_ids)}
    else:
        loaded_networks = dict(network_rows_by_id)

    # Devices
    device_map: dict[str, list[DeviceRow]] = {}
    if networks_needing_devices:
        missing_device_networks = [
            nid
            for nid in networks_needing_devices
            if devices_by_network is None or nid not in devices_by_network
        ]
        bulk_devices = (
            repo.list_devices_for_networks(missing_device_networks)
            if missing_device_networks
            else {}
        )
        for nid in networks_needing_devices:
            if devices_by_network is not None and nid in devices_by_network:
                device_map[nid] = list(devices_by_network[nid])
            else:
                device_map[nid] = list(bulk_devices.get(nid, []))

    # Topology snapshots (once per network that needs them)
    snapshots_by_network: dict[str, list[dict[str, Any]]] = {}
    if networks_needing_topo:
        snapshots_by_network = repo.list_topology_snapshots_for_networks(networks_needing_topo)

    # Collect snapshot IDs for nodes/links (complete + latest)
    snapshot_ids_for_links: list[str] = []
    snapshot_ids_for_nodes: list[str] = []
    latest_by_network: dict[str, dict[str, Any] | None] = {}
    for network_id in networks_needing_topo:
        snapshots = snapshots_by_network.get(network_id, [])
        complete_ids: list[str] = []
        for snap in snapshots:
            if snap.get("status") == "complete":
                sid = str(snap["snapshot_id"])
                if sid not in complete_ids:
                    complete_ids.append(sid)
        # Latest usable = first complete by captured_at DESC (same as get_latest)
        latest = next(
            (dict(snap) for snap in snapshots if snap.get("status") == "complete"),
            None,
        )
        latest_by_network[network_id] = latest
        link_ids = list(complete_ids)
        if latest is not None:
            latest_id = str(latest["snapshot_id"])
            if latest_id not in link_ids:
                link_ids.append(latest_id)
        node_ids = link_ids[:MAX_SNAPSHOT_HISTORY]
        if latest is not None:
            latest_id = str(latest["snapshot_id"])
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

    # Availability lookback: max of current consumers (passive/shared/model = 7 days)
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
        snapshots = snapshots_by_network.get(network_id)
        latest = latest_by_network.get(network_id) if snapshots is not None else None
        complete = (
            tuple(
                _freeze_row(snap)
                for snap in (snapshots or [])
                if snap.get("status") == "complete"
            )
            if snapshots is not None
            else None
        )

        network_links: dict[str, list[dict[str, Any]]] | None = None
        network_nodes: dict[str, list[dict[str, Any]]] | None = None
        latest_nodes: tuple[Mapping[str, Any], ...] | None = None
        latest_links: tuple[Mapping[str, Any], ...] | None = None
        if snapshots is not None:
            network_links = {}
            network_nodes = {}
            for snap in snapshots:
                sid = str(snap["snapshot_id"])
                if sid in links_by_snapshot:
                    network_links[sid] = list(links_by_snapshot[sid])
                if sid in nodes_by_snapshot:
                    network_nodes[sid] = list(nodes_by_snapshot[sid])
            if latest is not None:
                latest_id = str(latest["snapshot_id"])
                latest_nodes = _freeze_rows(network_nodes.get(latest_id, []))
                latest_links = _freeze_rows(network_links.get(latest_id, []))
            else:
                latest_nodes = ()
                latest_links = ()
            if NetworkEvidenceCapability.latest_topology in requirements:
                loaded.add(NetworkEvidenceCapability.latest_topology)
            if NetworkEvidenceCapability.snapshot_history in requirements or _needs_topology_raw(
                requirements
            ):
                # Raw snapshot maps are always attached when topology raw was loaded.
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
        if network_id in earliest_by_network or NetworkEvidenceCapability.earliest_availability in requirements:
            earliest_at = earliest_by_network.get(network_id)
            tracking_enabled = earliest_at is not None
            loaded.add(NetworkEvidenceCapability.earliest_availability)

        ha_areas: bool | None = None
        if network_id in ha_by_network or NetworkEvidenceCapability.ha_areas in requirements:
            ha_areas = ha_by_network.get(network_id, False)
            loaded.add(NetworkEvidenceCapability.ha_areas)

        # Derived: historical / last-known / snapshot-history context
        historical: Mapping[str, Any] | None = None
        last_known: Mapping[str, Any] | None = None
        snap_history_ctx: Any | None = None
        if snapshots is not None and network_links is not None:
            snap_list = list(snapshots)
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
            if (
                NetworkEvidenceCapability.snapshot_history in requirements
                or NetworkEvidenceCapability.latest_topology in requirements
            ):
                snap_history_ctx = load_device_snapshot_history_network_context(
                    repo,
                    network_id,
                    snapshots=snap_list,
                    links_by_snapshot_id=links_map,
                    earliest_availability_at=earliest_by_network.get(network_id),
                    earliest_availability_supplied=network_id in earliest_by_network
                    or NetworkEvidenceCapability.earliest_availability in requirements,
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
            shared = shared_availability_event_groups_for_network(
                repo,
                network_id,
                now=reference_now,
                devices=device_list,
                availability_rows=avail_rows,
            )
            loaded.add(NetworkEvidenceCapability.shared_availability)

        models: Any | None = None
        if NetworkEvidenceCapability.model_patterns in requirements:
            models = observed_model_patterns_for_network(
                repo,
                network_id,
                now=reference_now,
                devices=device_list,
                availability_rows=avail_rows,
            )
            loaded.add(NetworkEvidenceCapability.model_patterns)

        routers: Any | None = None
        if NetworkEvidenceCapability.router_areas in requirements:
            devices = list(device_rows_tuple or ())
            issue_ieees = issue_device_ieees_from_state(devices)
            hist = (
                dict(historical)
                if historical is not None
                else aggregate_historical_evidence(
                    repo, network_id, now=reference_now,
                    snapshots=list(snapshots or []),
                    links_by_snapshot_id={
                        sid: list(rows) for sid, rows in (network_links or {}).items()
                    },
                )
            )
            lk = (
                dict(last_known)
                if last_known is not None
                else aggregate_last_known_links(
                    repo,
                    network_id,
                    snapshots=list(snapshots or []),
                    links_by_snapshot_id={
                        sid: list(rows) for sid, rows in (network_links or {}).items()
                    },
                )
            )
            ph = (
                dict(passive)
                if passive is not None
                else aggregate_passive_hints(repo, network_id, now=reference_now)
            )
            routers = observed_router_areas_for_network(
                repo,
                network_id,
                devices=devices,
                latest_links=[dict(row) for row in (latest_links or ())],
                history=hist,
                last_known_links=list(lk.get("last_known_links") or []),
                passive_hints=list(ph.get("hints") or []),
                issue_device_ieees=issue_ieees,
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
            hist = dict(historical) if historical is not None else aggregate_historical_evidence(
                repo,
                network_id,
                now=reference_now,
                snapshots=list(snapshots or []),
                links_by_snapshot_id={
                    sid: list(rows) for sid, rows in (network_links or {}).items()
                },
                latest_snapshot=latest,
                latest_nodes=[dict(row) for row in (latest_nodes or ())],
            )
            lk = dict(last_known) if last_known is not None else aggregate_last_known_links(
                repo,
                network_id,
                snapshots=list(snapshots or []),
                links_by_snapshot_id={
                    sid: list(rows) for sid, rows in (network_links or {}).items()
                },
                latest_snapshot=latest,
                latest_nodes=[dict(row) for row in (latest_nodes or ())],
            )
            ph = dict(passive) if passive is not None else aggregate_passive_hints(
                repo,
                network_id,
                now=reference_now,
                devices=device_list,
                availability_rows=avail_rows,
                snapshots=list(snapshots or []),
                links_by_snapshot_id={
                    sid: list(rows) for sid, rows in (network_links or {}).items()
                },
                latest_snapshot=latest,
            )
            sh = shared or shared_availability_event_groups_for_network(
                repo,
                network_id,
                now=reference_now,
                devices=device_list,
                availability_rows=avail_rows,
            )
            mp = models or observed_model_patterns_for_network(
                repo,
                network_id,
                now=reference_now,
                devices=device_list,
                availability_rows=avail_rows,
            )
            ra = routers
            if ra is None and NetworkEvidenceCapability.router_areas not in requirements:
                # Build router areas opportunistically for investigations.
                devices = list(device_rows_tuple or ())
                ra = observed_router_areas_for_network(
                    repo,
                    network_id,
                    devices=devices,
                    latest_links=[dict(row) for row in (latest_links or ())],
                    history=hist,
                    last_known_links=list(lk.get("last_known_links") or []),
                    passive_hints=list(ph.get("hints") or []),
                    issue_device_ieees=issue_device_ieees_from_state(devices),
                )
            investigations = MappingProxyType(
                dict(
                    aggregate_investigations(
                        repo,
                        network_id,
                        history=hist,
                        passive_hints=list(ph.get("hints") or []),
                        shared_availability_events=list(sh.groups),
                        observed_router_areas=list(ra.areas) if ra is not None else [],
                        observed_model_patterns=list(mp.patterns),
                        last_known_links=list(lk.get("last_known_links") or []),
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
        if (
            NetworkEvidenceCapability.topology_facts in requirements
            or NetworkEvidenceCapability.coverage in requirements
        ):
            topology_facts = build_network_topology_facts(
                latest_snapshot=dict(latest) if latest is not None else None,
                nodes=[dict(row) for row in (latest_nodes or ())],
                links=[dict(row) for row in (latest_links or ())],
                stale_after_hours=stale_after_hours,
                now=reference_now,
            )
            if NetworkEvidenceCapability.topology_facts in requirements:
                loaded.add(NetworkEvidenceCapability.topology_facts)
            if NetworkEvidenceCapability.coverage in requirements:
                coverage = build_network_topology_coverage(
                    topology_facts,
                    tracking_enabled_now=bool(tracking_enabled),
                    has_known_devices=bool(device_rows_tuple),
                    has_usable_ha_area_assignments=bool(ha_areas),
                )
                loaded.add(NetworkEvidenceCapability.coverage)

        # Ensure requested capabilities that only mark raw loads are recorded.
        for capability in requirements:
            if capability not in loaded and capability in {
                NetworkEvidenceCapability.latest_topology,
                NetworkEvidenceCapability.snapshot_history,
                NetworkEvidenceCapability.devices,
                NetworkEvidenceCapability.availability_observations,
                NetworkEvidenceCapability.earliest_availability,
                NetworkEvidenceCapability.ha_areas,
            }:
                # Capability was requested; raw load path above should have set it.
                # If topology/devices were not needed by helpers, mark explicitly.
                if capability == NetworkEvidenceCapability.devices and device_rows_tuple is not None:
                    loaded.add(capability)
                elif capability == NetworkEvidenceCapability.availability_observations and availability_tuple is not None:
                    loaded.add(capability)
                elif capability == NetworkEvidenceCapability.earliest_availability:
                    loaded.add(capability)
                elif capability == NetworkEvidenceCapability.ha_areas and ha_areas is not None:
                    loaded.add(capability)
                elif capability in {
                    NetworkEvidenceCapability.latest_topology,
                    NetworkEvidenceCapability.snapshot_history,
                } and snapshots is not None:
                    loaded.add(capability)

        contexts[network_id] = NetworkEvidenceContext(
            network_id=network_id,
            reference_now=reference_now,
            loaded_capabilities=frozenset(loaded),
            network_row=loaded_networks.get(network_id),
            device_rows=device_rows_tuple,
            devices_by_ieee=devices_by_ieee,
            topology_snapshots=_freeze_rows(snapshots) if snapshots is not None else None,
            complete_topology_snapshots=complete,
            latest_usable_snapshot=_freeze_row(latest) if latest is not None else (
                None if snapshots is None else None
            ),
            nodes_by_snapshot_id=_freeze_rows_by_key(network_nodes),
            links_by_snapshot_id=_freeze_rows_by_key(network_links),
            latest_nodes=latest_nodes,
            latest_links=latest_links,
            availability_changes=availability_tuple,
            earliest_availability_at=earliest_at,
            availability_tracking_enabled=tracking_enabled,
            network_has_usable_ha_areas=ha_areas,
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
    device_rows: list[DeviceRow] | tuple[DeviceRow, ...] | None = None,
    stale_after_hours: int | None = None,
) -> NetworkEvidenceContext:
    """Build one NetworkEvidenceContext for a single network."""
    network_rows_by_id = {network_id: network_row} if network_row is not None else None
    devices_by_network = {network_id: list(device_rows)} if device_rows is not None else None
    contexts = compose_network_evidence_contexts(
        repo,
        [network_id],
        reference_now=reference_now,
        requirements_by_network={network_id: requirements},
        network_rows_by_id=network_rows_by_id,
        devices_by_network=devices_by_network,
        stale_after_hours=stale_after_hours,
    )
    if network_id not in contexts:
        raise LookupError(f"unknown network_id: {network_id}")
    return contexts[network_id]
