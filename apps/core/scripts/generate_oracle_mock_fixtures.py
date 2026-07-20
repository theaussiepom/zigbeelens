#!/usr/bin/env python3
"""Dump oracle mock scenario contract fixtures for UI tests."""

from __future__ import annotations

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
from zigbeelens.services.data_service import DataService  # noqa: E402
from zigbeelens.services.mock_provider import MockProvider  # noqa: E402
from zigbeelens.services.reports import generate_report  # noqa: E402
from zigbeelens.storage.incident_collection import build_incident_collection_query  # noqa: E402
from zigbeelens.storage.repository import Repository  # noqa: E402

OUTPUT = ROOT / "apps" / "ui" / "src" / "test" / "fixtures" / "oracleMockScenarios.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "oracle-fixture-gen.sqlite")
        db.migrate()
        repo = Repository(db)
        config = AppConfig()
        config.mode.mock = True
        data = DataService(config, repo)

        fixtures: dict[str, dict] = {}
        for scenario_id in BUILDERS:
            provider = MockProvider(scenario_id)
            incidents_page = provider.incidents_page(build_incident_collection_query(limit=50))
            try:
                report = generate_report(
                    data=data,
                    config=config,
                    reporting=config.reporting,
                    collector={},
                    request=ReportRequest(),
                    scenario=scenario_id,
                    now=NOW,
                ).model_dump(mode="json")
            except Exception:
                report = None

            fixtures[scenario_id] = {
                "dashboard": provider.dashboard().model_dump(mode="json"),
                "devices": [device.model_dump(mode="json") for device in provider.devices()],
                "networks": [network.model_dump(mode="json") for network in provider.networks()],
                "incidents": [
                    incident.model_dump(mode="json") for incident in incidents_page["items"]
                ],
                "report": report,
            }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(fixtures)} scenarios)")


if __name__ == "__main__":
    main()
