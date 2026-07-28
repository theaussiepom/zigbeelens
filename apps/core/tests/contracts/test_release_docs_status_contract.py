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
    "screenshots_s1_s9_stale",
    "screenshots_one_runtime_recapture",
    "phase_7d_blocked",
    "addon_deferred",
    "review_inventory_unresolved",
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
    for relative in {
        relative for _, relative, _ in VALIDATOR.RELEASE_BLOCKER_STATUS_GUARDS
    }:
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
        len(EXPECTED_GUARD_LABELS) + 4
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
