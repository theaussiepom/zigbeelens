"""Fail-closed workflow ownership for the canonical Core smoke gate."""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[4]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-check.yml"
CONTRACT_RUNNER = ROOT / "scripts" / "validate-contracts.sh"
SMOKE_CONTRACT = ROOT / "apps" / "core" / "tests" / "contracts" / "test_smoke_core_script.py"

SETUP_UV_REF = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
SETUP_UV_VERSION = "0.11.16"
SETUP_STEP_NAME = "Set up pinned uv for Core smoke"
CANONICAL_SMOKE_COMMAND = "bash scripts/smoke-core.sh"
REAL_UV_TEST = "test_uv_owned_invocation_passes_without_pip_repair"

OWNER_JOBS = (
    (
        CI_WORKFLOW,
        "backend",
        ("run: pytest apps/core/tests -q",),
    ),
    (
        CI_WORKFLOW,
        "contracts",
        ("run: bash scripts/validate-contracts.sh",),
    ),
    (
        CI_WORKFLOW,
        "packaging",
        (f"run: {CANONICAL_SMOKE_COMMAND}",),
    ),
    (
        RELEASE_WORKFLOW,
        "release-gate",
        (
            "run: bash scripts/validate-contracts.sh",
            "run: pytest apps/core/tests -q",
            f"run: {CANONICAL_SMOKE_COMMAND}",
        ),
    ),
)

DIRECT_SMOKE_JOBS = (
    (CI_WORKFLOW, "packaging", "Core smoke test"),
    (RELEASE_WORKFLOW, "release-gate", "Core smoke"),
)


def _job_body(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:[ \t]*\n"
        rf"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*\n|\Z)",
        workflow,
    )
    assert match is not None, f"missing workflow job: {job_name}"
    return match.group("body")


def _named_step_body(job_body: str, step_name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name:\s*{re.escape(step_name)}\s*\n"
        rf".*?(?=^      - (?:name:|uses:)|\Z)",
        job_body,
    )
    assert match is not None, f"missing workflow step: {step_name}"
    return match.group(0)


def _replace_job_body(workflow: str, job_name: str, replacement: str) -> str:
    body = _job_body(workflow, job_name)
    assert body in workflow
    return workflow.replace(body, replacement, 1)


def _assert_required_job_owns_pinned_uv(
    workflow: str,
    job_name: str,
    ownership_commands: tuple[str, ...],
) -> None:
    body = _job_body(workflow, job_name)
    setup = _named_step_body(body, SETUP_STEP_NAME)

    assert body.count(f"uses: {SETUP_UV_REF}") == 1
    assert body.count(f'version: "{SETUP_UV_VERSION}"') == 1
    assert setup.count(f"uses: {SETUP_UV_REF}") == 1
    assert setup.count(f'version: "{SETUP_UV_VERSION}"') == 1
    assert setup.count("enable-cache: true") == 1
    assert "continue-on-error:" not in setup
    assert re.search(r"(?m)^\s+if:\s*", setup) is None

    assert "continue-on-error:" not in body
    assert re.search(r"(?m)^    if:\s*", body) is None
    setup_position = body.index(f"- name: {SETUP_STEP_NAME}")
    for command in ownership_commands:
        assert body.count(command) == 1
        assert setup_position < body.index(command)


def _assert_direct_smoke_is_required(
    workflow: str,
    job_name: str,
    step_name: str,
) -> None:
    body = _job_body(workflow, job_name)
    step = _named_step_body(body, step_name)
    exact_command = f"run: {CANONICAL_SMOKE_COMMAND}"

    assert step.count(exact_command) == 1
    assert step.rstrip().endswith(exact_command)
    assert "continue-on-error:" not in step
    assert re.search(r"(?m)^\s+if:\s*", step) is None
    assert "ZIGBEELENS_CORE_PYTHON" not in body

    lowered = step.lower()
    for forbidden in (
        "|| true",
        "exit 0",
        "run: true",
        "run: echo",
    ):
        assert forbidden not in lowered, f"Core smoke step contains weakening: {forbidden}"


def _assert_smoke_contract_collection(runner: str, source: str) -> None:
    exact_collection = '"${core_python}" -m pytest -q tests/contracts'
    assert runner.count(exact_collection) == 1

    lowered_runner = runner.lower()
    for forbidden in (
        "--ignore",
        "--deselect",
        "--collect-only",
        "--continue-on-collection-errors",
        "--passwithnotests",
        " -k ",
        "|| true",
    ):
        assert forbidden not in lowered_runner, (
            f"Core contract runner contains weakening: {forbidden}"
        )

    tree = ast.parse(source)
    test_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    assert test_names, "Core smoke contract corpus must not be empty"
    assert REAL_UV_TEST in test_names

    lowered_source = source.lower()
    assert "pytestmark = pytest.mark.skip" not in lowered_source
    assert "@pytest.mark.skip" not in lowered_source
    assert "pytest.skip(" not in lowered_source


@pytest.mark.parametrize(
    ("workflow_path", "job_name", "ownership_commands"),
    OWNER_JOBS,
)
def test_required_core_smoke_jobs_own_pinned_uv(
    workflow_path: Path,
    job_name: str,
    ownership_commands: tuple[str, ...],
) -> None:
    _assert_required_job_owns_pinned_uv(
        workflow_path.read_text(encoding="utf-8"),
        job_name,
        ownership_commands,
    )


@pytest.mark.parametrize(
    ("workflow_path", "job_name", "step_name"),
    DIRECT_SMOKE_JOBS,
)
def test_required_workflows_run_exact_core_smoke(
    workflow_path: Path,
    job_name: str,
    step_name: str,
) -> None:
    _assert_direct_smoke_is_required(
        workflow_path.read_text(encoding="utf-8"),
        job_name,
        step_name,
    )


def test_contract_runner_collects_nonempty_real_uv_smoke_corpus() -> None:
    _assert_smoke_contract_collection(
        CONTRACT_RUNNER.read_text(encoding="utf-8"),
        SMOKE_CONTRACT.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    ("workflow_path", "job_name", "ownership_commands"),
    OWNER_JOBS,
)
@pytest.mark.parametrize(
    "weakening",
    ("missing-setup", "moving-action", "moving-version"),
)
def test_core_smoke_jobs_reject_missing_or_moving_uv_setup(
    workflow_path: Path,
    job_name: str,
    ownership_commands: tuple[str, ...],
    weakening: str,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    body = _job_body(workflow, job_name)
    setup = _named_step_body(body, SETUP_STEP_NAME)

    if weakening == "missing-setup":
        weakened_body = body.replace(setup, "", 1)
    elif weakening == "moving-action":
        weakened_body = body.replace(
            f"uses: {SETUP_UV_REF}",
            "uses: astral-sh/setup-uv@main",
            1,
        )
    else:
        weakened_body = body.replace(
            f'version: "{SETUP_UV_VERSION}"',
            'version: "latest"',
            1,
        )
    assert weakened_body != body

    with pytest.raises(AssertionError):
        _assert_required_job_owns_pinned_uv(
            _replace_job_body(workflow, job_name, weakened_body),
            job_name,
            ownership_commands,
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_name", "step_name"),
    DIRECT_SMOKE_JOBS,
)
@pytest.mark.parametrize(
    "weakening",
    ("no-op", "skipped", "soft-failed", "shell-soft-failed"),
)
def test_core_smoke_jobs_reject_noop_skipped_or_soft_failed_smoke(
    workflow_path: Path,
    job_name: str,
    step_name: str,
    weakening: str,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    body = _job_body(workflow, job_name)
    step = _named_step_body(body, step_name)
    command_line = f"        run: {CANONICAL_SMOKE_COMMAND}"
    assert command_line in step

    if weakening == "no-op":
        weakened_step = step.replace(command_line, "        run: true", 1)
    elif weakening == "skipped":
        weakened_step = step.replace(
            command_line,
            f"        if: false\n{command_line}",
            1,
        )
    elif weakening == "soft-failed":
        weakened_step = step.replace(
            command_line,
            f"        continue-on-error: true\n{command_line}",
            1,
        )
    else:
        weakened_step = step.replace(command_line, f"{command_line} || true", 1)
    assert weakened_step != step

    weakened_body = body.replace(step, weakened_step, 1)
    with pytest.raises(AssertionError):
        _assert_direct_smoke_is_required(
            _replace_job_body(workflow, job_name, weakened_body),
            job_name,
            step_name,
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_name", "ownership_commands", "old", "new"),
    (
        (
            CI_WORKFLOW,
            "backend",
            ("run: pytest apps/core/tests -q",),
            "run: pytest apps/core/tests -q",
            "run: pytest apps/core/tests/test_logging_config.py -q",
        ),
        (
            CI_WORKFLOW,
            "contracts",
            ("run: bash scripts/validate-contracts.sh",),
            "run: bash scripts/validate-contracts.sh",
            (
                "run: pytest "
                "apps/core/tests/contracts/test_live_enrichment_workflow_gate.py -q"
            ),
        ),
        (
            RELEASE_WORKFLOW,
            "release-gate",
            (
                "run: bash scripts/validate-contracts.sh",
                "run: pytest apps/core/tests -q",
                f"run: {CANONICAL_SMOKE_COMMAND}",
            ),
            "run: bash scripts/validate-contracts.sh",
            (
                "run: pytest "
                "apps/core/tests/contracts/test_live_enrichment_workflow_gate.py -q"
            ),
        ),
        (
            RELEASE_WORKFLOW,
            "release-gate",
            (
                "run: bash scripts/validate-contracts.sh",
                "run: pytest apps/core/tests -q",
                f"run: {CANONICAL_SMOKE_COMMAND}",
            ),
            "run: pytest apps/core/tests -q",
            "run: pytest apps/core/tests/test_logging_config.py -q",
        ),
    ),
)
def test_core_smoke_jobs_reject_excluding_smoke_contracts(
    workflow_path: Path,
    job_name: str,
    ownership_commands: tuple[str, ...],
    old: str,
    new: str,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    body = _job_body(workflow, job_name)
    weakened_body = body.replace(old, new, 1)
    assert weakened_body != body

    with pytest.raises(AssertionError):
        _assert_required_job_owns_pinned_uv(
            _replace_job_body(workflow, job_name, weakened_body),
            job_name,
            ownership_commands,
        )


def test_smoke_contract_guard_rejects_zero_excluded_or_skipped_corpus() -> None:
    runner = CONTRACT_RUNNER.read_text(encoding="utf-8")
    source = SMOKE_CONTRACT.read_text(encoding="utf-8")
    no_tests = re.sub(r"(?m)^def test_", "def disabled_", source)
    excluded = runner.replace(
        "pytest -q tests/contracts",
        (
            "pytest -q tests/contracts "
            "--ignore=tests/contracts/test_smoke_core_script.py"
        ),
        1,
    )
    skipped = "pytestmark = pytest.mark.skip(reason='disabled')\n" + source

    assert no_tests != source
    assert excluded != runner
    for weakened_runner, weakened_source in (
        (runner, ""),
        (runner, no_tests),
        (excluded, source),
        (runner, skipped),
    ):
        with pytest.raises(AssertionError):
            _assert_smoke_contract_collection(weakened_runner, weakened_source)
