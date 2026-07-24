"""Fail-closed ownership for the canonical live enrichment E2E gate."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[4]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-check.yml"
RUNNER = ROOT / "scripts" / "test-enrichment-live-e2e.sh"
E2E_CONFIG = ROOT / "apps" / "ui" / "vitest.e2e.config.ts"
E2E_ROOT = ROOT / "apps" / "ui" / "src" / "e2e"
MINIMUM_REQUIREMENTS = (
    ROOT / "apps" / "ha_integration" / "requirements-test-minimum.txt"
)

JOB_NAME = "enrichment-live-e2e"
CANONICAL_COMMAND = "bash scripts/test-enrichment-live-e2e.sh"
SETUP_UV_REF = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
SETUP_UV_VERSION = "0.11.16"


def _job_body(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:[ \t]*\n"
        rf"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*\n|\Z)",
        workflow,
    )
    assert match is not None, f"missing workflow job: {job_name}"
    return match.group("body")


def _job_needs(workflow: str, job_name: str) -> set[str]:
    body = _job_body(workflow, job_name)
    match = re.search(
        r"(?ms)^    needs:\s*(?P<value>\[[^\]]*\]|[A-Za-z0-9_-]+)\s*$",
        body,
    )
    assert match is not None, f"{job_name} must declare explicit needs"
    return set(re.findall(r"[A-Za-z0-9_-]+", match.group("value")))


def _assert_live_job_contract(workflow: str) -> None:
    body = _job_body(workflow, JOB_NAME)
    assert re.search(r"(?m)^    runs-on:\s*ubuntu-latest\s*$", body)
    assert re.search(r"(?m)^    timeout-minutes:\s*30\s*$", body)
    assert body.count("uses: actions/checkout@v4") == 1
    assert body.count("uses: actions/setup-python@v5") == 1
    assert body.count('python-version: "3.12"') == 1
    assert body.count(f"uses: {SETUP_UV_REF}") == 1
    assert body.count(f'version: "{SETUP_UV_VERSION}"') == 1
    assert body.count("enable-cache: true") == 1
    assert body.count("uses: pnpm/action-setup@v4") == 1
    assert body.count("uses: actions/setup-node@v4") == 1
    assert body.count("node-version: 22") == 1
    assert body.count("cache: pnpm") == 1
    assert body.count("run: pnpm install --frozen-lockfile") == 1
    assert body.count("run: pnpm --filter @zigbeelens/shared build") == 1
    assert body.count(f"run: {CANONICAL_COMMAND}") == 1
    assert body.rstrip().endswith(f"run: {CANONICAL_COMMAND}")

    lowered = body.lower()
    for forbidden in (
        "continue-on-error:",
        "--passwithnotests",
        "if: false",
        "if: ${{ false }}",
        " mock",
        "--skip",
        "|| true",
        "exit 0",
        "run: true",
        "run: echo",
    ):
        assert forbidden not in lowered, f"live E2E job contains weakening: {forbidden}"
    assert re.search(r"(?m)^\s+if:\s*", body) is None


def _assert_e2e_corpus_contract(
    runner: str,
    config: str,
    sources: dict[str, str],
    minimum_requirements: str,
) -> None:
    assert re.search(r"(?m)^\s*--python 3\.12\s*$", runner)
    assert runner.count(
        'core_command=("$uv_command" run --project "$repo_root/apps/core" python)'
    ) == 1
    assert runner.count(
        'apps/ha_integration/requirements-test-minimum.txt'
    ) == 1
    assert runner.count('if [[ "$ha_lane" != "3.12|2025.1.0" ]]') == 1
    assert re.search(
        r"(?m)^homeassistant==2025\.1\.0\s*$",
        minimum_requirements,
    )
    assert "homeassistant==2026.7.3" not in minimum_requirements
    assert not re.search(r"(?m)^\s*(?:exit|return)\s+0\s*$", runner)
    lowered_runner = runner.lower()
    assert "passwithnotests" not in lowered_runner
    assert "zigbeelens_skip" not in lowered_runner

    execution_start = runner.index('(\n  cd "$repo_root/apps/ui"')
    execution = runner[execution_start:]
    assert execution.count("pnpm exec vitest run") == 1
    assert execution.count("--config vitest.e2e.config.ts") == 1
    assert "--passWithNoTests" not in execution
    assert "|| true" not in execution
    assert "exit 0" not in execution

    assert 'include: ["src/e2e/**/*.e2e.test.{ts,tsx}"]' in config
    assert "passWithNoTests: false" in config
    assert "passWithNoTests: true" not in config
    assert sources, "live E2E corpus must not be empty"
    combined = "\n".join(sources.values())
    assert re.search(r"\bit\s*\(", combined), "live E2E corpus must collect a test"
    assert re.search(r"\b(?:describe|it|test)\.(?:skip|todo)\b", combined) is None
    for forbidden in (
        "vi.mock(",
        "mockResolvedValue",
        "mockImplementation",
        "eventSourceTestState.emit",
    ):
        assert forbidden not in combined
    for required in (
        "DeviceDetailPage",
        "liveConnection",
        "NetworkEventSource",
        "HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT",
        "applyHomeAssistantState",
    ):
        assert required in combined


@pytest.mark.parametrize("workflow_path", (CI_WORKFLOW, RELEASE_WORKFLOW))
def test_monorepo_workflows_run_exact_live_enrichment_gate(
    workflow_path: Path,
) -> None:
    _assert_live_job_contract(workflow_path.read_text(encoding="utf-8"))


def test_downstream_jobs_require_live_enrichment_gate() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    assert _job_needs(ci, "packaging") == {
        "contracts",
        "backend",
        "ui",
        "ha-integration",
        "ha-integration-matrix",
        JOB_NAME,
    }

    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert _job_needs(release, "release-gate") == {
        "ha-integration-matrix",
        JOB_NAME,
    }
    for workflow, job_name in (
        (ci, "packaging"),
        (release, "release-gate"),
    ):
        body = _job_body(workflow, job_name)
        assert "continue-on-error:" not in body
        assert re.search(r"(?m)^\s+if:\s*", body) is None


def test_live_gate_runs_on_pr_main_and_version_tag_paths() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(
        r"(?ms)^on:\s*\n"
        r"\s+push:\s*\n"
        r"\s+branches:\s*\[[^\]]*\bmain\b[^\]]*\]\s*\n"
        r"\s+pull_request:\s*$",
        ci,
    )

    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(
        r'(?ms)^on:\s*\n\s+push:\s*\n\s+tags:\s*\n\s+-\s+"v\*"\s*$',
        release,
    )


def test_release_helper_orders_live_gate_before_hacs_packaging() -> None:
    helper = (ROOT / "scripts" / "run-release-checks.sh").read_text(
        encoding="utf-8"
    )
    structural = helper.index(
        "bash scripts/validate-ha-integration.sh --skip-matrix"
    )
    matrix = helper.index("bash scripts/test-ha-integration-matrix.sh")
    live = helper.index(CANONICAL_COMMAND)
    package = helper.index("bash scripts/package-hacs-repo.sh")
    assert structural < matrix < live < package


def test_live_e2e_runner_and_corpus_fail_closed() -> None:
    sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(E2E_ROOT.glob("**/*.e2e.test.*"))
    }
    _assert_e2e_corpus_contract(
        RUNNER.read_text(encoding="utf-8"),
        E2E_CONFIG.read_text(encoding="utf-8"),
        sources,
        MINIMUM_REQUIREMENTS.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    "old,new",
    (
        (f"run: {CANONICAL_COMMAND}", "run: echo mock live E2E"),
        ("timeout-minutes: 30", "timeout-minutes: 0"),
        ('python-version: "3.12"', 'python-version: "3.13"'),
        (f"uses: {SETUP_UV_REF}", "uses: astral-sh/setup-uv@main"),
        ('version: "0.11.16"', 'version: "latest"'),
        ("pnpm install --frozen-lockfile", "pnpm install"),
        (
            "- name: Run canonical live enrichment E2E",
            "- name: Run canonical live enrichment E2E\n        continue-on-error: true",
        ),
        (
            "- name: Run canonical live enrichment E2E",
            "- name: Run canonical live enrichment E2E\n        if: false",
        ),
        (
            f"run: {CANONICAL_COMMAND}",
            f"run: {CANONICAL_COMMAND} --skip",
        ),
    ),
)
def test_live_job_contract_rejects_adversarial_weakening(
    old: str,
    new: str,
) -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    body = _job_body(workflow, JOB_NAME)
    assert old in body
    weakened = workflow.replace(body, body.replace(old, new, 1), 1)
    with pytest.raises(AssertionError):
        _assert_live_job_contract(weakened)


def test_live_corpus_contract_rejects_zero_tests_skips_and_mocks() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    config = E2E_CONFIG.read_text(encoding="utf-8")
    minimum_requirements = MINIMUM_REQUIREMENTS.read_text(encoding="utf-8")
    source_path = next(iter(sorted(E2E_ROOT.glob("**/*.e2e.test.*"))))
    source = source_path.read_text(encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner,
            config,
            {},
            minimum_requirements,
        )
    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner + "\n--passWithNoTests\n",
            config,
            {str(source_path): source},
            minimum_requirements,
        )
    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner,
            config.replace("passWithNoTests: false", "passWithNoTests: true"),
            {str(source_path): source},
            minimum_requirements,
        )
    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner,
            config,
            {str(source_path): source.replace('it(\n    "', 'it.skip(\n    "', 1)},
            minimum_requirements,
        )
    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner,
            config,
            {str(source_path): source + "\nvi.mock('@/lib/api');\n"},
            minimum_requirements,
        )
    for weakened_runner in (
        "exit 0\n" + runner,
        runner.replace("--python 3.12", "--python 3.14", 1),
        runner.replace(
            "requirements-test-minimum.txt",
            "requirements-test-current.txt",
            1,
        ),
        runner.replace(
            '--project "$repo_root/apps/core"',
            "--no-project",
            1,
        ),
        runner.replace("3.12|2025.1.0", "3.14|2026.7.3", 1),
    ):
        with pytest.raises(AssertionError):
            _assert_e2e_corpus_contract(
                weakened_runner,
                config,
                {str(source_path): source},
                minimum_requirements,
            )
    with pytest.raises(AssertionError):
        _assert_e2e_corpus_contract(
            runner,
            config,
            {str(source_path): source},
            minimum_requirements.replace(
                "homeassistant==2025.1.0",
                "homeassistant==2026.7.3",
            ),
        )


def test_generated_satellite_workflows_remain_package_scoped() -> None:
    for relative in (
        "release/zigbeelens-hacs/.github/workflows/ci.yml",
        "release/zigbeelens-hacs/.github/workflows/release.yml",
    ):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert CANONICAL_COMMAND not in workflow
        assert JOB_NAME not in workflow
