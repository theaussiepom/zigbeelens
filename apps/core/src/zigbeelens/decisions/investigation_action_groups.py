"""Action-group mapping for problem-first investigation cards."""

from __future__ import annotations

from typing import Any

from zigbeelens.decisions.types import InvestigationActionGroup

PRIORITY_CONTEXT_ONLY = "Lower priority"


def action_group_for_investigation_card(card: dict[str, Any]) -> InvestigationActionGroup:
    """Map an existing investigation card type to an action-led group.

    Cards keep their evidence-specific title and summary; the action group
    tells the user what kind of check to start with. Lower-priority passive
    groups surface as watch-only because the evidence is weaker.
    """
    card_type = card.get("type")
    priority = card.get("priority")

    if card_type == "diagnostics_limited_group":
        return InvestigationActionGroup.improve_data_coverage
    if card_type == "router_neighbourhood_review":
        return InvestigationActionGroup.review_observed_router_area
    if card_type == "recent_missing_cluster":
        return InvestigationActionGroup.check_power_reporting
    if card_type == "shared_availability_event":
        return InvestigationActionGroup.investigate_shared_event
    if card_type == "issue_cluster":
        return InvestigationActionGroup.investigate_shared_event
    if card_type == "passive_instability_group":
        if priority == PRIORITY_CONTEXT_ONLY:
            return InvestigationActionGroup.watch_only
        return InvestigationActionGroup.investigate_shared_event
    return InvestigationActionGroup.watch_only


def assign_investigation_action_groups(cards: list[dict[str, Any]]) -> None:
    """Attach ``action_group`` to each card in place."""
    for card in cards:
        card["action_group"] = action_group_for_investigation_card(card).value
