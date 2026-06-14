"""Human-readable incident explanations."""

from __future__ import annotations

from zigbeelens.diagnostics.incidents.models import IncidentType


def explanation_for(incident_type: IncidentType) -> str:
    snippets = {
        IncidentType.single_device_unavailable: (
            "This looks isolated to this device. ZigbeeLens does not see wider network "
            "instability at the same time."
        ),
        IncidentType.correlated_device_unavailability: (
            "Multiple devices changed state around the same time. This is less consistent with "
            "unrelated device failures and may indicate a local mesh segment, shared router, "
            "power, or interference pattern."
        ),
        IncidentType.bridge_offline: (
            "The Zigbee2MQTT bridge for this network is offline or stale, so device failures "
            "may be downstream of the bridge/coordinator layer."
        ),
        IncidentType.network_wide_instability: (
            "Many devices on this Zigbee2MQTT network are affected. This looks wider than a "
            "single device or small mesh segment."
        ),
        IncidentType.multi_network_instability: (
            "Multiple Zigbee2MQTT networks show related instability. This may point above an "
            "individual Zigbee mesh."
        ),
        IncidentType.router_risk: (
            "This router has health signals that may matter to nearby devices. Review it as a "
            "mesh infrastructure risk candidate."
        ),
        IncidentType.stale_reporting_cluster: (
            "Several devices are stale. This may indicate a reporting, mesh, or sleepy-device "
            "pattern, but they are not necessarily unavailable."
        ),
        IncidentType.low_battery_cluster: (
            "Multiple devices have low battery readings. This is a maintenance signal rather "
            "than a confirmed network fault."
        ),
        IncidentType.interview_failure: (
            "One or more devices have incomplete or failed interview state. This may prevent "
            "reliable operation."
        ),
        IncidentType.unknown_pattern: (
            "ZigbeeLens sees health signals but does not yet have enough evidence to classify "
            "the scope."
        ),
    }
    return snippets.get(
        incident_type,
        "The evidence suggests a pattern worth monitoring, but ZigbeeLens cannot prove root cause.",
    )


def standard_limitations(incident_type: IncidentType) -> list[str]:
    common = {
        IncidentType.single_device_unavailable: [
            "This does not prove the device itself is faulty",
            "A local router or interference issue may still affect only one device",
        ],
        IncidentType.correlated_device_unavailability: [
            "This may indicate a local mesh, shared router, power, or interference pattern, "
            "but ZigbeeLens cannot prove which from MQTT alone",
            "ZigbeeLens cannot prove a physical route without topology data",
        ],
        IncidentType.bridge_offline: [
            "This identifies the Zigbee2MQTT bridge layer, not necessarily the physical coordinator hardware",
        ],
        IncidentType.network_wide_instability: [
            "ZigbeeLens cannot determine from MQTT alone whether this is coordinator, "
            "channel/interference, power, or mesh-related",
        ],
        IncidentType.multi_network_instability: [
            "This may indicate shared MQTT, host, power, or broader infrastructure effects, "
            "but ZigbeeLens cannot prove the shared cause",
        ],
        IncidentType.router_risk: [
            "ZigbeeLens cannot prove which end devices route through this router without topology data",
        ],
        IncidentType.stale_reporting_cluster: [
            "Some sleepy battery devices report infrequently by design",
            "This does not prove devices are offline",
        ],
        IncidentType.low_battery_cluster: [
            "Some devices report battery infrequently or inaccurately",
        ],
        IncidentType.interview_failure: [
            "Interview state depends on latest Zigbee2MQTT inventory data",
        ],
        IncidentType.unknown_pattern: [
            "ZigbeeLens needs more history to classify this pattern",
        ],
    }
    return list(common.get(incident_type, ["ZigbeeLens cannot prove root cause from MQTT data alone"]))
