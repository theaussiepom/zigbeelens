#!/usr/bin/env python3
"""Dump oracle mock scenario contract fixtures for UI/Core contract tests.

Fail closed: every scenario must produce a ReportDetailV3. Generation failure
exits nonzero and never overwrites the checked-in fixture with incomplete
output. Output is deterministic (fixed clock via mock NOW, fixed redaction salt,
sorted scenario/device keys, Core-owned vocabulary manifest).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = ROOT / "apps" / "core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from zigbeelens.config.models import AppConfig  # noqa: E402
from zigbeelens.db.connection import Database  # noqa: E402
from zigbeelens.decisions.device_story import (  # noqa: E402
    DEVICE_STORY_HEADLINE_CODES,
    CheckCode,
    LimitationCode,
)
from zigbeelens.decisions.reasons import REASON_CODES  # noqa: E402
from zigbeelens.decisions.types import (  # noqa: E402
    CoverageDimension,
    CoverageLabelCode,
    CoverageState,
    DecisionPriority,
    DecisionStatus,
)
from zigbeelens.enrichment.ha import (  # noqa: E402
    HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT,
)
from zigbeelens.mock.fixtures import BUILDERS, NOW  # noqa: E402
from zigbeelens.schemas import RedactionOptions, ReportRequest  # noqa: E402
from zigbeelens.services import report_redaction as report_redaction_mod  # noqa: E402
from zigbeelens.services import reports as reports_mod  # noqa: E402
from zigbeelens.services.data_service import DataService  # noqa: E402
from zigbeelens.services.mock_provider import MockProvider  # noqa: E402
from zigbeelens.services.report_redaction import resolve_redaction  # noqa: E402
from zigbeelens.services.reports import generate_report  # noqa: E402
from zigbeelens.storage.incident_collection import build_incident_collection_query  # noqa: E402
from zigbeelens.storage.repository import Repository  # noqa: E402

ORACLE_CONTRACT_VERSION = 2
DEFAULT_OUTPUT = (
    ROOT / "apps" / "ui" / "src" / "test" / "fixtures" / "oracleMockScenarios.json"
)
_ORACLE_REDACTION_SALT = "zigbeelens-oracle-fixture-v1"


def _sorted_unique(values: set[str] | frozenset[str] | list[str]) -> list[str]:
    cleaned = sorted({str(v) for v in values if str(v).strip()})
    return cleaned


def build_vocabulary_manifest() -> dict[str, list[str]]:
    """Derive vocabulary directly from Core enums/registries (not scenario emission)."""
    return {
        "decision_statuses": _sorted_unique(m.value for m in DecisionStatus),
        "decision_priorities": _sorted_unique(m.value for m in DecisionPriority),
        "headline_codes": _sorted_unique(DEVICE_STORY_HEADLINE_CODES),
        "reason_codes": _sorted_unique(REASON_CODES),
        "limitation_codes": _sorted_unique(m.value for m in LimitationCode),
        "suggested_check_codes": _sorted_unique(m.value for m in CheckCode),
        "coverage_dimensions": _sorted_unique(m.value for m in CoverageDimension),
        "coverage_states": _sorted_unique(m.value for m in CoverageState),
        "coverage_label_codes": _sorted_unique(m.value for m in CoverageLabelCode),
        "live_event_types": _sorted_unique(
            [HOME_ASSISTANT_ENRICHMENT_UPDATED_EVENT]
        ),
    }


def _story_key(network_id: str, ieee_address: str) -> str:
    return f"{network_id}|{ieee_address}"


def _report_story_keys(
    provider: MockProvider,
    redactor_cls: type,
) -> dict[str, str]:
    """Map raw API story keys to redacted report story keys (same salt/profile)."""
    resolved = resolve_redaction(RedactionOptions(profile="standard"))
    redactor = redactor_cls(resolved, salt=_ORACLE_REDACTION_SALT)
    mapping: dict[str, str] = {}
    for network_id, ieee in sorted(provider.data.device_stories, key=lambda item: item):
        raw = _story_key(network_id, ieee)
        report_network = redactor._network_id(network_id)  # noqa: SLF001 — fixture join
        report_ieee = redactor._ieee(ieee)  # noqa: SLF001 — fixture join
        mapping[raw] = _story_key(report_network, report_ieee)
    return mapping


def _representative_subjects(
    provider: MockProvider,
    report_story_keys: dict[str, str],
) -> list[dict[str, str]]:
    """Pick deterministic representative device subjects for focused component tests."""
    subjects: list[dict[str, str]] = []
    seen: set[str] = set()
    ranked = sorted(
        provider.data.device_stories.items(),
        key=lambda item: (
            0 if item[1].status.value != "no_notable_change" else 1,
            item[0][0],
            item[0][1],
        ),
    )
    for (network_id, ieee), story in ranked:
        key = _story_key(network_id, ieee)
        if key in seen:
            continue
        subjects.append(
            {
                "network_id": network_id,
                "ieee_address": ieee,
                "report_story_key": report_story_keys[key],
                "status": story.status.value,
                "priority": story.priority.value,
                "headline_code": story.headline_code,
            }
        )
        seen.add(key)
        if len(subjects) >= 3:
            break
    if not subjects:
        for device in sorted(
            provider.devices(), key=lambda d: (d.network_id, d.ieee_address)
        )[:1]:
            key = _story_key(device.network_id, device.ieee_address)
            subjects.append(
                {
                    "network_id": device.network_id,
                    "ieee_address": device.ieee_address,
                    "report_story_key": report_story_keys.get(key, key),
                    "status": "unknown",
                    "priority": "none",
                    "headline_code": "missing",
                }
            )
    return subjects


def build_fixtures() -> dict[str, Any]:
    original_redactor = report_redaction_mod.Redactor
    original_reports_redactor = reports_mod.Redactor

    class _DeterministicRedactor(original_redactor):  # type: ignore[misc,valid-type]
        def __init__(self, resolved, salt: str = _ORACLE_REDACTION_SALT) -> None:
            super().__init__(resolved, salt=salt)

    report_redaction_mod.Redactor = _DeterministicRedactor  # type: ignore[misc]
    reports_mod.Redactor = _DeterministicRedactor  # type: ignore[misc]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "oracle-fixture-gen.sqlite")
            db.migrate()
            repo = Repository(db)
            config = AppConfig()
            config.mode.mock = True
            data = DataService(config, repo)

            scenarios: dict[str, dict] = {}
            for scenario_id in sorted(BUILDERS):
                provider = MockProvider(scenario_id)
                incidents_page = provider.incidents_page(
                    build_incident_collection_query(limit=50)
                )
                report = generate_report(
                    data=data,
                    config=config,
                    reporting=config.reporting,
                    collector={},
                    request=ReportRequest(),
                    scenario=scenario_id,
                    now=NOW,
                )
                device_stories = {
                    _story_key(network_id, ieee): story.model_dump(mode="json")
                    for (network_id, ieee), story in sorted(
                        provider.data.device_stories.items(),
                        key=lambda item: (item[0][0], item[0][1]),
                    )
                }
                report_story_keys = _report_story_keys(provider, _DeterministicRedactor)
                scenarios[scenario_id] = {
                    "dashboard": provider.dashboard().model_dump(mode="json"),
                    "devices": [
                        device.model_dump(mode="json") for device in provider.devices()
                    ],
                    "networks": [
                        network.model_dump(mode="json") for network in provider.networks()
                    ],
                    "incidents": [
                        incident.model_dump(mode="json")
                        for incident in incidents_page["items"]
                    ],
                    "report": report.model_dump(mode="json"),
                    "device_stories": device_stories,
                    "report_story_keys": report_story_keys,
                    "representative_subjects": _representative_subjects(
                        provider, report_story_keys
                    ),
                }
            return {
                "oracle_contract_version": ORACLE_CONTRACT_VERSION,
                "vocabulary": build_vocabulary_manifest(),
                "scenarios": scenarios,
            }
    finally:
        report_redaction_mod.Redactor = original_redactor  # type: ignore[misc]
        reports_mod.Redactor = original_reports_redactor  # type: ignore[misc]


def render_fixtures(fixtures: dict[str, Any]) -> str:
    return json.dumps(fixtures, indent=2, sort_keys=True) + "\n"


def validate_fixture_payload(fixtures: dict[str, Any]) -> None:
    """Raise ValueError when the payload must not be published."""
    if fixtures.get("oracle_contract_version") != ORACLE_CONTRACT_VERSION:
        raise ValueError(
            f"oracle_contract_version must be {ORACLE_CONTRACT_VERSION}"
        )
    vocabulary = fixtures.get("vocabulary")
    if not isinstance(vocabulary, dict) or not vocabulary:
        raise ValueError("vocabulary manifest missing")
    expected_vocab = build_vocabulary_manifest()
    if vocabulary != expected_vocab:
        raise ValueError("vocabulary manifest does not match Core registries")
    for key, values in vocabulary.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"vocabulary.{key} must be a non-empty list")
        if values != sorted(set(values)):
            raise ValueError(f"vocabulary.{key} must be sorted unique values")
        if any(not str(v).strip() for v in values):
            raise ValueError(f"vocabulary.{key} contains blank values")

    scenarios = fixtures.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("empty scenarios")
    if set(scenarios) != set(BUILDERS):
        raise ValueError(
            f"scenario ownership mismatch: {sorted(scenarios)} != {sorted(BUILDERS)}"
        )

    status_set = set(vocabulary["decision_statuses"])
    priority_set = set(vocabulary["decision_priorities"])
    headline_set = set(vocabulary["headline_codes"])
    reason_set = set(vocabulary["reason_codes"])
    limitation_set = set(vocabulary["limitation_codes"])
    check_set = set(vocabulary["suggested_check_codes"])
    dimension_set = set(vocabulary["coverage_dimensions"])
    state_set = set(vocabulary["coverage_states"])
    label_set = set(vocabulary["coverage_label_codes"])

    for scenario_id, payload in scenarios.items():
        report = payload.get("report")
        if report is None:
            raise ValueError(f"null report for {scenario_id}")
        if type(report.get("report_version")) is not int or report.get("report_version") != 3:
            raise ValueError(f"report_version!=3 for {scenario_id}")
        for key, story in (payload.get("device_stories") or {}).items():
            if story.get("status") not in status_set:
                raise ValueError(f"unknown status in {scenario_id}:{key}")
            if story.get("priority") not in priority_set:
                raise ValueError(f"unknown priority in {scenario_id}:{key}")
            if story.get("headline_code") not in headline_set:
                raise ValueError(f"unknown headline in {scenario_id}:{key}")
            for reason in story.get("reasons") or []:
                if reason.get("code") not in reason_set:
                    raise ValueError(f"unknown reason in {scenario_id}:{key}")
            for limitation in story.get("limitations") or []:
                if limitation.get("code") not in limitation_set:
                    raise ValueError(f"unknown limitation in {scenario_id}:{key}")
            for check in story.get("suggested_checks") or []:
                if check.get("code") not in check_set:
                    raise ValueError(f"unknown check in {scenario_id}:{key}")
            for item in story.get("coverage") or []:
                if item.get("dimension") not in dimension_set:
                    raise ValueError(f"unknown coverage dimension in {scenario_id}:{key}")
                if item.get("state") not in state_set:
                    raise ValueError(f"unknown coverage state in {scenario_id}:{key}")
                if item.get("label_code") not in label_set:
                    raise ValueError(f"unknown coverage label in {scenario_id}:{key}")


def publish_fixture_text(text: str, output: Path) -> None:
    """Atomically publish validated fixture bytes."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output.with_suffix(output.suffix + ".tmp")
    tmp_out.write_text(text, encoding="utf-8")
    tmp_out.replace(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination JSON path (default: checked-in UI fixture)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare generated bytes to --output without writing",
    )
    args = parser.parse_args(argv)
    try:
        fixtures = build_fixtures()
        validate_fixture_payload(fixtures)
    except Exception as exc:  # noqa: BLE001 — fail closed with nonzero exit
        print(f"oracle fixture generation failed: {exc}", file=sys.stderr)
        return 1

    text = render_fixtures(fixtures)
    if args.check:
        if not args.output.is_file():
            print(f"oracle fixture check failed: missing {args.output}", file=sys.stderr)
            return 1
        checked = args.output.read_text(encoding="utf-8")
        if checked != text:
            print(
                f"oracle fixture check failed: drift vs {args.output}",
                file=sys.stderr,
            )
            return 1
        print(f"Oracle fixture fresh ({len(fixtures['scenarios'])} scenarios)")
        return 0

    publish_fixture_text(text, args.output)
    print(f"Wrote {args.output} ({len(fixtures['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
