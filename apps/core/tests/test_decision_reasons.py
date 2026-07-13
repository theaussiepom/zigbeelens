"""Tests for the shared reason-code catalogue."""

from __future__ import annotations

from zigbeelens.decisions.reasons import REASON_CODES, ReasonCode

PHASE_1_REASON_CODES = frozenset(
    {
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
    }
)

SPECULATIVE_FUTURE_REASON_CODES = frozenset(
    {
        "router_area_issue_cluster",
        "model_pattern_observed",
    }
)


def test_reason_codes_are_unique():
    values = [member.value for member in ReasonCode]
    assert len(values) == len(set(values))


PHASE_4B_REASON_CODES = frozenset(
    {
        "observed_reporting_rhythm",
        "reporting_silence_beyond_expected",
    }
)


def test_phase_1_reason_codes_match_conservative_set():
    assert REASON_CODES == PHASE_1_REASON_CODES | PHASE_4B_REASON_CODES


def test_speculative_future_reason_codes_are_not_stabilised():
    assert SPECULATIVE_FUTURE_REASON_CODES.isdisjoint(REASON_CODES)


def test_reason_codes_include_topology_and_device_examples():
    assert ReasonCode.latest_snapshot_no_links.value in REASON_CODES
    assert ReasonCode.battery_low.value in REASON_CODES
    assert ReasonCode.shared_availability_event.value in REASON_CODES


def test_reason_codes_are_not_topology_only():
    assert ReasonCode.ha_areas_not_linked.value in REASON_CODES
    assert ReasonCode.insufficient_history.value in REASON_CODES
