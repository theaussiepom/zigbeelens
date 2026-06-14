from fastapi.testclient import TestClient

from zigbeelens.mock.fixtures import BUILDERS, DEFAULT_SCENARIO


def test_health(mock_client: TestClient):
    res = mock_client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert body["config_loaded"] is True
    assert body["database"] == "ok"
    assert body["migration_version"] >= 2
    assert "collector" in body


def test_dashboard_default_scenario(mock_client: TestClient):
    res = mock_client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == DEFAULT_SCENARIO
    assert "current_finding" in data
    assert "evidence" in data["current_finding"]


def test_all_mock_scenarios_load(mock_client: TestClient):
    for scenario_id in BUILDERS:
        res = mock_client.get("/api/dashboard", params={"scenario": scenario_id})
        assert res.status_code == 200, scenario_id
        body = res.json()
        assert body["scenario"] == scenario_id
        finding = body["current_finding"]
        assert finding["summary"]
        assert isinstance(finding["evidence"], list)
        assert isinstance(finding["limitations"], list)


def test_device_lookup(mock_client: TestClient):
    dash = mock_client.get("/api/dashboard").json()
    if dash["top_affected_devices"]:
        d = dash["top_affected_devices"][0]
        path = f"/api/devices/{d['network_id']}/{d['ieee_address']}"
        res = mock_client.get(path)
        assert res.status_code == 200
        assert res.json()["ieee_address"] == d["ieee_address"]


def test_report_preview(mock_client: TestClient):
    res = mock_client.get("/api/reports/preview")
    assert res.status_code == 200
    data = res.json()
    assert data["redaction"]["mqtt_credentials"] is True
    assert "markdown_summary" in data


def test_config_status_redacts_secrets(mock_client: TestClient):
    res = mock_client.get("/api/config/status")
    assert res.status_code == 200
    body = res.json()
    assert "secret" not in body["mqtt_server"]
    assert "***" in body["mqtt_server"]
    assert body["mock_mode"] is True
    assert body["diagnostics"]["flapping_threshold"] == 3


def test_live_empty_dashboard(live_client: TestClient):
    res = live_client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] is None
    assert "No Zigbee2MQTT data has been collected yet" in data["current_finding"]["summary"]
    assert len(data["networks"]) == 2
    assert data["top_affected_devices"] == []


def test_live_mode_uses_scenario_override(live_client: TestClient):
    res = live_client.get("/api/dashboard", params={"scenario": "bridge_offline"})
    assert res.status_code == 200
    assert res.json()["scenario"] == "bridge_offline"


def test_create_and_fetch_report(mock_client: TestClient):
    created = mock_client.post("/api/reports").json()
    assert created["id"]
    fetched = mock_client.get(f"/api/reports/{created['id']}").json()
    assert fetched["id"] == created["id"]
