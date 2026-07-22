#!/usr/bin/env python3
"""Dump oracle mock scenario contract fixtures for UI/Core contract tests.

Fail closed: every scenario must produce a ReportDetailV3. Generation failure
exits nonzero and never overwrites the checked-in fixture with incomplete
output. Output is deterministic (fixed clock via mock NOW, fixed redaction salt,
sorted scenario/device keys).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = ROOT / "apps" / "core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from zigbeelens.config.models import AppConfig  # noqa: E402
from zigbeelens.db.connection import Database  # noqa: E402
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

ORACLE_CONTRACT_VERSION = 1
DEFAULT_OUTPUT = (
    ROOT / "apps" / "ui" / "src" / "test" / "fixtures" / "oracleMockScenarios.json"
)
_ORACLE_REDACTION_SALT = "zigbeelens-oracle-fixture-v1"


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
    """Pick deterministic representative device subjects for parity matrices."""
    subjects: list[dict[str, str]] = []
    seen: set[str] = set()
    # Prefer non-baseline stories first, then fall back to first device.
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


def build_fixtures() -> dict:
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
                "scenarios": scenarios,
            }
    finally:
        report_redaction_mod.Redactor = original_redactor  # type: ignore[misc]
        reports_mod.Redactor = original_reports_redactor  # type: ignore[misc]


def render_fixtures(fixtures: dict) -> str:
    return json.dumps(fixtures, indent=2, sort_keys=True) + "\n"


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
    except Exception as exc:  # noqa: BLE001 — fail closed with nonzero exit
        print(f"oracle fixture generation failed: {exc}", file=sys.stderr)
        return 1

    scenarios = fixtures.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        print("oracle fixture generation failed: empty scenarios", file=sys.stderr)
        return 1
    for scenario_id, payload in scenarios.items():
        report = payload.get("report")
        if report is None:
            print(
                f"oracle fixture generation failed: null report for {scenario_id}",
                file=sys.stderr,
            )
            return 1
        if report.get("report_version") != 3:
            print(
                f"oracle fixture generation failed: report_version!=3 for {scenario_id}",
                file=sys.stderr,
            )
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
        print(f"Oracle fixture fresh ({len(scenarios)} scenarios)")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Write via temp+replace only after full validation so incomplete runs never
    # overwrite the checked-in fixture.
    tmp_out = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp_out.write_text(text, encoding="utf-8")
    tmp_out.replace(args.output)
    print(f"Wrote {args.output} ({len(scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
