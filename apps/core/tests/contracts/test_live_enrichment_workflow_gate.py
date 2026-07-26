"""Fail-closed ownership for the canonical live enrichment E2E gate."""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[4]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-check.yml"
DOCKER_WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
RUNNER = ROOT / "scripts" / "test-enrichment-live-e2e.sh"
HA_CONTROL_SERVER = (
    ROOT / "tests" / "e2e" / "enrichment_live" / "ha_control_server.py"
)
E2E_CONFIG = ROOT / "apps" / "ui" / "vitest.e2e.config.ts"
E2E_ROOT = ROOT / "apps" / "ui" / "src" / "e2e"
MINIMUM_REQUIREMENTS = (
    ROOT / "apps" / "ha_integration" / "requirements-test-minimum.txt"
)

JOB_NAME = "enrichment-live-e2e"
CANONICAL_COMMAND = "bash scripts/test-enrichment-live-e2e.sh"
SETUP_UV_REF = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
SETUP_UV_VERSION = "0.11.16"
CORE_SYNC_COMMAND = "uv sync --project apps/core --python 3.12 --extra dev"
DOCKER_LIVE_STEP_NAME = (
    "Run canonical live enrichment E2E before tag publication"
)
DOCKER_LIVE_STEP_ID = "tag-live-e2e"
TAG_CONDITION = "startsWith(github.ref, 'refs/tags/v')"
DOCKER_PUSH_EXPRESSION = (
    "${{ github.event_name != 'pull_request' && "
    "(github.ref == 'refs/heads/main' || "
    "(startsWith(github.ref, 'refs/tags/v') && "
    "steps.tag-live-e2e.outcome == 'success')) && "
    "github.repository == format('{0}/zigbeelens', github.repository_owner) }}"
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
    assert body.count(f"run: {CORE_SYNC_COMMAND}") == 1
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


def _assert_docker_tag_publish_contract(workflow: str) -> None:
    push_trigger = re.search(
        r"(?ms)^  push:\s*\n(?P<body>.*?)(?=^\S)",
        workflow,
    )
    assert push_trigger is not None, "Docker workflow must keep its push trigger"
    trigger_body = push_trigger.group("body")
    assert re.search(
        r"(?m)^    branches:\s*\[main,\s*master\]\s*$",
        trigger_body,
    )
    assert re.search(
        r'(?m)^    tags:\s*\n\s+-\s+"v\*"\s*$',
        trigger_body,
    )
    assert re.search(
        r"(?ms)^  pull_request:\s*\n"
        r"\s+branches:\s*\[main,\s*master\]\s*$",
        workflow,
    )

    body = _job_body(workflow, "build")
    assert body.count("uses: actions/setup-python@v5") == 1
    assert body.count('python-version: "3.12"') == 1
    assert body.count(f"uses: {SETUP_UV_REF}") == 1
    assert body.count(f'version: "{SETUP_UV_VERSION}"') == 1
    assert body.count("enable-cache: true") == 1
    assert body.count(f"run: {CORE_SYNC_COMMAND}") == 1
    assert body.count("uses: pnpm/action-setup@v4") == 1
    assert body.count("uses: actions/setup-node@v4") == 1
    assert body.count("node-version: 22") == 1
    assert body.count("cache: pnpm") == 1
    assert body.count("run: pnpm install --frozen-lockfile") == 1
    assert body.count("run: pnpm --filter @zigbeelens/shared build") == 1
    assert body.count(f"run: {CANONICAL_COMMAND}") == 1

    tag_steps = (
        ("Set up uv for tag live E2E", f"uses: {SETUP_UV_REF}"),
        (
            "Install Core dependencies for tag live E2E",
            f"run: {CORE_SYNC_COMMAND}",
        ),
        ("Set up pnpm for tag live E2E", "uses: pnpm/action-setup@v4"),
        ("Set up Node for tag live E2E", "uses: actions/setup-node@v4"),
        (
            "Install JavaScript dependencies for tag live E2E",
            "run: pnpm install --frozen-lockfile",
        ),
        (
            "Build shared types for tag live E2E",
            "run: pnpm --filter @zigbeelens/shared build",
        ),
        (DOCKER_LIVE_STEP_NAME, f"run: {CANONICAL_COMMAND}"),
    )
    for step_name, required in tag_steps:
        step = _named_step_body(body, step_name)
        assert step.count(f"if: {TAG_CONDITION}") == 1
        assert required in step

    live_step = _named_step_body(body, DOCKER_LIVE_STEP_NAME)
    assert live_step.count(f"id: {DOCKER_LIVE_STEP_ID}") == 1
    assert live_step.rstrip().endswith(f"run: {CANONICAL_COMMAND}")

    ordered_fragments = (
        "uses: actions/setup-python@v5",
        'python-version: "3.12"',
        f"uses: {SETUP_UV_REF}",
        f"run: {CORE_SYNC_COMMAND}",
        "uses: pnpm/action-setup@v4",
        "uses: actions/setup-node@v4",
        "node-version: 22",
        "run: pnpm install --frozen-lockfile",
        "run: pnpm --filter @zigbeelens/shared build",
        f"run: {CANONICAL_COMMAND}",
        "- name: Log in to GHCR",
        "- name: Build and push",
    )
    positions = [body.index(fragment) for fragment in ordered_fragments]
    assert positions == sorted(positions)

    tag_prerequisites = body[
        body.index("- name: Set up uv for tag live E2E"):
        body.index("- name: Log in to GHCR")
    ]
    lowered = tag_prerequisites.lower()
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
        assert forbidden not in lowered, (
            f"Docker tag live E2E contains weakening: {forbidden}"
        )
    assert "continue-on-error:" not in body
    assert "|| true" not in body

    build_step = _named_step_body(body, "Build and push")
    push = re.search(
        r"(?m)^\s+push:\s*(?P<expression>\$\{\{.*\}\})\s*$",
        build_step,
    )
    assert push is not None, "Docker build-push action must declare push ownership"
    assert push.group("expression") == DOCKER_PUSH_EXPRESSION


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


def _call_attribute(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _function(tree: ast.AST, name: str) -> ast.AsyncFunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"expected exactly one async {name} function"
    return matches[0]


def _class(tree: ast.AST, name: str) -> ast.ClassDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    assert len(matches) == 1, f"expected exactly one {name} class"
    return matches[0]


def _assert_live_ha_ownership_contract(runner: str, control: str) -> None:
    package_command = 'bash "$repo_root/scripts/package-hacs-repo.sh"'
    validate_command = (
        'bash "$hacs_stage/scripts/validate-hacs-repo.sh"'
    )
    stage_assignment = (
        'hacs_stage="$repo_root/dist/zigbeelens-hacs"'
    )
    staged_copy = (
        'cp -R "$hacs_stage/custom_components" "$ha_config_dir/"'
    )
    disposable_assignment = (
        'ha_components_dir="$ha_config_dir/custom_components"'
    )
    launch = '"$repo_root/tests/e2e/enrichment_live/ha_control_server.py"'

    assert runner.count(package_command) == 1
    assert runner.count(validate_command) == 1
    assert runner.count(stage_assignment) == 1
    assert runner.count(staged_copy) == 1
    assert runner.count(disposable_assignment) == 1
    assert runner.count("SOURCE_COMMIT") >= 1
    assert re.search(r"\bgit\b[^\n]*\brev-parse\b[^\n]*\bHEAD\b", runner)
    assert (
        'if [[ "$staged_source_commit" != "$source_commit" ]]'
        in runner
    )
    assert (
        'if [[ "$ha_provenance" != "$source_commit|0.1.14" ]]'
        in runner
    )
    assert package_command in runner[: runner.index(validate_command)]
    assert validate_command in runner[: runner.index(launch)]
    assert stage_assignment in runner[: runner.index(package_command)]
    assert staged_copy in runner[: runner.index(launch)]
    assert disposable_assignment in runner[: runner.index(staged_copy)]
    for argument in (
        "--components-dir",
        "--source-commit",
        "--provenance-file",
    ):
        assert runner.count(argument) == 1
    assert "PYTHONASYNCIODEBUG=1" in runner
    assert "grep -Eiq" in runner
    for marker in (
        "from a thread other than the event loop",
        "non-thread-safe operation invoked on an event loop",
        "task exception was never retrieved",
        "exception in callback",
    ):
        assert marker in runner.lower()

    tree = ast.parse(control)
    manager_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_attribute(node) == "HomeAssistantEnrichmentManager"
    ]
    assert len(manager_calls) == 1
    manager_keywords = {
        keyword.arg
        for keyword in manager_calls[0].keywords
        if keyword.arg is not None
    }
    assert {"debounce_seconds", "reconciliation_interval"} <= manager_keywords
    assert {
        "later_scheduler",
        "interval_scheduler",
        "task_factory",
    }.isdisjoint(manager_keywords)

    calls = [
        node for node in ast.walk(tree) if isinstance(node, ast.Call)
    ]
    call_attributes = {
        attribute
        for node in calls
        if (attribute := _call_attribute(node)) is not None
    }
    assert "async_update_device" in call_attributes
    assert "async_reconcile" not in call_attributes
    assert "drain_one" not in call_attributes
    assert "async_wait_for_idle" not in call_attributes
    assert "sleep" not in call_attributes

    apply_state = _function(tree, "apply_state")
    apply_awaits = [
        node for node in ast.walk(apply_state) if isinstance(node, ast.Await)
    ]
    assert any(
        "publish" in ast.unparse(node.value).lower()
        for node in apply_awaits
    ), "apply_state must wait on publish observation"
    observed_client = _class(tree, "_ObservedApiClient")
    assert any(
        isinstance(node, ast.Call)
        and _call_attribute(node) in {"Condition", "Event"}
        for node in ast.walk(observed_client)
    ), "publish observation must be event-driven"

    assert any(
        _call_attribute(node) == "set_debug"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value is True
        for node in calls
    ), "the disposable HA loop must enable asyncio debug"
    assert "THREAD_SAFETY_MARKERS" in control
    assert "_RuntimeErrorCapture" in control
    assert "from a thread other than the event loop" in control.lower()
    assert "non-thread-safe operation" in control.lower()
    assert sum(
        _call_attribute(node) == "set_exception_handler"
        for node in calls
    ) == 2
    assert "addHandler" in call_attributes
    assert sum(
        _call_attribute(node) == "raise_if_any"
        for node in calls
    ) >= 2

    assert "apps/ha_integration/custom_components" not in control
    for argument in (
        "--components-dir",
        "--source-commit",
        "--provenance-file",
    ):
        assert argument in control
    assert "SOURCE_COMMIT" in control
    assert "inspect.getfile" in control
    assert "0.1.14" in control


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


def test_docker_tag_publication_requires_exact_live_gate() -> None:
    _assert_docker_tag_publish_contract(
        DOCKER_WORKFLOW.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "run: echo mock live E2E",
        "run: true",
        f"run: {CANONICAL_COMMAND} --skip",
    ),
)
def test_docker_tag_contract_rejects_mocked_or_skipped_e2e(
    replacement: str,
) -> None:
    workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
    exact = f"run: {CANONICAL_COMMAND}"
    assert exact in workflow
    with pytest.raises(AssertionError):
        _assert_docker_tag_publish_contract(
            workflow.replace(exact, replacement, 1)
        )


def test_docker_tag_contract_rejects_deleted_e2e() -> None:
    workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
    body = _job_body(workflow, "build")
    live_step = _named_step_body(body, DOCKER_LIVE_STEP_NAME)
    with pytest.raises(AssertionError):
        _assert_docker_tag_publish_contract(
            workflow.replace(live_step, "", 1)
        )


def test_docker_tag_contract_rejects_skipped_or_soft_failed_e2e() -> None:
    workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
    body = _job_body(workflow, "build")
    live_step = _named_step_body(body, DOCKER_LIVE_STEP_NAME)
    for weakened_step in (
        live_step.replace(f"if: {TAG_CONDITION}", "if: false", 1),
        live_step.replace(
            f"- name: {DOCKER_LIVE_STEP_NAME}",
            f"- name: {DOCKER_LIVE_STEP_NAME}\n"
            "        continue-on-error: true",
            1,
        ),
    ):
        assert weakened_step != live_step
        with pytest.raises(AssertionError):
            _assert_docker_tag_publish_contract(
                workflow.replace(live_step, weakened_step, 1)
            )


def test_docker_tag_contract_rejects_publish_without_e2e_success() -> None:
    workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
    weakened_push = (
        "${{ github.event_name != 'pull_request' && "
        "(github.ref == 'refs/heads/main' || "
        "startsWith(github.ref, 'refs/tags/v')) && "
        "github.repository == format('{0}/zigbeelens', github.repository_owner) }}"
    )
    assert DOCKER_PUSH_EXPRESSION in workflow
    with pytest.raises(AssertionError):
        _assert_docker_tag_publish_contract(
            workflow.replace(DOCKER_PUSH_EXPRESSION, weakened_push, 1)
        )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (f"uses: {SETUP_UV_REF}", "uses: astral-sh/setup-uv@main"),
        (f'version: "{SETUP_UV_VERSION}"', 'version: "latest"'),
        (CORE_SYNC_COMMAND, "uv sync --project apps/core"),
        ("node-version: 22", "node-version: 20"),
        ("pnpm install --frozen-lockfile", "pnpm install"),
        (
            "pnpm --filter @zigbeelens/shared build",
            "echo shared build skipped",
        ),
    ),
)
def test_docker_tag_contract_rejects_weakened_prerequisites(
    old: str,
    new: str,
) -> None:
    workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
    assert old in workflow
    with pytest.raises(AssertionError):
        _assert_docker_tag_publish_contract(
            workflow.replace(old, new, 1)
        )


def test_release_helper_orders_live_gate_before_hacs_packaging() -> None:
    helper = (ROOT / "scripts" / "run-release-checks.sh").read_text(
        encoding="utf-8"
    )
    structural = helper.index(
        "bash scripts/validate-ha-integration.sh --skip-matrix"
    )
    matrix = helper.index(
        "bash dist/zigbeelens-hacs/scripts/test-ha-integration-matrix.sh"
    )
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


def test_live_e2e_uses_staged_production_scheduler_ownership() -> None:
    _assert_live_ha_ownership_contract(
        RUNNER.read_text(encoding="utf-8"),
        HA_CONTROL_SERVER.read_text(encoding="utf-8"),
    )


def test_live_ha_contract_rejects_source_or_unproven_integration() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    control = HA_CONTROL_SERVER.read_text(encoding="utf-8")
    mutations = (
        (
            'bash "$repo_root/scripts/package-hacs-repo.sh"',
            'bash "$repo_root/scripts/validate-ha-integration.sh"',
        ),
        (
            'bash "$hacs_stage/scripts/validate-hacs-repo.sh"',
            'bash "$repo_root/scripts/validate-ha-integration.sh"',
        ),
        (
            'hacs_stage="$repo_root/dist/zigbeelens-hacs"',
            'hacs_stage="$repo_root/apps/ha_integration"',
        ),
        (
            'cp -R "$hacs_stage/custom_components" "$ha_config_dir/"',
            'cp -R "$repo_root/apps/ha_integration/custom_components" '
            '"$ha_config_dir/"',
        ),
        (
            'if [[ "$staged_source_commit" != "$source_commit" ]]',
            'if [[ "$staged_source_commit" == "$source_commit" ]]',
        ),
        ("SOURCE_COMMIT", "UNVERIFIED_COMMIT"),
        ("--components-dir", "--source-components-dir"),
        ("--source-commit", "--unverified-source-commit"),
        ("--provenance-file", "--unverified-provenance-file"),
    )
    for old, new in mutations:
        assert old in runner
        weakened = runner.replace(old, new)
        with pytest.raises(AssertionError):
            _assert_live_ha_ownership_contract(weakened, control)


def test_live_ha_contract_rejects_scheduler_path_masking() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    control = HA_CONTROL_SERVER.read_text(encoding="utf-8")
    debounce = re.search(
        r"(?m)^(?P<indent>\s*)debounce_seconds\s*=\s*[^,\n]+,\s*$",
        control,
    )
    assert debounce is not None

    for keyword in (
        "later_scheduler",
        "interval_scheduler",
        "task_factory",
    ):
        injected = (
            f"\n{debounce.group('indent')}{keyword}="
            "lambda *_args: None,"
        )
        weakened = (
            control[: debounce.end()]
            + injected
            + control[debounce.end() :]
        )
        with pytest.raises(AssertionError):
            _assert_live_ha_ownership_contract(runner, weakened)

    mutations = (
        (
            ".async_update_device(",
            ".async_get_device(",
        ),
        (
            "await client.async_wait_for_publish_count(",
            "await manager.async_wait_for_idle(",
        ),
        (
            "asyncio.Condition(",
            "asyncio.Lock(",
        ),
    )
    for old, new in mutations:
        assert old in control
        weakened = control.replace(old, new, 1)
        with pytest.raises(AssertionError):
            _assert_live_ha_ownership_contract(runner, weakened)


def test_live_ha_contract_rejects_disabled_runtime_detection() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    control = HA_CONTROL_SERVER.read_text(encoding="utf-8")

    assert "PYTHONASYNCIODEBUG=1" in runner
    with pytest.raises(AssertionError):
        _assert_live_ha_ownership_contract(
            runner.replace("PYTHONASYNCIODEBUG=1", "PYTHONASYNCIODEBUG=0", 1),
            control,
        )
    with pytest.raises(AssertionError):
        _assert_live_ha_ownership_contract(
            runner.replace("grep -Eiq", "grep -Eivq", 1),
            control,
        )

    mutations = (
        ("set_debug(True)", "set_debug(False)"),
        ("set_exception_handler(", "call_exception_handler("),
        (".addHandler(", ".addFilter("),
        (
            "from a thread other than the event loop",
            "ignored off-loop scheduler call",
        ),
        (
            "non-thread-safe operation",
            "ignored unsafe operation",
        ),
        (".raise_if_any(", ".ignore_any("),
    )
    for old, new in mutations:
        assert old in control
        weakened = control.replace(old, new)
        with pytest.raises(AssertionError):
            _assert_live_ha_ownership_contract(runner, weakened)


@pytest.mark.parametrize(
    "old,new",
    (
        (f"run: {CANONICAL_COMMAND}", "run: echo mock live E2E"),
        ("timeout-minutes: 30", "timeout-minutes: 0"),
        ('python-version: "3.12"', 'python-version: "3.13"'),
        (f"uses: {SETUP_UV_REF}", "uses: astral-sh/setup-uv@main"),
        ('version: "0.11.16"', 'version: "latest"'),
        ("pnpm install --frozen-lockfile", "pnpm install"),
        (CORE_SYNC_COMMAND, "uv sync --project apps/core"),
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
