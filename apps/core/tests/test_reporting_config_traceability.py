"""Release-blocker traceability for every supported ReportingConfig leaf."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from zigbeelens.config.models import AppConfig, ReportingConfig
from zigbeelens.db.connection import Database
from zigbeelens.schemas import RedactionOptions, ReportRequest
from zigbeelens.services.data_service import DataService
from zigbeelens.services.reports import generate_report
from zigbeelens.storage.repository import Repository


REPO_ROOT = Path(__file__).resolve().parents[3]

# This matrix is intentionally test-owned: adding an accepted reporting leaf
# requires naming its production owner, observable behavior, boundary test and
# documentation owner in the same change.
REPORTING_CONTROL_TRACEABILITY = {
    "max_recent_events": {
        "production_owner": "services/report_composition.py",
        "observable_behavior": "caps report-v3 events_or_timeline",
        "boundary_test": "test_max_recent_events_changes_final_report_v3",
        "documentation_owner": "docs/configuration.md",
    },
    "default_profile": {
        "production_owner": "services/reports.py -> report_redaction.py",
        "observable_behavior": "sets report-v3 redaction.profile when no request override exists",
        "boundary_test": "test_default_profile_changes_final_report_v3",
        "documentation_owner": "docs/configuration.md",
    },
}

REMOVED_NO_OP_CONTROLS = (
    "max_metric_samples_per_device",
    "max_availability_changes_per_device",
    "include_raw_payloads",
)


def _mock_report(
    tmp_path: Path,
    reporting: ReportingConfig,
    request: ReportRequest | None = None,
):
    db = Database(tmp_path / "reporting-traceability.sqlite")
    db.migrate()
    repo = Repository(db)
    config = AppConfig(reporting=reporting)
    config.mode.mock = True
    data = DataService(config, repo)
    return generate_report(
        data=data,
        config=config,
        reporting=reporting,
        collector={},
        request=request or ReportRequest(),
    )


def test_traceability_matrix_exactly_owns_every_reporting_leaf():
    assert set(REPORTING_CONTROL_TRACEABILITY) == set(ReportingConfig.model_fields)
    for ownership in REPORTING_CONTROL_TRACEABILITY.values():
        assert all(ownership.values())


@pytest.mark.parametrize("value", [0, -1, 1001])
def test_max_recent_events_rejects_out_of_range_values(value: int):
    with pytest.raises(ValidationError):
        ReportingConfig(max_recent_events=value)


@pytest.mark.parametrize("value", [1, 1000])
def test_max_recent_events_accepts_documented_boundaries(value: int):
    assert ReportingConfig(max_recent_events=value).max_recent_events == value


def test_max_recent_events_changes_final_report_v3(tmp_path: Path):
    one = _mock_report(tmp_path, ReportingConfig(max_recent_events=1))
    many = _mock_report(tmp_path, ReportingConfig(max_recent_events=1000))

    assert len(one.events_or_timeline) == 1
    assert one.raw_counts["events_included"] == 1
    assert len(many.events_or_timeline) > len(one.events_or_timeline)
    assert many.raw_counts["events_included"] == len(many.events_or_timeline)


def test_default_profile_changes_final_report_v3(tmp_path: Path):
    inherited = _mock_report(
        tmp_path,
        ReportingConfig(default_profile="public_safe"),
    )
    assert inherited.redaction.profile == "public_safe"
    assert inherited.redaction.hostnames is True
    assert inherited.redaction.network_names == "labeled"

    explicit = _mock_report(
        tmp_path,
        ReportingConfig(default_profile="public_safe"),
        ReportRequest(redaction=RedactionOptions(profile="standard")),
    )
    assert explicit.redaction.profile == "standard"
    assert explicit.redaction.hostnames is False
    assert explicit.redaction.network_names == "preserved"


@pytest.mark.parametrize("field", REMOVED_NO_OP_CONTROLS)
def test_removed_reporting_controls_are_rejected_not_silently_accepted(field: str):
    with pytest.raises(ValidationError):
        ReportingConfig.model_validate({field: False if field == "include_raw_payloads" else 50})


def test_removed_raw_request_surface_is_rejected_not_silently_accepted():
    with pytest.raises(ValidationError):
        RedactionOptions.model_validate({"include_raw_payloads": True})


@pytest.mark.parametrize(
    "relative_path",
    [
        "config/config.yaml",
        "config/config.live.example.yaml",
        "examples/config.example.yaml",
        "deploy/compose/config.dev.yaml",
        "deploy/docker/config.example.yaml",
        "deploy/docker/config.multi-network.example.yaml",
    ],
)
def test_core_config_examples_expose_only_owned_reporting_controls(relative_path: str):
    payload = yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    assert set(payload["reporting"]) == set(REPORTING_CONTROL_TRACEABILITY)
    ReportingConfig.model_validate(payload["reporting"])


def test_addon_schema_matches_owned_reporting_controls():
    payload = yaml.safe_load(
        (REPO_ROOT / "apps/addon/zigbeelens/config.yaml").read_text(encoding="utf-8")
    )
    assert set(payload["options"]["reporting"]) == set(REPORTING_CONTROL_TRACEABILITY)
    assert set(payload["schema"]["reporting"]) == set(REPORTING_CONTROL_TRACEABILITY)
    assert payload["schema"]["reporting"]["max_recent_events"] == "int(1,1000)?"
