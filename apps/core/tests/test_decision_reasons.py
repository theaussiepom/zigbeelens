"""Tests for the shared reason-code catalogue."""

from __future__ import annotations

from zigbeelens.decisions.reasons import REASON_CODES, ReasonCode


def test_reason_codes_are_unique():
    values = [member.value for member in ReasonCode]
    assert len(values) == len(set(values))


def test_reason_codes_include_topology_and_device_examples():
    assert ReasonCode.latest_snapshot_no_links.value in REASON_CODES
    assert ReasonCode.battery_low.value in REASON_CODES
    assert ReasonCode.shared_availability_event.value in REASON_CODES
    assert ReasonCode.router_area_issue_cluster.value in REASON_CODES


def test_reason_codes_are_not_topology_only():
    assert ReasonCode.ha_areas_not_linked.value in REASON_CODES
    assert ReasonCode.insufficient_history.value in REASON_CODES
