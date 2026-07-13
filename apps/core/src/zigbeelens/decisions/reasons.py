"""Stable reason-code catalogue for decision services.

Decision services emit these codes plus optional params. Presenters and
ViewModels map them to user-facing copy — final prose does not belong here.
"""

from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    latest_snapshot_no_links = "latest_snapshot_no_links"
    selected_snapshot_had_links = "selected_snapshot_had_links"
    snapshot_link_count_changed = "snapshot_link_count_changed"
    route_hints_changed = "route_hints_changed"
    availability_tracking_off = "availability_tracking_off"
    availability_history_building = "availability_history_building"
    availability_status_unknown = "availability_status_unknown"
    route_hints_unavailable = "route_hints_unavailable"
    ha_areas_not_linked = "ha_areas_not_linked"
    snapshot_stale = "snapshot_stale"
    current_issue_present = "current_issue_present"
    battery_low = "battery_low"
    last_seen_stale = "last_seen_stale"
    reported_lqi_low = "reported_lqi_low"
    recent_missing_links_present = "recent_missing_links_present"
    last_known_links_present = "last_known_links_present"
    passive_instability_hint_present = "passive_instability_hint_present"
    shared_availability_event = "shared_availability_event"
    insufficient_history = "insufficient_history"
    observed_reporting_rhythm = "observed_reporting_rhythm"
    reporting_silence_beyond_expected = "reporting_silence_beyond_expected"


REASON_CODES: frozenset[str] = frozenset(member.value for member in ReasonCode)

# Future pattern/cluster codes (e.g. router_area_issue_cluster,
# model_pattern_observed) belong in later phases once the intelligence exists.
