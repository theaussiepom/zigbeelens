#!/usr/bin/env python3
"""Dump oracle mock scenario contract fixtures for UI tests.

Fail closed: every scenario must produce a ReportDetailV3. Generation failure
exits nonzero and never writes null reports. Output is deterministic.
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
from zigbeelens.schemas import ReportRequest  # noqa: E402
from zigbeelens.services import report_redaction as report_redaction_mod  # noqa: E402
from zigbeelens.services import reports as reports_mod  # noqa: E402
from zigbeelens.services.data_service import DataService  # noqa: E402
from zigbeelens.services.mock_provider import MockProvider  # noqa: E402
from zigbeelens.services.reports import generate_report  # noqa: E402
from zigbeelens.storage.incident_collection import build_incident_collection_query  # noqa: E402
from zigbeelens.storage.repository import Repository  # noqa: E402

DEFAULT_OUTPUT = ROOT / "apps" / "ui" / "src" / "test" / "fixtures" / "oracleMockScenarios.json"
# Fixed redaction salt so regenerated fixture bytes stay stable across runs.
_ORACLE_REDACTION_SALT = "zigbeelens-oracle-fixture-v1"


def build_fixtures() -> dict[str, dict]:
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

            fixtures: dict[str, dict] = {}
            for scenario_id in sorted(BUILDERS):
                provider = MockProvider(scenario_id)
                incidents_page = provider.incidents_page(build_incident_collection_query(limit=50))
                report = generate_report(
                    data=data,
                    config=config,
                    reporting=config.reporting,
                    collector={},
                    request=ReportRequest(),
                    scenario=scenario_id,
                    now=NOW,
                )
                fixtures[scenario_id] = {
                    "dashboard": provider.dashboard().model_dump(mode="json"),
                    "devices": [device.model_dump(mode="json") for device in provider.devices()],
                    "networks": [network.model_dump(mode="json") for network in provider.networks()],
                    "incidents": [
                        incident.model_dump(mode="json") for incident in incidents_page["items"]
                    ],
                    "report": report.model_dump(mode="json"),
                }
            return fixtures
    finally:
        report_redaction_mod.Redactor = original_redactor  # type: ignore[misc]
        reports_mod.Redactor = original_reports_redactor  # type: ignore[misc]


def render_fixtures(fixtures: dict[str, dict]) -> str:
    return json.dumps(fixtures, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination JSON path (default: checked-in UI fixture)",
    )
    args = parser.parse_args(argv)
    try:
        fixtures = build_fixtures()
    except Exception as exc:  # noqa: BLE001 — fail closed with nonzero exit
        print(f"oracle fixture generation failed: {exc}", file=sys.stderr)
        return 1

    for scenario_id, payload in fixtures.items():
        if payload.get("report") is None:
            print(f"oracle fixture generation failed: null report for {scenario_id}", file=sys.stderr)
            return 1

    text = render_fixtures(fixtures)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output} ({len(fixtures)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
