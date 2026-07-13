"""Deterministic, evidence-gated device stories for the decision engine.

Device stories assemble neutral facts from stored evidence, apply bounded
deterministic rules, and emit coded reasons, coverage, limitations and checks.
Presenters map codes to user-facing copy — no prose belongs here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from zigbeelens.decisions import coverage as coverage_helpers
from zigbeelens.decisions.availability_tracking import availability_tracking_enabled_now
from zigbeelens.decisions.reasons import ReasonCode
from zigbeelens.decisions.topology_facts import (
    TopologyFactCode,
    build_device_latest_topology_facts,
    build_device_snapshot_comparison_facts,
    normalize_device_ieee,
)
from zigbeelens.decisions.types import (
    DataCoverage,
    DecisionLimitation,
    DecisionPriority,
    DecisionReason,
    DecisionStatus,
    EvidenceFact,
    EvidenceReference,
    SuggestedCheck,
)
from zigbeelens.decisions.reporting_rhythm import ReportingRhythm, reporting_rhythm_for_device
from zigbeelens.decisions.reporting_silence import (
    ReportingSilence,
    SilenceState,
    build_reporting_silence,
)
from zigbeelens.topology.device_compare import (
    COVERAGE_BUILDING,
    COVERAGE_UNKNOWN,
    device_snapshot_history,
)
from zigbeelens.topology.history import aggregate_historical_evidence, aggregate_last_known_links
from zigbeelens.topology.investigations import LOW_BATTERY_PERCENT, STALE_LAST_SEEN_HOURS

if TYPE_CHECKING:
    from zigbeelens.storage.repository import Repository


class HeadlineCode(StrEnum):
    """Stable presenter codes for device story headlines."""

    current_issue_present = "current_issue_present"
    topology_evidence_gap = "topology_evidence_gap"
    availability_tracking_needed = "availability_tracking_needed"
    stale_last_seen = "stale_last_seen"
    low_battery = "low_battery"
    data_coverage_gaps = "data_coverage_gaps"
    no_notable_signals = "no_notable_signals"
    extended_reporting_silence = "extended_reporting_silence"


class CheckCode(StrEnum):
    """Practical suggested checks for device stories."""

    confirm_powered = "confirm_powered"
    confirm_reporting_in_z2m = "confirm_reporting_in_z2m"
    compare_earlier_snapshot = "compare_earlier_snapshot"
    route_hints_context_only = "route_hints_context_only"
    enable_availability_reporting = "enable_availability_reporting"
    check_battery_level = "check_battery_level"


class LimitationCode(StrEnum):
    """Interpretation limits for device stories."""

    route_hints_not_live_routing = "route_hints_not_live_routing"
    absence_from_latest_not_failure = "absence_from_latest_not_failure"
    availability_limits_interpretation = "availability_limits_interpretation"
    extended_silence_not_failure = "extended_silence_not_failure"


DEVICE_STORY_HEADLINE_CODES: frozenset[str] = frozenset(
    member.value for member in HeadlineCode
)

_INFORMATIONAL_COVERAGE_REASONS = frozenset(
    {
        ReasonCode.ha_areas_not_linked,
        ReasonCode.route_hints_unavailable,
    }
)


class DeviceStoryTimelineItem(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class DeviceStoryEvidence(BaseModel):
    """Bounded evidence inputs for one device story."""

    network_id: str
    device_ieee: str
    friendly_name: str | None = None
    availability: str | None = None
    last_seen: datetime | None = None
    last_payload_at: datetime | None = None
    linkquality: int | None = None
    battery: int | None = None
    has_current_issue: bool = False
    active_incident_ids: list[str] = Field(default_factory=list)
    availability_tracking_enabled: bool = False
    latest_availability_coverage: str | None = None
    topology_facts: list[EvidenceFact] = Field(default_factory=list)
    recent_missing_link_count: int = 0
    last_known_link_count: int = 0
    route_hints_available: bool = False
    latest_snapshot_id: str | None = None
    latest_snapshot_captured_at: datetime | None = None
    ha_area: str | None = None
    network_has_usable_ha_areas: bool = False
    reporting_rhythm: ReportingRhythm | None = None


class DeviceStory(BaseModel):
    """One device diagnostic story — presenters map codes to copy.

    Report consumers should use :func:`device_story_report_payload` or the
    identical Device Story API JSON; keep coded output and map copy in presenters.
    """

    subject_type: str = "device"
    subject_id: str
    status: DecisionStatus
    priority: DecisionPriority = DecisionPriority.none
    headline_code: str
    reasons: list[DecisionReason] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[DecisionLimitation] = Field(default_factory=list)
    suggested_checks: list[SuggestedCheck] = Field(default_factory=list)
    coverage: list[DataCoverage] = Field(default_factory=list)
    timeline: list[DeviceStoryTimelineItem] = Field(default_factory=list)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _norm(ieee: Any) -> str:
    return str(ieee or "").strip().lower()


def _fact_codes(facts: list[EvidenceFact]) -> set[str]:
    return {str(fact.code) for fact in facts}


def _count_touching_device(items: list[dict[str, Any]], device: str) -> int:
    count = 0
    for item in items:
        source = _norm(item.get("source_ieee"))
        target = _norm(item.get("target_ieee"))
        if device in (source, target):
            count += 1
    return count


def _network_route_hints_available(links: list[dict[str, Any]]) -> bool:
    return any((link.get("route_count") or 0) > 0 for link in links)


def load_device_story_evidence(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    now: datetime | None = None,
) -> DeviceStoryEvidence | None:
    """Load bounded stored evidence for one device. Returns None when unknown."""
    device = normalize_device_ieee(device_ieee)
    if not device:
        return None

    row = repo.get_device(network_id, device)
    if row is None:
        return None

    now = now or datetime.now(timezone.utc)
    active_incident_ids = repo.incidents.list_incidents_for_device(network_id, device)
    has_current_issue = row.availability == "offline" or bool(active_incident_ids)

    latest_snapshot = repo.get_latest_topology_snapshot(network_id)
    latest_snapshot_id = latest_snapshot["snapshot_id"] if latest_snapshot else None
    latest_nodes = (
        repo.list_topology_nodes(latest_snapshot_id) if latest_snapshot_id else []
    )
    latest_links = (
        repo.list_topology_links(latest_snapshot_id) if latest_snapshot_id else []
    )

    topology_facts = build_device_latest_topology_facts(
        device_ieee=device,
        latest_snapshot=latest_snapshot,
        nodes=latest_nodes,
        links=latest_links,
    )

    history = device_snapshot_history(repo, network_id, device)
    for snapshot_row in history.get("snapshots", []):
        topology_facts.extend(
            build_device_snapshot_comparison_facts(
                device_ieee=device,
                comparison_snapshot_row=snapshot_row,
            )
        )

    historical = aggregate_historical_evidence(repo, network_id, now=now)
    last_known = aggregate_last_known_links(repo, network_id)

    ha_enrichment = repo.get_ha_device_enrichment(network_id, device)

    latest_row = history.get("latest_snapshot")
    latest_availability_coverage = None
    if isinstance(latest_row, dict):
        coverage = latest_row.get("availability_coverage_status")
        if isinstance(coverage, str):
            latest_availability_coverage = coverage

    return DeviceStoryEvidence(
        network_id=network_id,
        device_ieee=device,
        friendly_name=row.friendly_name,
        availability=row.availability,
        last_seen=_parse_ts(row.last_seen),
        last_payload_at=_parse_ts(row.last_payload_at),
        linkquality=row.linkquality,
        battery=row.battery,
        has_current_issue=has_current_issue,
        active_incident_ids=list(active_incident_ids),
        availability_tracking_enabled=availability_tracking_enabled_now(repo, network_id),
        latest_availability_coverage=latest_availability_coverage,
        topology_facts=topology_facts,
        recent_missing_link_count=_count_touching_device(
            historical.get("historical_neighbors", []), device
        )
        + _count_touching_device(historical.get("historical_routes", []), device),
        last_known_link_count=_count_touching_device(
            last_known.get("last_known_links", []), device
        ),
        route_hints_available=_network_route_hints_available(latest_links),
        latest_snapshot_id=latest_snapshot_id,
        latest_snapshot_captured_at=_parse_ts(
            latest_snapshot.get("captured_at") if latest_snapshot else None
        ),
        ha_area=ha_enrichment.get("area_name") if ha_enrichment else None,
        network_has_usable_ha_areas=repo.network_has_usable_ha_area_assignments(network_id),
        reporting_rhythm=reporting_rhythm_for_device(repo, network_id, device),
    )


def build_device_story_coverage(evidence: DeviceStoryEvidence) -> list[DataCoverage]:
    """Compose device-scoped coverage from stored evidence signals."""
    items: list[DataCoverage] = []

    if not evidence.availability_tracking_enabled:
        items.append(coverage_helpers.availability_tracking_off())

    if evidence.latest_availability_coverage == COVERAGE_BUILDING:
        items.append(coverage_helpers.availability_history_building())

    if evidence.latest_availability_coverage == COVERAGE_UNKNOWN:
        items.append(coverage_helpers.availability_status_unknown())

    if not evidence.route_hints_available and evidence.latest_snapshot_id is not None:
        items.append(coverage_helpers.route_hints_unavailable())

    if (
        evidence.network_has_usable_ha_areas is False
        and evidence.ha_area is None
        and evidence.friendly_name is not None
    ):
        items.append(coverage_helpers.ha_areas_not_linked())

    return items


def _topology_gap(evidence: DeviceStoryEvidence) -> bool:
    fact_codes = _fact_codes(evidence.topology_facts)
    if TopologyFactCode.device_has_latest_links in fact_codes:
        return False
    return (
        evidence.last_known_link_count > 0
        or evidence.recent_missing_link_count > 0
        or TopologyFactCode.device_has_selected_snapshot_links in fact_codes
    )


def _append_unique_reason(
    reasons: list[DecisionReason], code: ReasonCode | str, **params: Any
) -> None:
    code_value = str(code)
    if any(reason.code == code_value for reason in reasons):
        return
    reasons.append(DecisionReason(code=code_value, params=params or {}))


def _append_unique_check(
    checks: list[SuggestedCheck], code: CheckCode | str, **params: Any
) -> None:
    code_value = str(code)
    if any(check.code == code_value for check in checks):
        return
    checks.append(SuggestedCheck(code=code_value, params=params or {}))


def _append_unique_limitation(
    limitations: list[DecisionLimitation], code: LimitationCode | str, **params: Any
) -> None:
    code_value = str(code)
    if any(limitation.code == code_value for limitation in limitations):
        return
    limitations.append(DecisionLimitation(code=code_value, params=params or {}))


def build_device_story(
    evidence: DeviceStoryEvidence,
    *,
    now: datetime | None = None,
) -> DeviceStory:
    """Apply deterministic device story rules to bounded evidence."""
    now = now or datetime.now(timezone.utc)
    reasons: list[DecisionReason] = []
    limitations: list[DecisionLimitation] = []
    checks: list[SuggestedCheck] = []
    evidence_refs: list[EvidenceReference] = []

    if evidence.latest_snapshot_id:
        evidence_refs.append(
            EvidenceReference(
                source="topology_snapshot",
                id=evidence.latest_snapshot_id,
                captured_at=evidence.latest_snapshot_captured_at,
            )
        )

    if evidence.has_current_issue:
        _append_unique_reason(reasons, ReasonCode.current_issue_present)
        _append_unique_check(checks, CheckCode.confirm_powered)
        _append_unique_check(checks, CheckCode.confirm_reporting_in_z2m)

    topology_gap = _topology_gap(evidence)
    if topology_gap:
        _append_unique_reason(reasons, ReasonCode.latest_snapshot_no_links)
        if evidence.last_known_link_count > 0:
            _append_unique_reason(
                reasons,
                ReasonCode.last_known_links_present,
                link_count=evidence.last_known_link_count,
            )
        if evidence.recent_missing_link_count > 0:
            _append_unique_reason(
                reasons,
                ReasonCode.recent_missing_links_present,
                link_count=evidence.recent_missing_link_count,
            )
        if TopologyFactCode.device_has_selected_snapshot_links in _fact_codes(
            evidence.topology_facts
        ):
            _append_unique_reason(reasons, ReasonCode.selected_snapshot_had_links)
        _append_unique_limitation(
            limitations, LimitationCode.absence_from_latest_not_failure
        )
        _append_unique_check(checks, CheckCode.compare_earlier_snapshot)
        _append_unique_check(checks, CheckCode.confirm_powered)

    if not evidence.availability_tracking_enabled:
        _append_unique_reason(reasons, ReasonCode.availability_tracking_off)
        _append_unique_check(checks, CheckCode.enable_availability_reporting)

    if evidence.latest_availability_coverage == COVERAGE_BUILDING:
        _append_unique_reason(reasons, ReasonCode.availability_history_building)

    if evidence.latest_availability_coverage == COVERAGE_UNKNOWN:
        _append_unique_reason(reasons, ReasonCode.availability_status_unknown)
        _append_unique_limitation(
            limitations, LimitationCode.availability_limits_interpretation
        )

    if evidence.last_seen is not None and now - evidence.last_seen >= timedelta(
        hours=STALE_LAST_SEEN_HOURS
    ):
        _append_unique_reason(
            reasons,
            ReasonCode.last_seen_stale,
            hours_since_last_seen=int((now - evidence.last_seen).total_seconds() // 3600),
        )

    if evidence.battery is not None and evidence.battery <= LOW_BATTERY_PERCENT:
        _append_unique_reason(
            reasons, ReasonCode.battery_low, battery_percent=evidence.battery
        )
        _append_unique_check(
            checks, CheckCode.check_battery_level, battery_percent=evidence.battery
        )

    if not evidence.route_hints_available and evidence.latest_snapshot_id is not None:
        _append_unique_reason(reasons, ReasonCode.route_hints_unavailable)
        _append_unique_limitation(limitations, LimitationCode.route_hints_not_live_routing)
        _append_unique_check(checks, CheckCode.route_hints_context_only)

    if evidence.network_has_usable_ha_areas is False and evidence.ha_area is None:
        _append_unique_reason(reasons, ReasonCode.ha_areas_not_linked)

    _apply_reporting_silence_rules(
        evidence=evidence,
        now=now,
        reasons=reasons,
        limitations=limitations,
        checks=checks,
    )

    coverage = build_device_story_coverage(evidence)

    status, priority, headline_code = _resolve_story_outcome(
        evidence=evidence,
        topology_gap=topology_gap,
        reasons=reasons,
    )

    return DeviceStory(
        subject_id=evidence.device_ieee,
        status=status,
        priority=priority,
        headline_code=headline_code,
        reasons=reasons,
        evidence=evidence_refs,
        limitations=limitations,
        suggested_checks=checks,
        coverage=coverage,
        timeline=[],
    )


def _apply_reporting_silence_rules(
    *,
    evidence: DeviceStoryEvidence,
    now: datetime,
    reasons: list[DecisionReason],
    limitations: list[DecisionLimitation],
    checks: list[SuggestedCheck],
) -> ReportingSilence | None:
    """Add rhythm/silence reasons when silence exceeds observed cadence."""
    if evidence.reporting_rhythm is None:
        return None

    silence = build_reporting_silence(evidence.reporting_rhythm, now=now)
    if silence is None or silence.silence_state is not SilenceState.beyond_expected:
        return silence

    rhythm = evidence.reporting_rhythm
    _append_unique_reason(
        reasons,
        ReasonCode.observed_reporting_rhythm,
        interval_minutes_p25=rhythm.interval_minutes_p25,
        interval_minutes_median=rhythm.interval_minutes_median,
        interval_minutes_p75=rhythm.interval_minutes_p75,
    )
    _append_unique_reason(
        reasons,
        ReasonCode.reporting_silence_beyond_expected,
        silence_minutes=silence.silence_minutes,
        suspicion_threshold_minutes=silence.suspicion_threshold_minutes,
    )
    _append_unique_limitation(limitations, LimitationCode.extended_silence_not_failure)
    _append_unique_check(checks, CheckCode.confirm_powered)
    _append_unique_check(checks, CheckCode.confirm_reporting_in_z2m)
    return silence


def _resolve_story_outcome(
    *,
    evidence: DeviceStoryEvidence,
    topology_gap: bool,
    reasons: list[DecisionReason],
) -> tuple[DecisionStatus, DecisionPriority, str]:
    reason_codes = {reason.code for reason in reasons}

    if evidence.has_current_issue and topology_gap:
        return (
            DecisionStatus.review_first,
            DecisionPriority.high,
            HeadlineCode.current_issue_present,
        )

    if evidence.has_current_issue:
        return (
            DecisionStatus.worth_reviewing,
            DecisionPriority.high,
            HeadlineCode.current_issue_present,
        )

    if topology_gap:
        return (
            DecisionStatus.watch,
            DecisionPriority.low,
            HeadlineCode.topology_evidence_gap,
        )

    if ReasonCode.reporting_silence_beyond_expected in reason_codes:
        return (
            DecisionStatus.watch,
            DecisionPriority.low,
            HeadlineCode.extended_reporting_silence,
        )

    if ReasonCode.last_seen_stale in reason_codes:
        return DecisionStatus.watch, DecisionPriority.low, HeadlineCode.stale_last_seen

    if ReasonCode.battery_low in reason_codes:
        return DecisionStatus.watch, DecisionPriority.low, HeadlineCode.low_battery

    if ReasonCode.availability_tracking_off in reason_codes:
        return (
            DecisionStatus.improve_data_coverage,
            DecisionPriority.medium,
            HeadlineCode.availability_tracking_needed,
        )

    if any(code in _INFORMATIONAL_COVERAGE_REASONS for code in reason_codes):
        return (
            DecisionStatus.informational,
            DecisionPriority.low,
            HeadlineCode.data_coverage_gaps,
        )

    if reason_codes:
        return (
            DecisionStatus.informational,
            DecisionPriority.none,
            HeadlineCode.no_notable_signals,
        )

    return (
        DecisionStatus.no_notable_change,
        DecisionPriority.none,
        HeadlineCode.no_notable_signals,
    )


def device_story_for_device(
    repo: Repository,
    network_id: str,
    device_ieee: str,
    *,
    now: datetime | None = None,
) -> DeviceStory | None:
    """Build a device story from stored evidence. Returns None when unknown."""
    evidence = load_device_story_evidence(repo, network_id, device_ieee, now=now)
    if evidence is None:
        return None
    return build_device_story(evidence, now=now)


def device_story_report_payload(story: DeviceStory) -> dict[str, Any]:
    """Report-ready coded Device Story payload.

    Phase 5 reports should consume this shape (or the identical API JSON) and map
    codes to copy through the same presenter path as the UI ViewModel. No final
    prose belongs here.
    """
    return story.model_dump(mode="json")
