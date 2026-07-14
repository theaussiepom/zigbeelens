"""User-facing copy for shared decision statuses, reasons and coverage labels.

Backend decision services emit stable codes plus params. This module maps
them to approved prose for UI and reports. Do not invent diagnostic meaning
elsewhere — map it here instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

REASON_CODES: tuple[str, ...] = (
    "latest_snapshot_no_links",
    "selected_snapshot_had_links",
    "snapshot_link_count_changed",
    "route_hints_changed",
    "availability_tracking_off",
    "availability_history_building",
    "availability_status_unknown",
    "route_hints_unavailable",
    "ha_areas_not_linked",
    "snapshot_stale",
    "current_issue_present",
    "battery_low",
    "last_seen_stale",
    "reported_lqi_low",
    "recent_missing_links_present",
    "last_known_links_present",
    "passive_instability_hint_present",
    "shared_availability_event",
    "insufficient_history",
    "observed_reporting_rhythm",
    "reporting_silence_beyond_expected",
    "observed_lqi_trend",
    "reported_lqi_declining",
    "model_pattern_observed",
)

COVERAGE_LABEL_CODES: tuple[str, ...] = (
    "availability_tracking_off",
    "availability_history_building",
    "availability_status_unknown",
    "availability_available",
    "route_hints_unavailable",
    "ha_areas_not_linked",
    "snapshot_stale",
    "battery_history_sparse",
    "battery_history_available",
    "lqi_history_sparse",
    "lqi_history_available",
    "last_seen_available",
    "last_seen_unknown",
    "last_payload_available",
    "last_payload_unknown",
    "topology_history_available",
    "topology_history_sparse",
    "topology_history_not_observed",
    "ha_area_linked",
)

HEADLINE_CODES: tuple[str, ...] = (
    "current_issue_present",
    "topology_evidence_gap",
    "availability_tracking_needed",
    "stale_last_seen",
    "low_battery",
    "data_coverage_gaps",
    "no_notable_signals",
    "extended_reporting_silence",
    "reported_link_quality_changed",
)

LIMITATION_CODES: tuple[str, ...] = (
    "absence_from_latest_not_failure",
    "route_hints_not_live_routing",
    "availability_limits_interpretation",
    "extended_silence_not_failure",
    "reported_lqi_not_path_failure",
    "model_pattern_not_causal",
)

SUGGESTED_CHECK_CODES: tuple[str, ...] = (
    "confirm_powered",
    "confirm_reporting_in_z2m",
    "compare_earlier_snapshot",
    "route_hints_context_only",
    "enable_availability_reporting",
    "check_battery_level",
    "compare_same_model_device_context",
    "review_same_model_availability_history",
)

DECISION_STATUS_LABELS: dict[str, str] = {
    "informational": "Informational",
    "no_notable_change": "No notable change",
    "changed": "Changed",
    "watch": "Watch",
    "worth_reviewing": "Worth reviewing",
    "review_first": "Review first",
    "improve_data_coverage": "Improve data coverage",
    "data_unavailable": "Data unavailable",
}

HEADLINE_COPY: dict[str, str] = {
    "current_issue_present": "Current issue needs attention",
    "topology_evidence_gap": "Topology evidence gap",
    "availability_tracking_needed": "Availability tracking needed",
    "stale_last_seen": "Last seen looks stale",
    "low_battery": "Battery reported low",
    "data_coverage_gaps": "Data coverage gaps",
    "no_notable_signals": "No notable signals",
    "extended_reporting_silence": "Extended reporting silence",
    "reported_link_quality_changed": "Reported link quality changed",
}

COVERAGE_LABEL_COPY: dict[str, str] = {
    "availability_tracking_off": "Availability tracking off",
    "availability_history_building": "Availability history building",
    "availability_status_unknown": "Availability status unknown",
    "availability_available": "Availability: available",
    "route_hints_unavailable": "Route hints unavailable",
    "ha_areas_not_linked": "HA areas not linked",
    "snapshot_stale": "Snapshot stale",
    "battery_history_sparse": "Battery history sparse",
    "battery_history_available": "Battery history available",
    "lqi_history_sparse": "LQI history sparse",
    "lqi_history_available": "LQI history available",
    "last_seen_available": "Last seen: available",
    "last_seen_unknown": "Last seen: unknown",
    "last_payload_available": "Last payload: available",
    "last_payload_unknown": "Last payload: unknown",
    "topology_history_available": "Topology history: available",
    "topology_history_sparse": "Topology history: sparse",
    "topology_history_not_observed": "Topology history: not observed",
    "ha_area_linked": "HA area: linked",
}

DEVICE_COVERAGE_LABEL_COPY: dict[str, str] = {
    **COVERAGE_LABEL_COPY,
    "availability_tracking_off": "Availability: tracking off",
    "availability_history_building": "Availability: building",
    "availability_status_unknown": "Availability: unknown",
    "ha_areas_not_linked": "HA area: missing",
}

CopyRenderer = Callable[[dict[str, Any]], str]


def _count_param(params: dict[str, Any], key: str) -> int | None:
    value = params.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _string_param(params: dict[str, Any], key: str) -> str | None:
    value = params.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _format_minute_span(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"
    hours = minutes // 60
    remainder = minutes % 60
    return (
        f"{hours} hour{'s' if hours != 1 else ''} "
        f"{remainder} minute{'s' if remainder != 1 else ''}"
    )


def _sample_count_label(count: int) -> str:
    return f"{count} sample{'s' if count != 1 else ''}"


def _device_battery_history_available_label(params: dict[str, Any]) -> str:
    count = _count_param(params, "sample_count")
    if count is None:
        return "Battery history: available"
    return f"Battery history: available ({_sample_count_label(count)})"


def _device_battery_history_sparse_label(params: dict[str, Any]) -> str:
    count = _count_param(params, "sample_count")
    if count is None:
        return "Battery history: sparse"
    return f"Battery history: sparse ({_sample_count_label(count)})"


def _device_lqi_history_available_label(params: dict[str, Any]) -> str:
    count = _count_param(params, "sample_count")
    if count is None:
        return "LQI history: available"
    return f"LQI history: available ({_sample_count_label(count)})"


def _device_lqi_history_sparse_label(params: dict[str, Any]) -> str:
    count = _count_param(params, "sample_count")
    if count is None:
        return "LQI history: sparse"
    return f"LQI history: sparse ({_sample_count_label(count)})"


def _topology_history_label(params: dict[str, Any], fallback: str) -> str:
    observed = _count_param(params, "observed_snapshot_count")
    window = _count_param(params, "snapshot_window_count")
    if observed is None or window is None:
        return fallback
    return f"Topology history: {observed} of {window} snapshots"


def _suggested_check_battery_level(params: dict[str, Any]) -> str:
    percent = _count_param(params, "battery_percent")
    if percent is None:
        return "Check the reported battery level."
    return f"Check the reported battery level ({percent}%)."


def _reason_latest_snapshot_no_links(_params: dict[str, Any]) -> str:
    return "Latest snapshot shows no links for this device."


def _reason_selected_snapshot_had_links(params: dict[str, Any]) -> str:
    count = _count_param(params, "selected_snapshot_link_count")
    if count is None:
        return "Selected snapshot showed links for this device."
    return f"Selected snapshot showed {count} link{'s' if count != 1 else ''} for this device."


def _reason_snapshot_link_count_changed(params: dict[str, Any]) -> str:
    latest = _count_param(params, "latest_link_count")
    selected = _count_param(params, "selected_link_count")
    if latest is None or selected is None:
        return "Link counts differ between the selected snapshot and the latest snapshot."
    return (
        f"Link count changed from {selected} in the selected snapshot "
        f"to {latest} in the latest snapshot."
    )


def _reason_route_hints_changed(_params: dict[str, Any]) -> str:
    return (
        "Route-hint counts differ between snapshots. "
        "Route hints do not prove live routing changed."
    )


def _reason_availability_tracking_off(_params: dict[str, Any]) -> str:
    return "Availability tracking is off."


def _reason_availability_history_building(_params: dict[str, Any]) -> str:
    return "Availability history is still building."


def _reason_availability_status_unknown(_params: dict[str, Any]) -> str:
    return "Availability status could not be confirmed from stored evidence."


def _reason_route_hints_unavailable(_params: dict[str, Any]) -> str:
    return "Route hints are unavailable for this network."


def _reason_ha_areas_not_linked(_params: dict[str, Any]) -> str:
    return "Home Assistant areas are not linked for this device."


def _reason_snapshot_stale(_params: dict[str, Any]) -> str:
    return "Latest topology snapshot is stale."


def _reason_current_issue_present(_params: dict[str, Any]) -> str:
    return "This device currently needs attention based on existing issue signals."


def _reason_battery_low(_params: dict[str, Any]) -> str:
    return "Battery is currently reported low."


def _reason_last_seen_stale(_params: dict[str, Any]) -> str:
    return "Last-seen reporting looks stale."


def _reason_reported_lqi_low(_params: dict[str, Any]) -> str:
    return "Reported link quality is low."


def _reason_recent_missing_links_present(_params: dict[str, Any]) -> str:
    return "Recent missing links are shown for this device in the mesh view."


def _reason_last_known_links_present(_params: dict[str, Any]) -> str:
    return "Last-known links are shown for this device in the mesh view."


def _reason_passive_instability_hint_present(_params: dict[str, Any]) -> str:
    return "Passive investigation hints suggest instability worth checking."


def _reason_shared_availability_event(_params: dict[str, Any]) -> str:
    return "Multiple devices changed availability around the same time."


def _reason_insufficient_history(_params: dict[str, Any]) -> str:
    return "Not enough history is available yet for a stronger judgement."


def _reason_observed_reporting_rhythm(params: dict[str, Any]) -> str:
    p25 = _count_param(params, "interval_minutes_p25")
    p75 = _count_param(params, "interval_minutes_p75")
    if p25 is None or p75 is None:
        return "Stored payload observations show a reporting rhythm for this device."
    if p25 == p75:
        return (
            f"Usually reports about every {_format_minute_span(p25)} "
            "based on stored payload history."
        )
    return (
        f"Usually reports every {_format_minute_span(p25)}–{_format_minute_span(p75)} "
        "based on stored payload history."
    )


def _reason_reporting_silence_beyond_expected(params: dict[str, Any]) -> str:
    silence_minutes = _count_param(params, "silence_minutes")
    if silence_minutes is None:
        return "Current payload silence is longer than the observed reporting cadence."
    return f"No payload observed for {_format_minute_span(silence_minutes)}."


def _reason_observed_lqi_trend(params: dict[str, Any]) -> str:
    earlier_median = _count_param(params, "earlier_median")
    recent_median = _count_param(params, "recent_median")
    if earlier_median is not None and recent_median is not None:
        return (
            f"Reported link quality median changed from {earlier_median} to "
            f"{recent_median} across the compared stored observation windows."
        )
    sample_count = _count_param(params, "sample_count")
    window_size = _count_param(params, "window_size")
    if sample_count is not None and window_size is not None:
        return (
            f"Stored reported link-quality observations from "
            f"{_sample_count_label(sample_count)} were compared across "
            f"{window_size}-observation windows."
        )
    return (
        "Stored reported link-quality observations show a trend across "
        "compared observation windows."
    )


def _reason_reported_lqi_declining(_params: dict[str, Any]) -> str:
    return "Reported link quality is lower in the recent stored observations."


def _reason_model_pattern_observed(params: dict[str, Any]) -> str:
    affected_count = _count_param(params, "affected_count")
    group_size = _count_param(params, "group_size")
    lookback_days = _count_param(params, "lookback_days")
    current_device_affected = params.get("current_device_affected") is True
    if affected_count is not None and group_size is not None and lookback_days is not None:
        day_word = "day" if lookback_days == 1 else "days"
        if current_device_affected:
            return (
                f"This device is one of {affected_count} of {group_size} devices "
                f"with the same model that went offline in the last {lookback_days} "
                f"{day_word}."
            )
        return (
            f"Other devices with the same model show a recent availability pattern: "
            f"{affected_count} of {group_size} went offline in the last "
            f"{lookback_days} {day_word}."
        )
    return (
        "Multiple devices with the same stored model identity show a recent "
        "availability pattern worth reviewing."
    )


REASON_COPY: dict[str, CopyRenderer] = {
    "latest_snapshot_no_links": _reason_latest_snapshot_no_links,
    "selected_snapshot_had_links": _reason_selected_snapshot_had_links,
    "snapshot_link_count_changed": _reason_snapshot_link_count_changed,
    "route_hints_changed": _reason_route_hints_changed,
    "availability_tracking_off": _reason_availability_tracking_off,
    "availability_history_building": _reason_availability_history_building,
    "availability_status_unknown": _reason_availability_status_unknown,
    "route_hints_unavailable": _reason_route_hints_unavailable,
    "ha_areas_not_linked": _reason_ha_areas_not_linked,
    "snapshot_stale": _reason_snapshot_stale,
    "current_issue_present": _reason_current_issue_present,
    "battery_low": _reason_battery_low,
    "last_seen_stale": _reason_last_seen_stale,
    "reported_lqi_low": _reason_reported_lqi_low,
    "recent_missing_links_present": _reason_recent_missing_links_present,
    "last_known_links_present": _reason_last_known_links_present,
    "passive_instability_hint_present": _reason_passive_instability_hint_present,
    "shared_availability_event": _reason_shared_availability_event,
    "insufficient_history": _reason_insufficient_history,
    "observed_reporting_rhythm": _reason_observed_reporting_rhythm,
    "reporting_silence_beyond_expected": _reason_reporting_silence_beyond_expected,
    "observed_lqi_trend": _reason_observed_lqi_trend,
    "reported_lqi_declining": _reason_reported_lqi_declining,
    "model_pattern_observed": _reason_model_pattern_observed,
}

LIMITATION_COPY: dict[str, CopyRenderer] = {
    "absence_from_latest_not_failure": lambda _params: (
        "Absence from the latest snapshot does not prove the device failed or left the network."
    ),
    "route_hints_not_live_routing": lambda _params: (
        "Route hints describe stored snapshot evidence. They do not prove live routing paths."
    ),
    "availability_limits_interpretation": lambda _params: (
        "Availability and last-seen evidence is limited for this period, so offline or "
        "stale interpretation is constrained."
    ),
    "extended_silence_not_failure": lambda _params: (
        "Silence longer than the observed reporting rhythm does not prove the device failed, "
        "lost power, or left the network."
    ),
    "reported_lqi_not_path_failure": lambda _params: (
        "A drop in reported link quality does not prove a Zigbee path, route, or device failure."
    ),
    "model_pattern_not_causal": lambda _params: (
        "A pattern among devices with the same stored model identity does not prove a model "
        "defect, manufacturer fault, or shared cause."
    ),
}

SUGGESTED_CHECK_COPY: dict[str, CopyRenderer] = {
    "confirm_powered": lambda _params: "Confirm the device is powered.",
    "confirm_reporting_in_z2m": lambda _params: "Confirm the device is reporting in Zigbee2MQTT.",
    "compare_earlier_snapshot": lambda _params: (
        "Compare an earlier topology snapshot for this device."
    ),
    "route_hints_context_only": lambda _params: (
        "Treat route hints as context only — they do not prove current routing."
    ),
    "enable_availability_reporting": lambda _params: (
        "Enable Zigbee2MQTT availability and last-seen reporting."
    ),
    "check_battery_level": lambda params: _suggested_check_battery_level(params),
    "compare_same_model_device_context": lambda _params: (
        "Compare power, placement, firmware or version information where stored for devices "
        "with the same model identity."
    ),
    "review_same_model_availability_history": lambda _params: (
        "Review availability timing for affected devices with the same model identity."
    ),
}

DEVICE_COVERAGE_LABEL_RENDERERS: dict[str, CopyRenderer] = {
    "availability_tracking_off": lambda _params: "Availability: tracking off",
    "availability_history_building": lambda _params: "Availability: building",
    "availability_status_unknown": lambda _params: "Availability: unknown",
    "availability_available": lambda _params: "Availability: available",
    "last_seen_available": lambda _params: "Last seen: available",
    "last_seen_unknown": lambda _params: "Last seen: unknown",
    "last_payload_available": lambda _params: "Last payload: available",
    "last_payload_unknown": lambda _params: "Last payload: unknown",
    "battery_history_available": lambda params: _device_battery_history_available_label(params),
    "battery_history_sparse": lambda params: _device_battery_history_sparse_label(params),
    "lqi_history_available": lambda params: _device_lqi_history_available_label(params),
    "lqi_history_sparse": lambda params: _device_lqi_history_sparse_label(params),
    "topology_history_available": lambda params: _topology_history_label(
        params, "Topology history: available"
    ),
    "topology_history_sparse": lambda params: _topology_history_label(
        params, "Topology history: sparse"
    ),
    "topology_history_not_observed": lambda params: _topology_history_label(
        params, "Topology history: not observed"
    ),
    "ha_area_linked": lambda params: (
        f"HA area: {_string_param(params, 'area_name')}"
        if _string_param(params, "area_name")
        else (
            f"HA area: {_string_param(params, 'area_id')}"
            if _string_param(params, "area_id")
            else "HA area: linked"
        )
    ),
    "ha_areas_not_linked": lambda _params: "HA area: missing",
}


def _is_known_reason_code(code: str) -> bool:
    return code in REASON_COPY


def _is_known_coverage_label_code(label_code: str) -> bool:
    return label_code in COVERAGE_LABEL_COPY


def _is_known_decision_status(status: str) -> bool:
    return status in DECISION_STATUS_LABELS


def _is_known_headline_code(code: str) -> bool:
    return code in HEADLINE_COPY


def _is_known_limitation_code(code: str) -> bool:
    return code in LIMITATION_COPY


def _is_known_suggested_check_code(code: str) -> bool:
    return code in SUGGESTED_CHECK_COPY


def decision_status_label(status: str) -> str:
    if not _is_known_decision_status(status):
        return "Status unknown"
    return DECISION_STATUS_LABELS[status]


def headline_text(code: str) -> str:
    if not _is_known_headline_code(code):
        return "Device story summary unavailable."
    return HEADLINE_COPY[code]


def reason_text(code: str, params: dict | None = None) -> str:
    resolved_params = params or {}
    if not _is_known_reason_code(code):
        return "Details unavailable."
    return REASON_COPY[code](resolved_params)


def coverage_label(code: str, params: dict | None = None) -> str:
    _ = params
    if not _is_known_coverage_label_code(code):
        return "Coverage status unknown"
    return COVERAGE_LABEL_COPY[code]


def device_coverage_label(code: str, params: dict | None = None) -> str:
    resolved_params = params or {}
    if not _is_known_coverage_label_code(code):
        return "Coverage status unknown"
    renderer = DEVICE_COVERAGE_LABEL_RENDERERS.get(code)
    if renderer is not None:
        return renderer(resolved_params)
    return DEVICE_COVERAGE_LABEL_COPY[code]


def limitation_text(code: str, params: dict | None = None) -> str:
    resolved_params = params or {}
    if not _is_known_limitation_code(code):
        return "Interpretation is limited for this evidence."
    return LIMITATION_COPY[code](resolved_params)


def suggested_check_text(code: str, params: dict | None = None) -> str:
    resolved_params = params or {}
    if not _is_known_suggested_check_code(code):
        return "Review stored evidence before taking action."
    return SUGGESTED_CHECK_COPY[code](resolved_params)
