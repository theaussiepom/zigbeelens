"""Health diagnostic orchestration and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.device_health import classify_device, sort_priority_from_health
from zigbeelens.diagnostics.models import (
    BridgeHealthResult,
    DeviceHealthContext,
    HealthResult,
    HealthSeverity,
    NetworkHealthResult,
)
from zigbeelens.diagnostics.network_health import classify_network
from zigbeelens.schemas import (
    Confidence,
    DeviceHealth,
    DeviceHealthPrimary,
    DiagnosticConclusion,
    EvidenceItem,
    IncidentScope,
    LimitationItem,
    RouterRisk,
    Severity,
)
from zigbeelens.storage.repository import DeviceRow, Repository
from zigbeelens.diagnostics.clock import SystemClock, utc_iso

OnHealthUpdate = Callable[[str], None]


@dataclass(frozen=True)
class NetworkEvaluationSnapshot:
    network_id: str
    network_name: str
    bridge_state: str
    evaluated_at: datetime
    devices: tuple[DeviceRow, ...]
    device_results: Mapping[tuple[str, str], HealthResult]
    network_result: NetworkHealthResult
    bridge_result: BridgeHealthResult
    health_changed: bool = False


@dataclass(frozen=True)
class HealthCacheState:
    devices: Mapping[tuple[str, str], HealthResult]
    networks: Mapping[str, NetworkHealthResult]
    bridges: Mapping[str, BridgeHealthResult]


_EMPTY_HEALTH_CACHE = HealthCacheState(
    devices=MappingProxyType({}), networks=MappingProxyType({}), bridges=MappingProxyType({})
)


class HealthDiagnosticService:
    def __init__(
        self,
        config: AppConfig,
        repo: Repository,
        on_update: OnHealthUpdate | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self._on_update = on_update
        self._state: HealthCacheState = _EMPTY_HEALTH_CACHE
        self.clock = SystemClock()

    def recalculate_all(self) -> None:
        now = self.clock.now()
        snapshots = self.evaluate_all(now=now)
        if any(s.health_changed for s in snapshots) and self._on_update:
            self._on_update("health_updated")

    def recalculate_device(self, network_id: str, ieee_address: str) -> HealthResult | None:
        now = self.clock.now()
        snapshot = self.evaluate_network(network_id, now=now)
        if snapshot and snapshot.health_changed and self._on_update:
            self._on_update("device_health_updated")
        return snapshot.device_results.get((network_id, ieee_address)) if snapshot else None

    def recalculate_network(self, network_id: str) -> None:
        now = self.clock.now()
        snapshot = self.evaluate_network(network_id, now=now)
        if snapshot and snapshot.health_changed and self._on_update:
            self._on_update("network_health_updated")

    def evaluate_all(self, *, now: datetime) -> list[NetworkEvaluationSnapshot]:
        snapshots = [
            snapshot
            for network in self.repo.list_networks()
            if (snapshot := self._build_network_snapshot(network.id, now=now)) is not None
        ]
        snapshots.sort(key=lambda snapshot: snapshot.network_id)
        self._publish_estate_cache(snapshots)
        return snapshots

    def evaluate_network(self, network_id: str, *, now: datetime) -> NetworkEvaluationSnapshot | None:
        snapshot = self._build_network_snapshot(network_id, now=now)
        if snapshot is not None:
            self._publish_network_cache(snapshot)
        return snapshot

    def evaluate_device_from_snapshot(
        self,
        snapshot: NetworkEvaluationSnapshot,
        ieee_address: str,
        *,
        now: datetime,
    ) -> NetworkEvaluationSnapshot | None:
        """Reclassify one target device against a complete cached network snapshot.

        Returns a new complete snapshot when incremental evaluation is valid.
        Returns None when a full-network rebuild is required instead.
        """
        expected_keys = {
            (snapshot.network_id, row.ieee_address) for row in snapshot.devices
        }
        if set(snapshot.device_results) != expected_keys:
            return None

        network = self.repo.get_network(snapshot.network_id)
        if network is None:
            return None
        target = self.repo.get_device(snapshot.network_id, ieee_address)
        if target is None:
            return None
        target_index = next(
            (
                index
                for index, row in enumerate(snapshot.devices)
                if row.ieee_address == ieee_address
            ),
            None,
        )
        if target_index is None:
            return None

        ts = utc_iso(now)
        network_updated_at = self._network_updated_at(snapshot.network_id)
        ctx = self._build_context(target, network.bridge_state)
        ctx.network_updated_at = network_updated_at
        result = classify_device(ctx, self.config.diagnostics, now=now)
        result.updated_at = ts

        devices = list(snapshot.devices)
        devices[target_index] = target
        device_results = dict(snapshot.device_results)
        device_results[(snapshot.network_id, ieee_address)] = result

        ordered_results = [
            device_results[(snapshot.network_id, row.ieee_address)] for row in devices
        ]
        router_pairs = [
            (row.ieee_address, device_results[(snapshot.network_id, row.ieee_address)])
            for row in devices
            if row.device_type == "Router"
        ]
        net_health, bridge_health = classify_network(
            network_id=snapshot.network_id,
            bridge_state=network.bridge_state,
            network_updated_at=network_updated_at,
            last_mqtt_activity_at=self._network_last_mqtt_activity_at(snapshot.network_id),
            device_health=ordered_results,
            router_devices=router_pairs,
            config=self.config.diagnostics,
            now=now,
        )
        net_health.updated_at = ts
        bridge_health.updated_at = ts

        changed = self._persist_device_health(
            (snapshot.network_id, ieee_address), result, captured_at=ts
        )
        changed = (
            self._persist_network_health(
                snapshot.network_id, net_health, bridge_health, captured_at=ts
            )
            or changed
        )

        updated = NetworkEvaluationSnapshot(
            network_id=snapshot.network_id,
            network_name=network.name,
            bridge_state=network.bridge_state,
            evaluated_at=now,
            devices=tuple(devices),
            device_results=MappingProxyType(device_results),
            network_result=net_health,
            bridge_result=bridge_health,
            health_changed=changed,
        )
        self._publish_network_cache(updated)
        return updated

    def _build_network_snapshot(self, network_id: str, *, now: datetime) -> NetworkEvaluationSnapshot | None:
        network = self.repo.get_network(network_id)
        if not network:
            return None
        ts = utc_iso(now)
        devices = tuple(self.repo.list_devices(network_id))
        local_device_results: dict[tuple[str, str], HealthResult] = {}
        device_results: list[HealthResult] = []
        router_pairs: list[tuple[str, HealthResult]] = []
        network_updated_at = self._network_updated_at(network_id)
        for row in devices:
            ctx = self._build_context(row, network.bridge_state)
            ctx.network_updated_at = network_updated_at
            result = classify_device(ctx, self.config.diagnostics, now=now)
            result.updated_at = ts
            key = (network_id, row.ieee_address)
            local_device_results[key] = result
            device_results.append(result)
            if row.device_type == "Router":
                router_pairs.append((row.ieee_address, result))

        net_health, bridge_health = classify_network(
            network_id=network_id,
            bridge_state=network.bridge_state,
            network_updated_at=network_updated_at,
            last_mqtt_activity_at=self._network_last_mqtt_activity_at(network_id),
            device_health=device_results,
            router_devices=router_pairs,
            config=self.config.diagnostics,
            now=now,
        )
        net_health.updated_at = ts
        bridge_health.updated_at = ts

        changed = False
        for key, result in local_device_results.items():
            changed = self._persist_device_health(key, result, captured_at=ts) or changed
        changed = self._persist_network_health(network_id, net_health, bridge_health, captured_at=ts) or changed

        snapshot = NetworkEvaluationSnapshot(
            network_id=network_id,
            network_name=network.name,
            bridge_state=network.bridge_state,
            evaluated_at=now,
            devices=devices,
            device_results=MappingProxyType(dict(local_device_results)),
            network_result=net_health,
            bridge_result=bridge_health,
            health_changed=changed,
        )
        return snapshot

    def _publish_network_cache(self, snapshot: NetworkEvaluationSnapshot) -> None:
        current = self._state
        devices = {key: value for key, value in current.devices.items() if key[0] != snapshot.network_id}
        devices.update(snapshot.device_results)
        networks = dict(current.networks)
        bridges = dict(current.bridges)
        networks[snapshot.network_id] = snapshot.network_result
        bridges[snapshot.network_id] = snapshot.bridge_result
        self._state = HealthCacheState(
            devices=MappingProxyType(devices),
            networks=MappingProxyType(networks),
            bridges=MappingProxyType(bridges),
        )

    def _publish_estate_cache(self, snapshots: list[NetworkEvaluationSnapshot]) -> None:
        devices: dict[tuple[str, str], HealthResult] = {}
        networks: dict[str, NetworkHealthResult] = {}
        bridges: dict[str, BridgeHealthResult] = {}
        for snapshot in snapshots:
            devices.update(snapshot.device_results)
            networks[snapshot.network_id] = snapshot.network_result
            bridges[snapshot.network_id] = snapshot.bridge_result
        self._state = HealthCacheState(
            devices=MappingProxyType(devices),
            networks=MappingProxyType(networks),
            bridges=MappingProxyType(bridges),
        )

    def get_device_health(self, network_id: str, ieee_address: str) -> HealthResult | None:
        key = (network_id, ieee_address)
        state = self._state
        return state.devices.get(key)

    def get_network_health(self, network_id: str) -> NetworkHealthResult | None:
        state = self._state
        return state.networks.get(network_id)

    def get_bridge_health(self, network_id: str) -> BridgeHealthResult | None:
        state = self._state
        return state.bridges.get(network_id)

    def all_device_health(self) -> dict[tuple[str, str], HealthResult]:
        state = self._state
        return dict(state.devices)

    def has_complete_network_cache(self, network_ids: Iterable[str]) -> bool:
        state = self._state
        return all(
            network_id in state.networks and network_id in state.bridges
            for network_id in network_ids
        )

    def _build_context(
        self,
        row: DeviceRow,
        bridge_state: str,
        network_updated_at: str | None = None,
    ) -> DeviceHealthContext:
        changes = self.repo.availability.count_availability_changes_in_window(
            row.network_id,
            row.ieee_address,
            self.config.diagnostics.recently_unstable_window_hours,
        )
        topology_linked = None
        if row.device_type == "Router" and self.config.topology.enabled:
            from zigbeelens.topology.enrichment import enrich_router_risk

            topo = enrich_router_risk(self.repo, row.network_id, row.ieee_address)
            if topo.has_snapshot:
                topology_linked = topo.linked_affected_count
        return DeviceHealthContext(
            network_id=row.network_id,
            ieee_address=row.ieee_address,
            friendly_name=row.friendly_name,
            device_type=row.device_type,
            power_source=row.power_source,
            interview_state=row.interview_state,
            availability=row.availability,
            last_seen=row.last_seen,
            last_payload_at=row.last_payload_at,
            linkquality=row.linkquality,
            battery=row.battery,
            availability_change_count=changes,
            bridge_online=bridge_state == "online",
            bridge_state=bridge_state,
            network_updated_at=network_updated_at,
            topology_linked_devices=topology_linked,
        )

    def _network_updated_at(self, network_id: str) -> str | None:
        cur = self.repo.db.conn.execute(
            "SELECT updated_at FROM networks WHERE id = ?", (network_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def _network_last_mqtt_activity_at(self, network_id: str) -> str | None:
        return self.repo.get_network_last_mqtt_activity_at(network_id)

    def _persist_device_health(self, key: tuple[str, str], result: HealthResult, *, captured_at: str | None = None) -> bool:
        network_id, ieee = key
        previous = self.repo.get_latest_health_snapshot("device", network_id, ieee)
        payload = _snapshot_payload(result)
        if previous and previous.get("fingerprint") == payload["fingerprint"]:
            return False
        self.repo.insert_health_snapshot(
            scope="device",
            network_id=network_id,
            ieee_address=ieee,
            primary=result.primary.value,
            severity=result.severity.value,
            confidence=result.confidence.value,
            summary=result.summary,
            flags=[f.value for f in result.flags],
            evidence=result.evidence,
            counter_evidence=result.counter_evidence,
            limitations=result.limitations,
            captured_at=captured_at,
        )
        return True

    def _persist_network_health(
        self, network_id: str, net: NetworkHealthResult, bridge: BridgeHealthResult, *, captured_at: str | None = None
    ) -> bool:
        changed = False
        for scope, primary, summary, extra in (
            ("network", net.state.value, net.summary, net),
            ("bridge", bridge.state.value, bridge.summary, bridge),
        ):
            previous = self.repo.get_latest_health_snapshot(scope, network_id, None)
            payload = {
                "primary": primary,
                "summary": summary,
                "severity": extra.severity.value,
                "flags": [],
            }
            fingerprint = json.dumps(payload, sort_keys=True)
            if previous and previous.get("fingerprint") == fingerprint:
                continue
            self.repo.insert_health_snapshot(
                scope=scope,
                network_id=network_id,
                ieee_address=None,
                primary=primary,
                severity=extra.severity.value,
                confidence=extra.confidence.value,
                summary=summary,
                flags=[],
                evidence=extra.evidence,
                counter_evidence=[],
                limitations=extra.limitations,
                captured_at=captured_at,
            )
            changed = True
        return changed


def _snapshot_payload(result: HealthResult) -> dict:
    return {
        "fingerprint": json.dumps(
            {
                "primary": result.primary.value,
                "flags": [f.value for f in result.flags],
                "severity": result.severity.value,
            },
            sort_keys=True,
        )
    }


def health_result_to_device_health(result: HealthResult) -> DeviceHealth:
    return DeviceHealth(
        primary=DeviceHealthPrimary(result.primary.value),
        severity=_map_severity(result.severity),
        confidence=Confidence(result.confidence.value),
        evidence=list(result.evidence),
        counter_evidence=list(result.counter_evidence),
        limitations=list(result.limitations),
        flags=[DeviceHealthPrimary(f.value) for f in result.flags],
    )


def health_result_to_diagnostic(result: HealthResult, friendly_name: str) -> DiagnosticConclusion:
    return DiagnosticConclusion(
        classification=result.primary.value,
        severity=_map_severity(result.severity),
        scope=IncidentScope.device,
        confidence=Confidence(result.confidence.value),
        summary=result.summary,
        evidence=[
            EvidenceItem(id=f"ev-{i}", kind="health", summary=e) for i, e in enumerate(result.evidence)
        ],
        counter_evidence=[
            EvidenceItem(id=f"ce-{i}", kind="health", summary=e)
            for i, e in enumerate(result.counter_evidence)
        ],
        limitations=[
            LimitationItem(id=f"lim-{i}", summary=lim) for i, lim in enumerate(result.limitations)
        ],
    )


def health_result_to_router_risk(
    row: DeviceRow,
    result: HealthResult,
    repo: Repository | None = None,
    *,
    network_evidence_context=None,
) -> RouterRisk:
    from zigbeelens.schemas import Availability

    dependent = None
    if repo is not None or network_evidence_context is not None:
        from zigbeelens.topology.enrichment import enrich_router_risk

        if network_evidence_context is not None:
            from zigbeelens.services.network_evidence import NetworkEvidenceCapability

            network_evidence_context.require_compatible(network_id=row.network_id)
            network_evidence_context.require(NetworkEvidenceCapability.latest_topology)
            topo = enrich_router_risk(
                repo,
                row.network_id,
                row.ieee_address,
                latest_snapshot=(
                    dict(network_evidence_context.latest_usable_snapshot)
                    if network_evidence_context.latest_usable_snapshot is not None
                    else None
                ),
                latest_nodes=[
                    dict(node) for node in (network_evidence_context.latest_nodes or ())
                ],
                latest_links=[
                    dict(link) for link in (network_evidence_context.latest_links or ())
                ],
            )
        else:
            assert repo is not None
            topo = enrich_router_risk(repo, row.network_id, row.ieee_address)
        if topo.has_snapshot:
            dependent = topo.linked_affected_count

    return RouterRisk(
        network_id=row.network_id,
        ieee_address=row.ieee_address,
        friendly_name=row.friendly_name,
        availability=Availability(row.availability)
        if row.availability in Availability.__members__
        else Availability.unknown,
        linkquality=row.linkquality,
        last_seen=row.last_seen,
        possibly_dependent_devices=dependent,
        correlated_affected_devices=0,
        risk=DiagnosticConclusion(
            classification="router_risk_candidate",
            severity=_map_severity(result.severity),
            scope=IncidentScope.router_candidate,
            confidence=Confidence(result.confidence.value),
            summary=result.summary,
            evidence=[
                EvidenceItem(id=f"ev-{i}", kind="health", summary=e)
                for i, e in enumerate(result.evidence)
            ],
            limitations=[
                LimitationItem(id=f"lim-{i}", summary=lim)
                for i, lim in enumerate(result.limitations)
            ],
        ),
    )


def _map_severity(severity: HealthSeverity) -> Severity:
    mapping = {
        HealthSeverity.ok: Severity.healthy,
        HealthSeverity.info: Severity.watch,
        HealthSeverity.watch: Severity.watch,
        HealthSeverity.incident: Severity.incident,
        HealthSeverity.unknown: Severity.watch,
    }
    return mapping.get(severity, Severity.watch)


def sort_priority(result: HealthResult | None, fallback: int = 100) -> int:
    if result is None:
        return fallback
    return sort_priority_from_health(result.primary)
