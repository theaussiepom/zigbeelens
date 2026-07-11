"""Health diagnostic orchestration and persistence."""

from __future__ import annotations

import json
from typing import Callable

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
from zigbeelens.storage.repository import DeviceRow, Repository, utc_now_iso

OnHealthUpdate = Callable[[str], None]


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
        self._devices: dict[tuple[str, str], HealthResult] = {}
        self._networks: dict[str, NetworkHealthResult] = {}
        self._bridges: dict[str, BridgeHealthResult] = {}

    def recalculate_all(self) -> None:
        changed = False
        self._devices.clear()
        self._networks.clear()
        self._bridges.clear()

        for network in self.repo.list_networks():
            device_results: list[HealthResult] = []
            router_pairs: list[tuple[str, HealthResult]] = []
            for row in self.repo.list_devices(network.id):
                ctx = self._build_context(row, network.bridge_state)
                ctx.network_updated_at = self._network_updated_at(network.id)
                result = classify_device(ctx, self.config.diagnostics)
                result.updated_at = utc_now_iso()
                key = (row.network_id, row.ieee_address)
                if self._persist_device_health(key, result):
                    changed = True
                self._devices[key] = result
                device_results.append(result)
                if row.device_type == "Router":
                    router_pairs.append((row.ieee_address, result))

            net_health, bridge_health = classify_network(
                network_id=network.id,
                bridge_state=network.bridge_state,
                network_updated_at=self._network_updated_at(network.id),
                last_mqtt_activity_at=self._network_last_mqtt_activity_at(network.id),
                device_health=device_results,
                router_devices=router_pairs,
                config=self.config.diagnostics,
            )
            self._networks[network.id] = net_health
            self._bridges[network.id] = bridge_health
            if self._persist_network_health(network.id, net_health, bridge_health):
                changed = True

        if changed and self._on_update:
            self._on_update("health_updated")

    def recalculate_device(self, network_id: str, ieee_address: str) -> HealthResult | None:
        row = self.repo.get_device(network_id, ieee_address)
        if not row:
            return None
        network = self.repo.get_network(network_id)
        ctx = self._build_context(row, network.bridge_state if network else "unknown")
        result = classify_device(ctx, self.config.diagnostics)
        result.updated_at = utc_now_iso()
        key = (network_id, ieee_address)
        if self._persist_device_health(key, result):
            if self._on_update:
                self._on_update("device_health_updated")
        self._devices[key] = result
        self._recalculate_network(network_id)
        return result

    def recalculate_network(self, network_id: str) -> None:
        self._recalculate_network(network_id)

    def _recalculate_network(self, network_id: str) -> None:
        network = self.repo.get_network(network_id)
        if not network:
            return
        device_results: list[HealthResult] = []
        router_pairs: list[tuple[str, HealthResult]] = []
        for row in self.repo.list_devices(network_id):
            ctx = self._build_context(row, network.bridge_state)
            ctx.network_updated_at = self._network_updated_at(network_id)
            result = classify_device(ctx, self.config.diagnostics)
            result.updated_at = utc_now_iso()
            key = (network_id, row.ieee_address)
            self._persist_device_health(key, result)
            self._devices[key] = result
            device_results.append(result)
            if row.device_type == "Router":
                router_pairs.append((row.ieee_address, result))

        net_health, bridge_health = classify_network(
            network_id=network_id,
            bridge_state=network.bridge_state,
            network_updated_at=self._network_updated_at(network_id),
            last_mqtt_activity_at=self._network_last_mqtt_activity_at(network_id),
            device_health=device_results,
            router_devices=router_pairs,
            config=self.config.diagnostics,
        )
        self._networks[network_id] = net_health
        self._bridges[network_id] = bridge_health
        if self._persist_network_health(network_id, net_health, bridge_health):
            if self._on_update:
                self._on_update("network_health_updated")

    def get_device_health(self, network_id: str, ieee_address: str) -> HealthResult | None:
        key = (network_id, ieee_address)
        if key in self._devices:
            return self._devices[key]
        return None

    def get_network_health(self, network_id: str) -> NetworkHealthResult | None:
        return self._networks.get(network_id)

    def get_bridge_health(self, network_id: str) -> BridgeHealthResult | None:
        return self._bridges.get(network_id)

    def all_device_health(self) -> dict[tuple[str, str], HealthResult]:
        return dict(self._devices)

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

    def _persist_device_health(self, key: tuple[str, str], result: HealthResult) -> bool:
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
        )
        return True

    def _persist_network_health(
        self, network_id: str, net: NetworkHealthResult, bridge: BridgeHealthResult
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
    row: DeviceRow, result: HealthResult, repo: Repository | None = None
) -> RouterRisk:
    from zigbeelens.schemas import Availability

    dependent = None
    if repo is not None:
        from zigbeelens.topology.enrichment import enrich_router_risk

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
