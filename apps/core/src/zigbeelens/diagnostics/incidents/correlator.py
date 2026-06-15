"""Incident correlation engine — evaluates rules and returns candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from zigbeelens.config.models import AppConfig
from zigbeelens.diagnostics.incidents.explanations import explanation_for, standard_limitations
from zigbeelens.diagnostics.incidents.models import (
    INCIDENT_PRIORITY,
    AffectedDevice,
    IncidentCandidate,
    IncidentType,
)
from zigbeelens.diagnostics.models import BridgeHealthState, HealthFlag, HealthResult
from zigbeelens.diagnostics.service import HealthDiagnosticService
from zigbeelens.schemas import Confidence, IncidentScope, Severity
from zigbeelens.storage.repository import DeviceRow, Repository


@dataclass
class NetworkContext:
    network_id: str
    network_name: str
    bridge_state: str
    bridge_health_state: BridgeHealthState | None
    devices: list[DeviceRow]
    device_health: dict[tuple[str, str], HealthResult]
    offline_cluster: dict[str, str]  # ieee -> changed_at


class IncidentCorrelationEngine:
    def __init__(self, config: AppConfig, repo: Repository) -> None:
        self.config = config
        self.repo = repo

    def correlate(
        self, health: HealthDiagnosticService, now: datetime | None = None
    ) -> list[IncidentCandidate]:
        now = now or datetime.now(timezone.utc)
        contexts = self._build_contexts(health, now)
        raw: list[IncidentCandidate] = []

        raw.extend(self._bridge_offline_rules(contexts))
        raw.extend(self._multi_network_rules(contexts))
        for ctx in contexts:
            raw.extend(self._network_unavailability_rules(ctx, contexts))
            raw.extend(self._router_risk_rules(ctx))
            raw.extend(self._cluster_rules(ctx))
            raw.extend(self._unknown_rules(ctx))

        return self._apply_priority(raw)

    def _build_contexts(
        self, health: HealthDiagnosticService, now: datetime
    ) -> list[NetworkContext]:
        contexts: list[NetworkContext] = []
        window = self.config.diagnostics.incident_window_seconds
        for network in self.repo.list_networks():
            devices = self.repo.list_devices(network.id)
            health_map = {
                (network.id, d.ieee_address): h
                for d in devices
                if (h := health.get_device_health(network.id, d.ieee_address)) is not None
            }
            offline_cluster = self._offline_cluster(network.id, window, devices, now)
            bridge = health.get_bridge_health(network.id)
            contexts.append(
                NetworkContext(
                    network_id=network.id,
                    network_name=network.name,
                    bridge_state=network.bridge_state,
                    bridge_health_state=bridge.state if bridge else None,
                    devices=devices,
                    device_health=health_map,
                    offline_cluster=offline_cluster,
                )
            )
        return contexts

    def _offline_cluster(
        self, network_id: str, window_seconds: int, devices: list[DeviceRow], now: datetime
    ) -> dict[str, str]:
        cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
        transitions = self.repo.list_offline_transitions_since(network_id, cutoff)
        still_offline = {d.ieee_address for d in devices if d.availability == "offline"}
        return {
            ieee: ts for ieee, ts in transitions.items() if ieee in still_offline
        }

    def _bridge_offline_rules(self, contexts: list[NetworkContext]) -> list[IncidentCandidate]:
        cfg = self.config.diagnostics
        out: list[IncidentCandidate] = []
        for ctx in contexts:
            bridge_offline = ctx.bridge_state == "offline" or (
                ctx.bridge_health_state == BridgeHealthState.offline
            )
            bridge_stale = ctx.bridge_health_state == BridgeHealthState.stale
            if not bridge_offline and not bridge_stale:
                continue
            confidence = Confidence.high if bridge_offline else Confidence.medium
            evidence = (
                ["Zigbee2MQTT bridge state is offline"]
                if bridge_offline
                else [
                    f"No bridge state update observed for more than "
                    f"{cfg.bridge_stale_after_minutes} minutes",
                    "No recent device MQTT activity observed on this network",
                ]
            )
            out.append(
                IncidentCandidate(
                    dedup_key=f"bridge_offline:{ctx.network_id}",
                    incident_type=IncidentType.bridge_offline,
                    scope=IncidentScope.network,
                    severity=Severity.critical if bridge_offline else Severity.watch,
                    confidence=confidence,
                    title=(
                        f"Bridge offline on {ctx.network_name}"
                        if bridge_offline
                        else f"Bridge state quiet on {ctx.network_name}"
                    ),
                    summary=(
                        f"The Zigbee2MQTT bridge for {ctx.network_name} is offline."
                        if bridge_offline
                        else (
                            f"The Zigbee2MQTT bridge for {ctx.network_name} has not published "
                            f"bridge/state recently and no device MQTT activity has been observed."
                        )
                    ),
                    explanation=explanation_for(IncidentType.bridge_offline),
                    evidence=evidence,
                    limitations=standard_limitations(IncidentType.bridge_offline),
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.bridge_offline),
                )
            )
        return out

    def _multi_network_rules(self, contexts: list[NetworkContext]) -> list[IncidentCandidate]:
        cfg = self.config.diagnostics
        affected_networks = [
            ctx.network_id
            for ctx in contexts
            if ctx.bridge_state == "offline"
            or len(ctx.offline_cluster) >= cfg.correlated_min_devices
            or sum(
                1
                for d in ctx.devices
                if d.availability == "offline"
            )
            >= cfg.network_wide_min_devices
        ]
        if len(affected_networks) < 2:
            return []
        names = [c.network_name for c in contexts if c.network_id in affected_networks]
        return [
            IncidentCandidate(
                dedup_key="multi_network_instability:active",
                incident_type=IncidentType.multi_network_instability,
                scope=IncidentScope.multi_network,
                severity=Severity.incident,
                confidence=Confidence.medium,
                title="Instability across multiple networks",
                summary=(
                    f"Signals appeared on {len(affected_networks)} Zigbee2MQTT networks: "
                    f"{', '.join(names)}."
                ),
                explanation=explanation_for(IncidentType.multi_network_instability),
                evidence=[
                    f"Signals appeared on {len(affected_networks)} configured networks "
                    f"within the correlation window"
                ],
                limitations=standard_limitations(IncidentType.multi_network_instability),
                network_ids=affected_networks,
                priority=INCIDENT_PRIORITY.index(IncidentType.multi_network_instability),
            )
        ]

    def _network_unavailability_rules(
        self, ctx: NetworkContext, all_contexts: list[NetworkContext]
    ) -> list[IncidentCandidate]:
        if ctx.bridge_state == "offline" or ctx.bridge_health_state == BridgeHealthState.offline:
            return []

        cfg = self.config.diagnostics
        out: list[IncidentCandidate] = []
        cluster = ctx.offline_cluster
        unavailable_count = sum(1 for d in ctx.devices if d.availability == "offline")
        total = len(ctx.devices) or 1
        pct = int((unavailable_count / total) * 100)

        is_network_wide = unavailable_count >= cfg.network_wide_min_devices or (
            total >= cfg.network_wide_min_devices
            and pct >= cfg.network_wide_device_percent
        )

        if is_network_wide:
            affected = [
                AffectedDevice(ctx.network_id, ieee)
                for ieee in cluster.keys()
            ] or [
                AffectedDevice(ctx.network_id, d.ieee_address)
                for d in ctx.devices
                if d.availability == "offline"
            ]
            device_key = ",".join(sorted(a.ieee_address for a in affected))
            out.append(
                IncidentCandidate(
                    dedup_key=f"network_wide:{ctx.network_id}:{device_key}",
                    incident_type=IncidentType.network_wide_instability,
                    scope=IncidentScope.network,
                    severity=Severity.incident,
                    confidence=Confidence.high if pct >= cfg.network_wide_device_percent else Confidence.medium,
                    title=f"Network-wide instability on {ctx.network_name}",
                    summary=(
                        f"{unavailable_count} devices are unavailable on {ctx.network_name} "
                        f"({pct}% of known devices)."
                    ),
                    explanation=explanation_for(IncidentType.network_wide_instability),
                    evidence=[
                        f"{unavailable_count} devices are unavailable",
                        f"That is {pct}% of known devices on this network",
                        "Bridge state did not show offline during the same window",
                    ],
                    limitations=standard_limitations(IncidentType.network_wide_instability),
                    affected_devices=affected,
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.network_wide_instability),
                )
            )
            return out

        if len(cluster) >= cfg.correlated_min_devices:
            times = sorted(cluster.values())
            span = self._span_seconds(times[0], times[-1]) if len(times) > 1 else 0
            affected = [AffectedDevice(ctx.network_id, ieee) for ieee in sorted(cluster.keys())]
            device_key = ",".join(sorted(cluster.keys()))
            evidence = [
                f"{len(cluster)} devices changed availability to offline within {span} seconds",
                f"All affected devices are on network {ctx.network_name}",
                "The Zigbee2MQTT bridge remained online",
            ]
            counter_evidence = ["No topology snapshot is available to confirm a shared router"]
            limitations = standard_limitations(IncidentType.correlated_device_unavailability)
            confidence = Confidence.medium

            if self.config.topology.enabled:
                from zigbeelens.topology.enrichment import enrich_correlated_unavailability

                topo = enrich_correlated_unavailability(self.repo, ctx.network_id, cluster.keys())
                if topo.has_snapshot:
                    limitations = topo.limitations or limitations
                    if topo.shared_router_ieee and topo.linked_affected_count >= 2:
                        name = topo.shared_router_name or topo.shared_router_ieee
                        evidence.append(
                            f"Latest topology snapshot suggests {topo.linked_affected_count} affected devices "
                            f"are linked to router {name}"
                        )
                        counter_evidence = [
                            e
                            for e in counter_evidence
                            if "No topology snapshot" not in e
                        ]
                    elif topo.unrelated_topology:
                        counter_evidence.append(
                            "Latest topology snapshot shows affected devices on unrelated segments"
                        )

            from zigbeelens.enrichment.ha import area_cluster_for_devices

            if self.repo.get_ha_enrichment_status().get("enabled"):
                areas = area_cluster_for_devices(self.repo, ctx.network_id, list(cluster.keys()))
                if areas["matched"] >= 2 and areas["area_count"] == 1:
                    area_name = next(iter(areas["areas"]))
                    evidence.append(
                        f"Home Assistant enrichment maps {areas['matched']} affected devices to {area_name}"
                    )
                elif areas["matched"] >= 2 and areas["area_count"] > 1:
                    counter_evidence.append("Affected devices span multiple Home Assistant areas")

            out.append(
                IncidentCandidate(
                    dedup_key=f"correlated:{ctx.network_id}:{device_key}",
                    incident_type=IncidentType.correlated_device_unavailability,
                    scope=IncidentScope.mesh_segment,
                    severity=Severity.incident,
                    confidence=confidence,
                    title=f"{len(cluster)} devices unavailable on {ctx.network_name}",
                    summary=(
                        f"{len(cluster)} devices became unavailable on {ctx.network_name} "
                        f"within {span} seconds while the bridge stayed online."
                    ),
                    explanation=explanation_for(IncidentType.correlated_device_unavailability),
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                    limitations=limitations,
                    affected_devices=affected,
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.correlated_device_unavailability),
                )
            )
            return out

        if unavailable_count == 1:
            offline = next(d for d in ctx.devices if d.availability == "offline")
            ieee = offline.ieee_address
            name = offline.friendly_name
            out.append(
                IncidentCandidate(
                    dedup_key=f"single_unavailable:{ctx.network_id}:{ieee}",
                    incident_type=IncidentType.single_device_unavailable,
                    scope=IncidentScope.device,
                    severity=Severity.incident,
                    confidence=Confidence.high,
                    title=f"{name} unavailable",
                    summary=f"1 device is unavailable on {ctx.network_name}. This currently looks isolated to that device.",
                    explanation=explanation_for(IncidentType.single_device_unavailable),
                    evidence=[
                        "Device is explicitly unavailable",
                        "No other devices on this network became unavailable within the correlation window",
                        "Bridge remained online",
                    ],
                    limitations=standard_limitations(IncidentType.single_device_unavailable),
                    affected_devices=[AffectedDevice(ctx.network_id, ieee)],
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.single_device_unavailable),
                )
            )
        return out

    def _router_risk_rules(self, ctx: NetworkContext) -> list[IncidentCandidate]:
        if ctx.bridge_state == "offline":
            return []
        out: list[IncidentCandidate] = []
        for device in ctx.devices:
            if device.device_type != "Router":
                continue
            health = ctx.device_health.get((ctx.network_id, device.ieee_address))
            if not health or HealthFlag.router_risk not in health.flags:
                continue
            unavailable = HealthFlag.unavailable in health.flags
            severity = Severity.incident if unavailable else Severity.watch
            flags = [f.value for f in health.flags if f != HealthFlag.router_risk]
            evidence = [
                "Device is a Zigbee router",
                f"Router has health flags: {', '.join(flags) or 'router_risk'}",
            ]
            counter_evidence = ["No dependent devices are confirmed without topology data"]
            limitations = standard_limitations(IncidentType.router_risk)

            if self.config.topology.enabled:
                from zigbeelens.topology.enrichment import enrich_router_risk

                topo = enrich_router_risk(self.repo, ctx.network_id, device.ieee_address)
                if topo.has_snapshot and topo.linked_affected_count > 0:
                    name = topo.shared_router_name or topo.shared_router_ieee
                    evidence.append(
                        f"Latest topology snapshot shows {topo.linked_affected_count} devices linked to router {name}"
                    )
                    counter_evidence = [
                        e for e in counter_evidence if "No dependent devices" not in e
                    ]
                    limitations = topo.limitations or limitations
                elif topo.has_snapshot:
                    limitations = topo.limitations or limitations

            out.append(
                IncidentCandidate(
                    dedup_key=f"router_risk:{ctx.network_id}:{device.ieee_address}",
                    incident_type=IncidentType.router_risk,
                    scope=IncidentScope.router_candidate,
                    severity=severity,
                    confidence=Confidence.medium,
                    title=f"Router risk: {device.friendly_name}",
                    summary=(
                        f"Router {device.friendly_name} has health signals that may matter to nearby devices."
                    ),
                    explanation=explanation_for(IncidentType.router_risk),
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                    limitations=limitations,
                    affected_devices=[
                        AffectedDevice(ctx.network_id, device.ieee_address, role="router_candidate")
                    ],
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.router_risk),
                )
            )
        return out

    def _cluster_rules(self, ctx: NetworkContext) -> list[IncidentCandidate]:
        if ctx.bridge_state == "offline":
            return []
        cfg = self.config.diagnostics
        out: list[IncidentCandidate] = []

        stale_devices = [
            d
            for d in ctx.devices
            if (h := ctx.device_health.get((ctx.network_id, d.ieee_address)))
            and HealthFlag.stale_reporting in h.flags
        ]
        if len(stale_devices) >= cfg.stale_cluster_min_devices:
            key = ",".join(sorted(d.ieee_address for d in stale_devices))
            out.append(
                IncidentCandidate(
                    dedup_key=f"stale_cluster:{ctx.network_id}:{key}",
                    incident_type=IncidentType.stale_reporting_cluster,
                    scope=IncidentScope.network if len(stale_devices) >= cfg.network_wide_min_devices else IncidentScope.mesh_segment,
                    severity=Severity.watch,
                    confidence=Confidence.medium,
                    title=f"Stale reporting cluster on {ctx.network_name}",
                    summary=f"{len(stale_devices)} devices have not reported within their configured stale threshold.",
                    explanation=explanation_for(IncidentType.stale_reporting_cluster),
                    evidence=[
                        f"{len(stale_devices)} devices have not reported within their configured stale threshold"
                    ],
                    limitations=standard_limitations(IncidentType.stale_reporting_cluster),
                    affected_devices=[
                        AffectedDevice(ctx.network_id, d.ieee_address) for d in stale_devices
                    ],
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.stale_reporting_cluster),
                )
            )

        low_bat = [
            d
            for d in ctx.devices
            if (h := ctx.device_health.get((ctx.network_id, d.ieee_address)))
            and HealthFlag.low_battery in h.flags
        ]
        if len(low_bat) >= cfg.low_battery_cluster_min_devices:
            key = ",".join(sorted(d.ieee_address for d in low_bat))
            out.append(
                IncidentCandidate(
                    dedup_key=f"low_battery_cluster:{ctx.network_id}:{key}",
                    incident_type=IncidentType.low_battery_cluster,
                    scope=IncidentScope.network,
                    severity=Severity.watch,
                    confidence=Confidence.high,
                    title=f"Low battery cluster on {ctx.network_name}",
                    summary=f"{len(low_bat)} devices are below the configured low-battery threshold.",
                    explanation=explanation_for(IncidentType.low_battery_cluster),
                    evidence=[
                        f"{len(low_bat)} devices are below the configured low-battery threshold"
                    ],
                    limitations=standard_limitations(IncidentType.low_battery_cluster),
                    affected_devices=[AffectedDevice(ctx.network_id, d.ieee_address) for d in low_bat],
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.low_battery_cluster),
                )
            )

        interview = [
            d
            for d in ctx.devices
            if (h := ctx.device_health.get((ctx.network_id, d.ieee_address)))
            and HealthFlag.interview_issue in h.flags
        ]
        if len(interview) >= cfg.interview_failure_min_devices or (
            len(interview) == 1 and interview[0].interview_state == "failed"
        ):
            key = ",".join(sorted(d.ieee_address for d in interview))
            out.append(
                IncidentCandidate(
                    dedup_key=f"interview_failure:{ctx.network_id}:{key}",
                    incident_type=IncidentType.interview_failure,
                    scope=IncidentScope.network if len(interview) > 1 else IncidentScope.device,
                    severity=Severity.incident if any(d.interview_state == "failed" for d in interview) else Severity.watch,
                    confidence=Confidence.high if any(d.interview_state == "failed" for d in interview) else Confidence.medium,
                    title=f"Interview issue on {ctx.network_name}",
                    summary="One or more devices have incomplete or failed interview state.",
                    explanation=explanation_for(IncidentType.interview_failure),
                    evidence=["Zigbee2MQTT inventory shows interview issues for affected devices"],
                    limitations=standard_limitations(IncidentType.interview_failure),
                    affected_devices=[AffectedDevice(ctx.network_id, d.ieee_address) for d in interview],
                    network_ids=[ctx.network_id],
                    priority=INCIDENT_PRIORITY.index(IncidentType.interview_failure),
                )
            )
        return out

    def _unknown_rules(self, ctx: NetworkContext) -> list[IncidentCandidate]:
        ambiguous = [
            d
            for d in ctx.devices
            if (h := ctx.device_health.get((ctx.network_id, d.ieee_address)))
            and h.primary.value == "unknown"
            and d.availability == "unknown"
            and not d.last_payload_at
        ]
        if len(ambiguous) < 2:
            return []
        key = ",".join(sorted(d.ieee_address for d in ambiguous[:5]))
        return [
            IncidentCandidate(
                dedup_key=f"unknown_pattern:{ctx.network_id}:{key}",
                incident_type=IncidentType.unknown_pattern,
                scope=IncidentScope.unknown,
                severity=Severity.watch,
                confidence=Confidence.low,
                title=f"Devices not reporting yet on {ctx.network_name}",
                summary=(
                    "These devices appear in the Zigbee2MQTT network, but ZigbeeLens has not "
                    "received any data from them yet, so their health is unknown."
                ),
                explanation=explanation_for(IncidentType.unknown_pattern),
                evidence=[
                    "Devices appear in the Zigbee2MQTT device list",
                    "No telemetry or payloads observed from them yet",
                ],
                limitations=standard_limitations(IncidentType.unknown_pattern),
                affected_devices=[AffectedDevice(ctx.network_id, d.ieee_address) for d in ambiguous[:5]],
                network_ids=[ctx.network_id],
                priority=INCIDENT_PRIORITY.index(IncidentType.unknown_pattern),
            )
        ]

    def _apply_priority(self, candidates: list[IncidentCandidate]) -> list[IncidentCandidate]:
        sorted_candidates = sorted(candidates, key=lambda c: c.priority)
        selected: list[IncidentCandidate] = []
        explained_devices: set[tuple[str, str]] = set()
        suppressed_networks: set[str] = set()

        for candidate in sorted_candidates:
            if candidate.incident_type == IncidentType.bridge_offline:
                suppressed_networks.update(candidate.network_ids)
            if any(nid in suppressed_networks for nid in candidate.network_ids):
                if candidate.incident_type not in {
                    IncidentType.bridge_offline,
                    IncidentType.multi_network_instability,
                }:
                    continue
            if candidate.device_keys() and candidate.device_keys().issubset(explained_devices):
                if candidate.incident_type not in {
                    IncidentType.router_risk,
                    IncidentType.stale_reporting_cluster,
                    IncidentType.low_battery_cluster,
                    IncidentType.interview_failure,
                }:
                    continue
            selected.append(candidate)
            if candidate.incident_type in {
                IncidentType.network_wide_instability,
                IncidentType.correlated_device_unavailability,
                IncidentType.single_device_unavailable,
            }:
                explained_devices.update(candidate.device_keys())
        return selected

    @staticmethod
    def _span_seconds(start: str, end: str) -> int:
        try:
            a = datetime.fromisoformat(start.replace("Z", "+00:00"))
            b = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return max(0, int((b - a).total_seconds()))
        except ValueError:
            return 0
