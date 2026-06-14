"""Device health classification rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zigbeelens.config.models import DiagnosticsConfig
from zigbeelens.diagnostics.models import (
    DeviceHealthContext,
    HealthConfidence,
    HealthFlag,
    HealthResult,
    HealthSeverity,
)


def classify_device(ctx: DeviceHealthContext, config: DiagnosticsConfig, now: datetime | None = None) -> HealthResult:
    now = now or datetime.now(timezone.utc)
    flags: list[HealthFlag] = []
    evidence: list[str] = []
    counter: list[str] = []
    limitations: list[str] = []

    unavailable = _check_unavailable(ctx, flags, evidence, counter, limitations)
    unstable = _check_unstable(ctx, config, flags, evidence, limitations)
    interview = _check_interview(ctx, flags, evidence, limitations)
    stale = _check_stale(ctx, config, now, flags, evidence, limitations)
    weak = _check_weak_link(ctx, config, flags, evidence, limitations)
    low_bat = _check_low_battery(ctx, config, flags, evidence, limitations)
    router = _check_router_risk(ctx, flags, evidence, limitations, unavailable, unstable, weak, stale, low_bat)
    healthy = _check_healthy(ctx, flags, evidence, limitations, unavailable, unstable, interview, stale, weak, low_bat)

    primary = _choose_primary(
        ctx, flags, unavailable, router, unstable, interview, stale, weak, low_bat, healthy
    )

    if primary == HealthFlag.unknown:
        flags = [f for f in flags if f != HealthFlag.healthy]
        if HealthFlag.unknown not in flags:
            flags.append(HealthFlag.unknown)
        if not any("inventory" in e.lower() for e in evidence):
            evidence.insert(0, "Device exists in Zigbee2MQTT inventory")
        if not any("payload" in e.lower() for e in evidence):
            evidence.append("No device payload has been observed by ZigbeeLens yet")
        for lim in (
            "Availability may not be enabled in Zigbee2MQTT",
            "ZigbeeLens has not observed enough history yet",
        ):
            if lim not in limitations:
                limitations.append(lim)

    severity = _severity_for_primary(primary, flags, ctx)
    confidence = _confidence_for_primary(primary, flags, ctx)
    summary = _summary_for_primary(primary, ctx)

    if not flags:
        flags = [HealthFlag.unknown]

    return HealthResult(
        primary=primary,
        flags=sorted(set(flags), key=lambda f: _flag_order(f)),
        severity=severity,
        confidence=confidence,
        summary=summary,
        evidence=evidence,
        counter_evidence=counter,
        limitations=limitations,
    )


def _check_unavailable(ctx, flags, evidence, counter, limitations) -> bool:
    if ctx.availability == "offline":
        flags.append(HealthFlag.unavailable)
        evidence.append("Latest Zigbee2MQTT availability state is offline")
        limitations.append("Availability is only available when enabled in Zigbee2MQTT")
        if ctx.last_payload_at:
            counter.append("Recent payload was observed, which may indicate intermittent reporting")
        return True
    return False


def _check_unstable(ctx, config, flags, evidence, limitations) -> bool:
    if ctx.availability_change_count >= config.flapping_threshold:
        flags.append(HealthFlag.recently_unstable)
        evidence.append(
            f"Availability changed {ctx.availability_change_count} times in the last "
            f"{config.recently_unstable_window_hours} hours"
        )
        limitations.append(
            "This indicates instability but does not prove whether the cause is device, "
            "router, interference, or coordinator related"
        )
        return True
    return False


def _check_interview(ctx, flags, evidence, limitations) -> bool:
    if ctx.interview_state in {"failed", "in_progress"}:
        flags.append(HealthFlag.interview_issue)
        evidence.append(f"Zigbee2MQTT inventory shows interview_state={ctx.interview_state}")
        limitations.append("Interview status comes from inventory and may need refreshed Zigbee2MQTT data")
        return True
    if ctx.interview_state == "unknown" and not ctx.last_payload_at:
        return False
    return False


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _check_stale(ctx, config, now, flags, evidence, limitations) -> bool:
    ts = _parse_ts(ctx.last_payload_at) or _parse_ts(ctx.last_seen)
    if ts is None:
        if ctx.last_payload_at is None and ctx.last_seen is None:
            return False
        return False

    hours = _stale_threshold_hours(ctx, config)
    age = now - ts
    if age > timedelta(hours=hours):
        flags.append(HealthFlag.stale_reporting)
        evidence.append(f"No payload observed for {int(age.total_seconds() // 3600)} hours")
        evidence.append(f"Configured stale threshold is {hours} hours")
        limitations.append("Some sleepy battery devices report infrequently by design")
        return True
    return False


def _stale_threshold_hours(ctx: DeviceHealthContext, config: DiagnosticsConfig) -> int:
    if ctx.device_type == "Router" or ctx.power_source == "Mains":
        return config.mains_stale_after_hours
    if ctx.power_source == "Battery":
        return config.battery_stale_after_hours
    return config.stale_after_hours


def _check_weak_link(ctx, config, flags, evidence, limitations) -> bool:
    if ctx.linkquality is not None and ctx.linkquality <= config.weak_link_threshold:
        flags.append(HealthFlag.weak_link)
        evidence.append(
            f"Latest linkquality is {ctx.linkquality}, below configured threshold {config.weak_link_threshold}"
        )
        limitations.append("Single linkquality readings are imperfect and can vary over time")
        return True
    return False


def _check_low_battery(ctx, config, flags, evidence, limitations) -> bool:
    if ctx.battery is not None and ctx.battery <= config.low_battery_percent:
        flags.append(HealthFlag.low_battery)
        evidence.append(
            f"Battery is {ctx.battery}%, below configured threshold {config.low_battery_percent}%"
        )
        limitations.append("Some devices report battery unreliably or infrequently")
        return True
    return False


def _check_router_risk(ctx, flags, evidence, limitations, unavailable, unstable, weak, stale, low_bat) -> bool:
    if ctx.device_type != "Router":
        return False
    issues = []
    if unavailable:
        issues.append("unavailable")
    if unstable:
        issues.append("recently_unstable")
    if weak:
        issues.append("weak_link")
    if stale:
        issues.append("stale_reporting")
    if low_bat:
        issues.append("low_battery")
    if not issues:
        return False
    flags.append(HealthFlag.router_risk)
    evidence.append("Device is a Zigbee router")
    evidence.append(f"Router has current health signals: {', '.join(issues)}")
    if getattr(ctx, "topology_linked_devices", None):
        evidence.append(
            f"Latest topology snapshot shows {ctx.topology_linked_devices} linked devices"
        )
        limitations.append(
            "ZigbeeLens cannot prove current routing from one snapshot; topology suggests possible relationships only"
        )
    else:
        limitations.append(
            "ZigbeeLens cannot prove dependent end devices route through this router without topology data"
        )
    return True


def _check_healthy(ctx, flags, evidence, limitations, unavailable, unstable, interview, stale, weak, low_bat) -> bool:
    if unavailable or unstable or interview or stale or weak or low_bat:
        return False
    has_signal = ctx.last_payload_at or ctx.last_seen or ctx.availability == "online"
    if not has_signal:
        return False
    flags.append(HealthFlag.healthy)
    if ctx.last_payload_at or ctx.last_seen:
        evidence.append("Recent payload observed")
    if ctx.availability == "online":
        evidence.append("Availability is online")
    elif ctx.availability == "unknown":
        limitations.append("Availability is not known")
    if ctx.battery is not None:
        evidence.append("Battery is above configured threshold")
    if ctx.linkquality is not None:
        evidence.append("Linkquality is above configured threshold")
    evidence.append("No recent availability changes")
    return True


def _choose_primary(ctx, flags, unavailable, router, unstable, interview, stale, weak, low_bat, healthy) -> HealthFlag:
    if unavailable:
        return HealthFlag.unavailable
    if ctx.device_type == "Router" and router and (unavailable or unstable):
        return HealthFlag.router_risk
    if unstable:
        return HealthFlag.recently_unstable
    if interview:
        return HealthFlag.interview_issue
    if stale:
        return HealthFlag.stale_reporting
    if weak:
        return HealthFlag.weak_link
    if low_bat:
        return HealthFlag.low_battery
    if HealthFlag.router_risk in flags:
        return HealthFlag.router_risk
    if healthy:
        return HealthFlag.healthy
    return HealthFlag.unknown


def _severity_for_primary(primary: HealthFlag, flags: list[HealthFlag], ctx: DeviceHealthContext) -> HealthSeverity:
    if primary == HealthFlag.unavailable:
        return HealthSeverity.incident
    if primary == HealthFlag.router_risk and ctx.availability == "offline":
        return HealthSeverity.incident
    if primary == HealthFlag.healthy:
        return HealthSeverity.ok
    if primary == HealthFlag.unknown:
        return HealthSeverity.unknown
    if primary == HealthFlag.stale_reporting and HealthFlag.unavailable in flags:
        return HealthSeverity.incident
    return HealthSeverity.watch


def _confidence_for_primary(primary: HealthFlag, flags: list[HealthFlag], ctx: DeviceHealthContext) -> HealthConfidence:
    if primary == HealthFlag.unavailable:
        return HealthConfidence.high
    if primary == HealthFlag.low_battery:
        return HealthConfidence.high
    if primary == HealthFlag.healthy:
        return HealthConfidence.medium if ctx.availability == "unknown" else HealthConfidence.high
    if primary == HealthFlag.unknown:
        return HealthConfidence.low
    if primary == HealthFlag.recently_unstable and ctx.availability_change_count >= 5:
        return HealthConfidence.high
    return HealthConfidence.medium


def _summary_for_primary(primary: HealthFlag, ctx: DeviceHealthContext) -> str:
    snippets = {
        HealthFlag.unavailable: "Zigbee2MQTT currently reports this device as unavailable.",
        HealthFlag.recently_unstable: (
            "This device has changed availability several times recently. ZigbeeLens cannot determine "
            "from this alone whether the cause is the device, router path, interference, or coordinator."
        ),
        HealthFlag.weak_link: (
            "The latest linkquality is below the configured weak-link threshold. "
            "Linkquality can fluctuate, so this should be treated as a signal rather than proof."
        ),
        HealthFlag.low_battery: (
            "The latest battery reading is below the configured threshold. "
            "Some devices report battery infrequently, so confirm against recent updates."
        ),
        HealthFlag.stale_reporting: (
            "ZigbeeLens has not observed a recent payload from this device. "
            "Some sleepy battery devices report infrequently by design."
        ),
        HealthFlag.interview_issue: "Zigbee2MQTT inventory indicates an interview or configuration issue.",
        HealthFlag.router_risk: (
            "This router has health signals that may matter to nearby devices. "
            "ZigbeeLens cannot prove dependent routes without topology data."
        ),
        HealthFlag.unknown: "ZigbeeLens has not observed enough data to classify this device yet.",
        HealthFlag.healthy: "ZigbeeLens has not detected any current health concerns for this device.",
    }
    return snippets.get(primary, "Device health classified from available MQTT telemetry.")


def _flag_order(flag: HealthFlag) -> int:
    order = {
        HealthFlag.unavailable: 1,
        HealthFlag.router_risk: 2,
        HealthFlag.recently_unstable: 3,
        HealthFlag.interview_issue: 4,
        HealthFlag.stale_reporting: 5,
        HealthFlag.weak_link: 6,
        HealthFlag.low_battery: 7,
        HealthFlag.unknown: 8,
        HealthFlag.healthy: 9,
    }
    return order.get(flag, 99)


def sort_priority_from_health(primary: HealthFlag) -> int:
    return _flag_order(primary)
