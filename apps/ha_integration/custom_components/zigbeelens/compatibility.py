"""Core version and decision-contract compatibility helpers for the HACS companion.

Track 5 requires exact decision contract v2. Missing, older, newer, or malformed
contracts disable companion decision display — never fall back to Health/Lens.
"""

from __future__ import annotations

from typing import Any

# Must match apps/core/.../api/summary.py DECISION_CONTRACT_VERSION.
DECISION_CONTRACT_VERSION = 2

# Exact versions this HACS package understands. Do not treat newer as compatible.
SUPPORTED_DECISION_CONTRACT_VERSIONS = frozenset({2})

REQUIRED_COMPANION_CAPABILITIES = frozenset(
    {
        "shared_decisions",
        "companion_decision_summary",
        "decision_only_diagnostic_payloads",
        "report_contract_v3",
        "decision_mqtt_summary",
    }
)

REQUIRED_COMPANION_DECISION_SURFACES = frozenset(
    {
        "dashboard_decision_summary",
        "dashboard_investigation_priorities",
        "dashboard_data_coverage_warnings",
        "network_decision_badges",
        "device_decision_badges",
    }
)

KNOWN_DECISION_STATUSES = frozenset(
    {
        "informational",
        "no_notable_change",
        "changed",
        "watch",
        "worth_reviewing",
        "review_first",
        "improve_data_coverage",
        "data_unavailable",
    }
)

DECISION_STATUS_ORDER = (
    "review_first",
    "worth_reviewing",
    "improve_data_coverage",
    "watch",
    "changed",
    "informational",
    "no_notable_change",
    "data_unavailable",
)

KNOWN_DECISION_PRIORITIES = frozenset(
    {
        "none",
        "low",
        "medium",
        "high",
    }
)

DECISION_PRIORITY_ORDER = (
    "high",
    "medium",
    "low",
    "none",
)

KNOWN_COVERAGE_LABEL_CODES = frozenset(
    {
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
    }
)

# Absolute minimum Core this integration expects for basic operational use.
MIN_CORE_VERSION = (0, 1, 0)


def parse_core_version(version: str | None) -> tuple[int, ...] | None:
    """Parse a dotted Core version into an int tuple; ignore pre-release suffixes."""
    if not version or not isinstance(version, str):
        return None
    cleaned = version.strip().split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for piece in cleaned.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) if parts else None


def core_version_compatible(version: str | None, *, minimum: tuple[int, ...] = MIN_CORE_VERSION) -> bool:
    """Return True when version is missing (unknown) or at/above minimum."""
    parsed = parse_core_version(version)
    if parsed is None:
        return True
    return parsed >= minimum


def nonneg_int_not_bool(value: Any) -> int | None:
    """Return a non-negative int or None when missing, bool, float, or invalid."""
    if value is None or isinstance(value, bool):
        return None
    if type(value) is not int:
        return None
    if value < 0:
        return None
    return value


def decision_contract_version(capabilities: dict[str, Any] | None) -> int:
    """Strict parse of decision_contract_version. Unsupported/malformed → 0."""
    if not isinstance(capabilities, dict):
        return 0
    raw = capabilities.get("decision_contract_version")
    if type(raw) is not int or raw < 0:
        return 0
    return raw


def supports_companion_decisions(capabilities: dict[str, Any] | None) -> bool:
    """Soft gate: True only for an exact supported companion decision contract."""
    if not isinstance(capabilities, dict):
        return False
    if decision_contract_version(capabilities) not in SUPPORTED_DECISION_CONTRACT_VERSIONS:
        return False
    caps = capabilities.get("capabilities")
    if not isinstance(caps, dict):
        return False
    for name in REQUIRED_COMPANION_CAPABILITIES:
        if caps.get(name) is not True:
            return False
    # Explicit negative fact — missing/null/string/0 must not pass.
    if caps.get("legacy_health_lens_payloads") is not False:
        return False
    surfaces = capabilities.get("decision_surfaces")
    if not isinstance(surfaces, dict):
        return False
    for surface in REQUIRED_COMPANION_DECISION_SURFACES:
        if surfaces.get(surface) is not True:
            return False
    return True


def validate_decision_count_summary(summary: Any) -> bool:
    """True when a DecisionCountSummary dict is a pure subject-count fold."""
    if not isinstance(summary, dict):
        return False
    subject_count = nonneg_int_not_bool(summary.get("subject_count"))
    if subject_count is None:
        return False
    overall = summary.get("overall_status")
    if not isinstance(overall, str) or overall not in KNOWN_DECISION_STATUSES:
        return False
    highest = summary.get("highest_priority")
    if not isinstance(highest, str) or highest not in KNOWN_DECISION_PRIORITIES:
        return False
    coverage = nonneg_int_not_bool(summary.get("coverage_warning_count"))
    if coverage is None:
        return False
    status_counts = summary.get("status_counts")
    if not isinstance(status_counts, dict):
        return False
    priority_counts = summary.get("priority_counts")
    if not isinstance(priority_counts, dict):
        return False

    status_total = 0
    for key, count in status_counts.items():
        if key not in KNOWN_DECISION_STATUSES:
            return False
        parsed = nonneg_int_not_bool(count)
        if parsed is None:
            return False
        status_total += parsed

    priority_total = 0
    for key, count in priority_counts.items():
        if key not in KNOWN_DECISION_PRIORITIES:
            return False
        parsed = nonneg_int_not_bool(count)
        if parsed is None:
            return False
        priority_total += parsed

    if subject_count == 0:
        return (
            not status_counts
            and not priority_counts
            and overall == "data_unavailable"
            and highest == "none"
        )

    if status_total != subject_count or priority_total != subject_count:
        return False

    expected_overall = "data_unavailable"
    for status in DECISION_STATUS_ORDER:
        parsed = nonneg_int_not_bool(status_counts.get(status))
        if parsed is not None and parsed > 0:
            expected_overall = status
            break
    if overall != expected_overall:
        return False

    expected_priority = "none"
    for priority in DECISION_PRIORITY_ORDER:
        parsed = nonneg_int_not_bool(priority_counts.get(priority))
        if parsed is not None and parsed > 0:
            expected_priority = priority
            break
    return highest == expected_priority


def validate_decision_badge(badge: Any) -> bool:
    """True when a compact decision badge dict is structurally valid."""
    if not isinstance(badge, dict):
        return False
    status = badge.get("status")
    if not isinstance(status, str) or status not in KNOWN_DECISION_STATUSES:
        return False
    priority = badge.get("priority")
    if not isinstance(priority, str) or priority not in KNOWN_DECISION_PRIORITIES:
        return False
    headline = badge.get("headline_code")
    if not isinstance(headline, str) or not headline.strip():
        return False
    if "coverage_label_codes" not in badge:
        return False
    codes = badge.get("coverage_label_codes")
    if not isinstance(codes, list):
        return False
    for code in codes:
        if not isinstance(code, str) or code not in KNOWN_COVERAGE_LABEL_CODES:
            return False
    return True


def _validate_dashboard_factual_fields(dashboard: dict[str, Any]) -> bool:
    for field in (
        "active_incident_count",
        "watching_incident_count",
        "device_count",
        "unavailable_device_count",
    ):
        if nonneg_int_not_bool(dashboard.get(field)) is None:
            return False
    if "network_count" in dashboard:
        if nonneg_int_not_bool(dashboard.get("network_count")) is None:
            return False
    return True


def _validate_network_decision_badges(networks: Any) -> bool:
    if not isinstance(networks, list):
        return False
    for net in networks:
        if not isinstance(net, dict):
            return False
        if not validate_decision_badge(net.get("decision")):
            return False
        if not validate_decision_count_summary(net.get("decision_summary")):
            return False
        for field in ("device_count", "unavailable_count", "active_incident_count"):
            if nonneg_int_not_bool(net.get(field)) is None:
                return False
    return True


def dashboard_decision_payload_valid(dashboard: dict[str, Any] | None) -> bool:
    """True when Dashboard advertises a valid contract-v2 decision payload."""
    if not isinstance(dashboard, dict):
        return False
    if not isinstance(dashboard.get("investigation_priorities"), list):
        return False
    if not isinstance(dashboard.get("data_coverage_warnings"), list):
        return False
    if not validate_decision_count_summary(dashboard.get("decision_summary")):
        return False
    if not _validate_dashboard_factual_fields(dashboard):
        return False
    return _validate_network_decision_badges(dashboard.get("networks"))
