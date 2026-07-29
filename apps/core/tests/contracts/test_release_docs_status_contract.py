"""Fail-closed ownership for the pre-Phase-7D release status."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import re
import shutil
import sys
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-docs.py"
SPEC = importlib.util.spec_from_file_location(
    "zigbeelens_validate_docs_release_status_contract",
    VALIDATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

EXPECTED_GUARD_LABELS = {
    "hacs_main_commit",
    "hacs_tree",
    "hacs_source_commit",
    "hacs_no_tag_or_release",
    "hacs_stale_after_correction",
    "public_installation_gated",
    "rejected_digest_invalid",
    "package_version_oci_metadata",
    "full_revision_oci_metadata",
    "canonical_source_oci_metadata",
    "schema_target_15",
    "migration_014_unchanged",
    "snapshot_parsed_json_null",
    "snapshot_typed_counts_preserved",
    "screenshots_s1_s9_current",
    "screenshots_one_runtime_source",
    "phase_7d_blocked",
    "addon_deferred",
    "phase_7c2_complete",
    "phase_7c2_pr_108_merged",
    "phase_7c2_capture_source_exact",
    "review_inventory_resolved",
    "pr_107_review_closures",
    "pr_108_s4_review_closed",
    "pr_106_p1",
    "pr_106_p2",
    "pr_100_mixed_case_ieee",
    "pr_97_coordinator_action",
    "delayed_approved_host_bypass",
    "changelog_exact_hacs_state",
    "changelog_hacs_stale_and_gated",
}


@contextmanager
def _validator_root(root: Path) -> Iterator[None]:
    original = VALIDATOR.ROOT
    VALIDATOR.ROOT = root
    try:
        yield
    finally:
        VALIDATOR.ROOT = original


def _copy_guard_documents(root: Path) -> None:
    guard_documents = {
        relative for _, relative, _ in VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS
    }
    scope_documents = {
        relative
        for _, relative, _, _ in VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES
    }
    for relative in guard_documents | scope_documents:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)


def test_release_status_guard_inventory_is_exact() -> None:
    guards = VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS
    labels = [label for label, _, _ in guards]

    assert len(labels) == len(set(labels))
    assert set(labels) == EXPECTED_GUARD_LABELS


def test_current_release_status_passes_exact_guards() -> None:
    assert VALIDATOR.validate_release_blocker_status_truth() == (
        len(EXPECTED_GUARD_LABELS)
        + len(VALIDATOR.STALE_TOPOLOGY_PARSED_JSON_CLAIMS)
        + len(VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES)
        * len(VALIDATOR.STALE_CURRENT_STATUS_PATTERNS)
    )


@pytest.mark.parametrize(
    ("label", "relative", "fragment"),
    VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS,
    ids=[guard[0] for guard in VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS],
)
def test_each_release_status_guard_fails_closed(
    tmp_path: Path,
    label: str,
    relative: str,
    fragment: str,
) -> None:
    _copy_guard_documents(tmp_path)
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\s+".join(re.escape(part) for part in fragment.split()),
        flags=re.IGNORECASE,
    )
    mutated, replacements = pattern.subn("[removed release status guard]", text, count=1)
    assert replacements == 1, label
    path.write_text(mutated, encoding="utf-8")

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=label,
    ):
        VALIDATOR.validate_release_blocker_status_truth()


@pytest.mark.parametrize(
    "stale_claim",
    (
        "Migration reduces legacy `parsed_json` to normalized counts.",
        "Snapshot `parsed_json` is limited to normalized counts.",
        "Persistence uses bounded count-only `parsed_json`.",
        "Migration rebuilds non-null snapshot `parsed_json`.",
    ),
)
def test_stale_parsed_json_claims_fail_closed(
    tmp_path: Path,
    stale_claim: str,
) -> None:
    _copy_guard_documents(tmp_path)
    safety = tmp_path / "docs/safety-audit.md"
    safety.write_text(
        safety.read_text(encoding="utf-8") + "\n" + stale_claim + "\n",
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match="stale topology parsed_json",
    ):
        VALIDATOR.validate_release_blocker_status_truth()


@pytest.mark.parametrize(
    "stale_claim",
    (
        "This status closure still requires review.",
        "This status closure is pending merge.",
        "Phase 7D waits for this status-closure PR to merge.",
        "The focused screenshot PR still requires merge.",
        "The evidence is ready for independent review.",
        "This remains a local screenshot candidate until merge.",
        "These findings remain unresolved until a future fixing PR is merged.",
        "The focused PR still needs independent review, green remote CI, and merge.",
        "This is a local 7C2 candidate pending PR review, CI, and merge.",
        "It is final-candidate review evidence.",
        "Phase 7C2 is awaiting remote CI and PR merge.",
        "Phase 7C2 is incomplete.",
        "Phase 7C2 still requires recapture of all S1–S9.",
        "The review inventory remains open until a future fixing PR is merged.",
        "Keep the focused screenshot PR gated on independent review, green "
        "remote CI, and merge.",
        "Phase 7C2 is still requiring recapture of all S1–S9.",
        "PR #106 discussions, PR #100 discussion, PR #97 discussion, and the "
        "delayed approved-host bypass review remain unresolved until a future "
        "fixing PR is merged.",
    ),
)
def test_stale_current_phase_7c2_status_fails_closed(
    tmp_path: Path,
    stale_claim: str,
) -> None:
    _copy_guard_documents(tmp_path)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "## Using the UI"
    assert marker in text
    readme.write_text(
        text.replace(marker, f"{stale_claim}\n\n{marker}", 1),
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match="stale current Phase 7C2 status",
    ):
        VALIDATOR.validate_release_blocker_status_truth()


@pytest.mark.parametrize(
    ("scope", "relative", "start_marker", "end_marker"),
    VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES,
    ids=[scope[0] for scope in VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES],
)
def test_each_current_status_scope_rejects_stale_status(
    tmp_path: Path,
    scope: str,
    relative: str,
    start_marker: str,
    end_marker: str,
) -> None:
    _copy_guard_documents(tmp_path)
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    assert start >= 0, scope
    assert end >= 0, scope
    path.write_text(
        text[:end]
        + "The evidence is ready for independent review.\n\n"
        + text[end:],
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=rf"{re.escape(scope)}: ready_for_independent_review",
    ):
        VALIDATOR.validate_release_blocker_status_truth()


@pytest.mark.parametrize(
    ("scope", "relative", "start_marker", "end_marker"),
    VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES,
    ids=[scope[0] for scope in VALIDATOR.CURRENT_RELEASE_STATUS_SCOPES],
)
def test_each_current_status_scope_rejects_self_expiring_status_closure(
    tmp_path: Path,
    scope: str,
    relative: str,
    start_marker: str,
    end_marker: str,
) -> None:
    _copy_guard_documents(tmp_path)
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    assert start >= 0, scope
    assert end >= 0, scope
    path.write_text(
        text[:end]
        + "Phase 7D waits for this status-closure PR to merge.\n\n"
        + text[end:],
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=rf"{re.escape(scope)}: status_closure_pending_merge",
    ):
        VALIDATOR.validate_release_blocker_status_truth()


def test_old_release_checklist_status_closure_wording_fails_closed(
    tmp_path: Path,
) -> None:
    _copy_guard_documents(tmp_path)
    checklist = tmp_path / "RELEASE_CHECKLIST.md"
    text = checklist.read_text(encoding="utf-8")
    durable = (
        "Phase 7D remains blocked until a final docs-bearing HACS tree is "
        "generated from\nmerged main, the exact tree is synchronized under "
        "separate explicit\nauthorization, the generated exact HA and official "
        "HACS/hassfest checks pass\nremotely, and the final monorepo/HACS/GHCR "
        "pairing is frozen."
    )
    assert durable in text
    checklist.write_text(
        text.replace(
            durable,
            "Phase 7D remains blocked until this status closure is "
            "independently reviewed\nand merged.",
            1,
        ),
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=(
            "release_checklist_phase_status: "
            "status_closure_pending_merge"
        ),
    ):
        VALIDATOR.validate_release_blocker_status_truth()


def test_historical_status_closure_review_prose_remains_allowed(
    tmp_path: Path,
) -> None:
    _copy_guard_documents(tmp_path)
    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    archived_claim = "Phase 7D waits for this status-closure PR to merge."
    status_pattern = next(
        pattern
        for label, pattern in VALIDATOR.STALE_CURRENT_STATUS_PATTERNS
        if label == "status_closure_pending_merge"
    )
    assert re.search(status_pattern, archived_claim, flags=re.IGNORECASE | re.DOTALL)
    readme.write_text(
        text
        + "\n## Archived execution record\n\n"
        + archived_claim
        + "\n",
        encoding="utf-8",
    )

    with _validator_root(tmp_path):
        assert VALIDATOR.validate_release_blocker_status_truth() > 0


def test_pr_108_merged_statement_is_required(tmp_path: Path) -> None:
    _copy_guard_documents(tmp_path)
    label, relative, fragment = next(
        guard
        for guard in VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS
        if guard[0] == "phase_7c2_pr_108_merged"
    )
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\s+".join(re.escape(part) for part in fragment.split()),
        flags=re.IGNORECASE,
    )
    mutated, replacements = pattern.subn(
        "The focused screenshot PR still requires merge.",
        text,
        count=1,
    )
    assert replacements == 1
    path.write_text(mutated, encoding="utf-8")

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=label,
    ):
        VALIDATOR.validate_release_blocker_status_truth()


def test_resolved_review_inventory_cannot_regress(tmp_path: Path) -> None:
    _copy_guard_documents(tmp_path)
    checklist = tmp_path / "RELEASE_CHECKLIST.md"
    text = checklist.read_text(encoding="utf-8")
    resolved = "The review inventory is resolved."
    assert resolved in text
    checklist.write_text(
        text.replace(
            resolved,
            "These findings remain unresolved until a future fixing PR is merged.",
            1,
        ),
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match="review_inventory_resolved",
    ):
        VALIDATOR.validate_release_blocker_status_truth()


@pytest.mark.parametrize(
    ("label", "owned_text", "replacement"),
    (
        (
            "pr_106_p1",
            "discussion_r3669046766",
            "discussion_r0000000000",
        ),
        (
            "delayed_approved_host_bypass",
            "issuecomment-5109485498",
            "issuecomment-0000000000",
        ),
        (
            "pr_108_s4_review_closed",
            "discussion_r3672142130`; resolved",
            "discussion_r3672142130`; unresolved",
        ),
    ),
)
def test_exact_review_reply_and_resolution_evidence_is_required(
    tmp_path: Path,
    label: str,
    owned_text: str,
    replacement: str,
) -> None:
    _copy_guard_documents(tmp_path)
    checklist = tmp_path / "RELEASE_CHECKLIST.md"
    text = checklist.read_text(encoding="utf-8")
    assert owned_text in text
    checklist.write_text(
        text.replace(owned_text, replacement, 1),
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match=label,
    ):
        VALIDATOR.validate_release_blocker_status_truth()


def test_historical_text_outside_current_scopes_is_not_globally_banned(
    tmp_path: Path,
) -> None:
    _copy_guard_documents(tmp_path)
    history = tmp_path / "docs/decision-engine-cursor-guardrails.md"
    history.write_text(
        history.read_text(encoding="utf-8")
        + "\n## Archived execution example\n\n"
        + "The evidence is ready for independent review.\n",
        encoding="utf-8",
    )

    with _validator_root(tmp_path):
        VALIDATOR.validate_release_blocker_status_truth()


def test_duplicate_scope_marker_fails_closed(tmp_path: Path) -> None:
    _copy_guard_documents(tmp_path)
    lens = tmp_path / "docs/lens-alignment-status.md"
    text = lens.read_text(encoding="utf-8")
    start_marker = "## Release-work boundary"
    insertion = text.index(start_marker) + len(start_marker)
    lens.write_text(
        text[:insertion]
        + "\n\nSee:\n\nThe evidence is ready for independent review.\n"
        + text[insertion:],
        encoding="utf-8",
    )

    with _validator_root(tmp_path), pytest.raises(
        VALIDATOR.DocumentationError,
        match="scope marker count must be exactly one",
    ):
        VALIDATOR.validate_release_blocker_status_truth()
