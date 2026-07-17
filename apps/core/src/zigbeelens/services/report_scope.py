"""ReportScopePlan — resolve report identity before expensive composition.

Track 3F: scope-before-composition. The plan holds factual identity only —
never composed DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from zigbeelens.schemas import ReportRequest, ReportScope


class ReportScopeAmbiguityError(ValueError):
    """Device scope without network_id matched multiple networks."""

    def __init__(self, ieee_address: str, network_ids: tuple[str, ...]) -> None:
        self.ieee_address = ieee_address
        self.network_ids = network_ids
        networks = ", ".join(network_ids)
        super().__init__(
            f"Device {ieee_address} matches multiple networks ({networks}); "
            "provide network_id to disambiguate"
        )


class ReportScopeNotFoundError(ValueError):
    """Selected report target identity was not found."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ReportScopeDeviceLookup(Protocol):
    def find_devices_by_ieee(self, ieee_address: str): ...

    def get_device(self, network_id: str, ieee_address: str): ...

    def get_incident(self, incident_id: str): ...

    def list_incident_devices(self, incident_id: str): ...

    def list_incident_networks(self, incident_id: str): ...

    def list_networks(self): ...

    def get_network(self, network_id: str): ...

    def list_devices(self, network_id: str | None = None): ...


@dataclass(frozen=True)
class ReportScopePlan:
    """Immutable factual identity for one report request."""

    scope: ReportScope
    reference_now: datetime
    include_timeline: bool
    network_ids: tuple[str, ...]
    device_keys: tuple[tuple[str, str], ...]
    incident_ids: tuple[str, ...]
    target_network_id: str | None = None
    target_device_ieee: str | None = None
    target_incident_id: str | None = None
    require_device_details: bool = False
    require_full_estate_history: bool = False
    empty_scope: bool = False
    not_found: bool = False
    not_found_reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.empty_scope or self.not_found


def resolve_report_scope_plan(
    request: ReportRequest,
    *,
    repo: ReportScopeDeviceLookup | None,
    reference_now: datetime | None = None,
    include_timeline: bool,
    known_network_ids: tuple[str, ...] | None = None,
    scenario_device_keys: tuple[tuple[str, str], ...] | None = None,
    scenario_incident_networks: dict[str, tuple[str, ...]] | None = None,
    scenario_incident_devices: dict[str, tuple[tuple[str, str], ...]] | None = None,
) -> ReportScopePlan:
    """Resolve factual report scope before composition.

    Live callers pass ``repo``. Scenario/mock callers may pass precomputed
    fixture identity maps instead of reading SQLite.
    """
    now = reference_now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    require_details = request.scope in {ReportScope.incident, ReportScope.device}

    if request.scope == ReportScope.full:
        if known_network_ids is not None:
            network_ids = known_network_ids
        elif repo is not None:
            network_ids = tuple(n.id for n in repo.list_networks())
        else:
            network_ids = ()
        return ReportScopePlan(
            scope=ReportScope.full,
            reference_now=now,
            include_timeline=include_timeline,
            network_ids=network_ids,
            device_keys=(),
            incident_ids=(),
            require_device_details=False,
            require_full_estate_history=True,
        )

    if request.scope == ReportScope.network:
        network_id = request.network_id
        if not network_id:
            return ReportScopePlan(
                scope=ReportScope.network,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(),
                device_keys=(),
                incident_ids=(),
                require_device_details=False,
                empty_scope=True,
                not_found=True,
                not_found_reason="network_id is required for network scope",
            )
        exists = True
        if known_network_ids is not None:
            exists = network_id in known_network_ids
        elif repo is not None:
            exists = repo.get_network(network_id) is not None
        if not exists:
            return ReportScopePlan(
                scope=ReportScope.network,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(),
                device_keys=(),
                incident_ids=(),
                target_network_id=network_id,
                require_device_details=False,
                empty_scope=True,
                not_found=True,
                not_found_reason="Network not found",
            )
        return ReportScopePlan(
            scope=ReportScope.network,
            reference_now=now,
            include_timeline=include_timeline,
            network_ids=(network_id,),
            device_keys=(),
            incident_ids=(),
            target_network_id=network_id,
            require_device_details=False,
        )

    if request.scope == ReportScope.incident:
        incident_id = request.incident_id
        if not incident_id:
            return ReportScopePlan(
                scope=ReportScope.incident,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(),
                device_keys=(),
                incident_ids=(),
                require_device_details=require_details,
                empty_scope=True,
                not_found=True,
                not_found_reason="incident_id is required for incident scope",
            )
        if scenario_incident_networks is not None:
            if incident_id not in scenario_incident_networks:
                return ReportScopePlan(
                    scope=ReportScope.incident,
                    reference_now=now,
                    include_timeline=include_timeline,
                    network_ids=(),
                    device_keys=(),
                    incident_ids=(),
                    target_incident_id=incident_id,
                    require_device_details=require_details,
                    empty_scope=True,
                    not_found=True,
                    not_found_reason="Incident not found",
                )
            network_ids = tuple(scenario_incident_networks.get(incident_id, ()))
            device_keys = tuple(
                (scenario_incident_devices or {}).get(incident_id, ())
            )
        else:
            assert repo is not None
            row = repo.get_incident(incident_id)
            if row is None:
                return ReportScopePlan(
                    scope=ReportScope.incident,
                    reference_now=now,
                    include_timeline=include_timeline,
                    network_ids=(),
                    device_keys=(),
                    incident_ids=(),
                    target_incident_id=incident_id,
                    require_device_details=require_details,
                    empty_scope=True,
                    not_found=True,
                    not_found_reason="Incident not found",
                )
            network_ids = tuple(repo.list_incident_networks(incident_id))
            refs = repo.list_incident_devices(incident_id)
            device_keys = tuple(
                (ref["network_id"], ref["ieee_address"]) for ref in refs
            )
        return ReportScopePlan(
            scope=ReportScope.incident,
            reference_now=now,
            include_timeline=include_timeline,
            network_ids=network_ids,
            device_keys=device_keys,
            incident_ids=(incident_id,),
            target_incident_id=incident_id,
            require_device_details=require_details,
        )

    if request.scope == ReportScope.device:
        ieee = (request.device or "").strip()
        if not ieee:
            return ReportScopePlan(
                scope=ReportScope.device,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(),
                device_keys=(),
                incident_ids=(),
                require_device_details=require_details,
                empty_scope=True,
                not_found=True,
                not_found_reason="device is required for device scope",
            )
        network_id = request.network_id
        if network_id:
            if scenario_device_keys is not None:
                key = (network_id, ieee)
                if key not in scenario_device_keys:
                    # Also try case-normalized IEEE matches from fixtures.
                    matches = [
                        k
                        for k in scenario_device_keys
                        if k[0] == network_id and k[1].lower() == ieee.lower()
                    ]
                    if not matches:
                        return ReportScopePlan(
                            scope=ReportScope.device,
                            reference_now=now,
                            include_timeline=include_timeline,
                            network_ids=(),
                            device_keys=(),
                            incident_ids=(),
                            target_network_id=network_id,
                            target_device_ieee=ieee,
                            require_device_details=require_details,
                            empty_scope=True,
                            not_found=True,
                            not_found_reason="Device not found",
                        )
                    network_id, ieee = matches[0]
                else:
                    network_id, ieee = key
            else:
                assert repo is not None
                row = repo.get_device(network_id, ieee)
                if row is None:
                    return ReportScopePlan(
                        scope=ReportScope.device,
                        reference_now=now,
                        include_timeline=include_timeline,
                        network_ids=(),
                        device_keys=(),
                        incident_ids=(),
                        target_network_id=network_id,
                        target_device_ieee=ieee,
                        require_device_details=require_details,
                        empty_scope=True,
                        not_found=True,
                        not_found_reason="Device not found",
                    )
                ieee = row.ieee_address
                network_id = row.network_id
            return ReportScopePlan(
                scope=ReportScope.device,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(network_id,),
                device_keys=((network_id, ieee),),
                incident_ids=(),
                target_network_id=network_id,
                target_device_ieee=ieee,
                require_device_details=require_details,
            )

        # Narrow IEEE lookup — never scan full inventory.
        if scenario_device_keys is not None:
            matches = [
                k for k in scenario_device_keys if k[1].lower() == ieee.lower()
            ]
        else:
            assert repo is not None
            rows = repo.find_devices_by_ieee(ieee)
            matches = [(row.network_id, row.ieee_address) for row in rows]
        if not matches:
            return ReportScopePlan(
                scope=ReportScope.device,
                reference_now=now,
                include_timeline=include_timeline,
                network_ids=(),
                device_keys=(),
                incident_ids=(),
                target_device_ieee=ieee,
                require_device_details=require_details,
                empty_scope=True,
                not_found=True,
                not_found_reason="Device not found",
            )
        if len(matches) > 1:
            raise ReportScopeAmbiguityError(
                ieee, tuple(sorted({nid for nid, _ in matches}))
            )
        network_id, ieee = matches[0]
        return ReportScopePlan(
            scope=ReportScope.device,
            reference_now=now,
            include_timeline=include_timeline,
            network_ids=(network_id,),
            device_keys=((network_id, ieee),),
            incident_ids=(),
            target_network_id=network_id,
            target_device_ieee=ieee,
            require_device_details=require_details,
        )

    return ReportScopePlan(
        scope=request.scope,
        reference_now=now,
        include_timeline=include_timeline,
        network_ids=(),
        device_keys=(),
        incident_ids=(),
        empty_scope=True,
        not_found=True,
        not_found_reason=f"Unsupported report scope: {request.scope}",
    )
