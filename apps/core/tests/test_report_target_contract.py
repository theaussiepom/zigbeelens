"""HTTP and storage contract for contextual report target resolution."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from zigbeelens.app.context import get_context


TARGET_CASES = (
    ("network", {}, {"network_id": "unknown-network"}),
    ("incident", {}, {"incident_id": "unknown-incident"}),
    ("device", {}, {"device": "0x000000000000dead", "network_id": "home"}),
    ("device", {}, {"device": "0x000000000000dead"}),
)


def _assert_json_error_parity(
    responses: Iterable,
    *,
    expected_status: int,
) -> None:
    responses = list(responses)
    assert responses
    assert {response.status_code for response in responses} == {expected_status}
    assert all(
        response.headers["content-type"].startswith("application/json") for response in responses
    )
    assert len({response.text for response in responses}) == 1


def _exercise_failure_matrix(client: TestClient) -> None:
    for scope, missing, unknown in TARGET_CASES:
        reports_before = client.get("/api/reports").json()

        missing_responses = []
        unknown_responses = []
        for prefix in ("/api", "/api/v1"):
            missing_responses.extend(
                [
                    client.get(
                        f"{prefix}/reports/preview",
                        params={"scope": scope, **missing},
                    ),
                    client.post(
                        f"{prefix}/reports",
                        json={"format": "json", "scope": scope, **missing},
                    ),
                ]
            )
            unknown_responses.extend(
                [
                    client.get(
                        f"{prefix}/reports/preview",
                        params={"scope": scope, **unknown},
                    ),
                    client.post(
                        f"{prefix}/reports",
                        json={"format": "json", "scope": scope, **unknown},
                    ),
                ]
            )

        _assert_json_error_parity(missing_responses, expected_status=422)
        _assert_json_error_parity(unknown_responses, expected_status=404)
        assert client.get("/api/reports").json() == reports_before


def test_contextual_target_failures_are_exact_in_live_mode(live_client: TestClient):
    _exercise_failure_matrix(live_client)


def test_contextual_target_failures_are_exact_in_scenario_mode(mock_client: TestClient):
    _exercise_failure_matrix(mock_client)


@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
def test_duplicate_device_identity_is_422_and_not_stored(
    live_client: TestClient,
    prefix: str,
):
    repo = get_context().repo
    for network_id in ("home", "home2"):
        repo.upsert_device(
            network_id=network_id,
            ieee_address="0x000000000000abcd",
            friendly_name=f"Duplicate {network_id}",
            device_type="Router",
            power_source="Mains",
            interview_state="successful",
        )

    before = live_client.get(f"{prefix}/reports").json()
    preview = live_client.get(
        f"{prefix}/reports/preview",
        params={"scope": "device", "device": "0x000000000000abcd"},
    )
    created = live_client.post(
        f"{prefix}/reports",
        json={
            "format": "json",
            "scope": "device",
            "device": "0x000000000000abcd",
        },
    )
    assert preview.status_code == created.status_code == 422
    assert preview.json() == created.json()
    assert "provide network_id" in preview.json()["detail"]
    assert live_client.get(f"{prefix}/reports").json() == before


@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
def test_valid_target_succeeds_after_unknown_target(prefix: str, mock_client: TestClient):
    devices = mock_client.get(f"{prefix}/devices").json()["items"]
    target = devices[0]

    failed = mock_client.get(
        f"{prefix}/reports/preview",
        params={
            "scope": "device",
            "network_id": target["network_id"],
            "device": "0x000000000000dead",
        },
    )
    assert failed.status_code == 404

    recovered = mock_client.get(
        f"{prefix}/reports/preview",
        params={
            "scope": "device",
            "network_id": target["network_id"],
            "device": target["ieee_address"],
        },
    )
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["scope"] == "device"
    assert body["raw_counts"]["devices_included"] == 1
    assert body["domain_details"]["devices"]
