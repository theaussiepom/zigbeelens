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


def test_health_redacts_collector_last_error(live_client: TestClient):
    from zigbeelens.app.context import get_context

    ctx = get_context()
    ctx.repo.update_collector_status(
        enabled=True,
        connected=False,
        subscribed_topics_count=0,
        last_error="Connection refused mqtt://user:secret@broker:1883",
    )
    res = live_client.get("/api/health")
    assert res.status_code == 200
    collector = res.json()["collector"]
    assert collector["last_error"] == "[redacted]"
    assert "secret" not in str(collector)


def test_openapi_disabled_by_default(live_client: TestClient):
    assert live_client.get("/docs").status_code == 404
    assert live_client.get("/openapi.json").status_code == 404


def test_openapi_enabled_when_configured(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from zigbeelens.app.context import reset_context
    from zigbeelens.main import create_app

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: true
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {tmp_path / "openapi.sqlite"}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(config_path))
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    reset_context()
    with TestClient(create_app(str(config_path))) as client:
        assert client.get("/openapi.json").status_code == 200
    reset_context()


def test_dashboard_default_scenario(mock_client: TestClient):
    res = mock_client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == DEFAULT_SCENARIO
    assert "decision_summary" in data
    assert data["decision_summary"]["overall_status"]
    assert "current_finding" not in data
    assert "health_snapshot" not in data


def test_all_mock_scenarios_load(mock_client: TestClient):
    for scenario_id in BUILDERS:
        res = mock_client.get("/api/dashboard", params={"scenario": scenario_id})
        assert res.status_code == 200, scenario_id
        body = res.json()
        assert body["scenario"] == scenario_id
        assert body["decision_summary"]["overall_status"]
        assert isinstance(body["shared_availability_events"], list)
        assert isinstance(body["model_patterns"], list)
        assert "current_finding" not in body
        assert "top_affected_devices" not in body


def test_device_lookup(mock_client: TestClient):
    devices = mock_client.get("/api/devices").json()["items"]
    assert devices
    d = devices[0]
    path = f"/api/devices/{d['network_id']}/{d['ieee_address']}"
    res = mock_client.get(path)
    assert res.status_code == 200
    body = res.json()
    assert body["ieee_address"] == d["ieee_address"]
    assert body["decision"]["status"]
    assert "health" not in body
    assert "diagnostic" not in body
    assert "lens_bucket" not in body


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
    security = body["security"]
    assert security["mode"] == "local"
    assert security["loopback_bind"] is True
    assert security["api_token_configured"] is False
    assert security["session_secret_configured"] is False
    assert security["trusted_local_open"] is True
    assert security["bearer_auth_enabled"] is False
    assert security["legacy_mutation_guard_enabled"] is False
    assert "api_token" not in security
    assert "session_secret" not in security


def test_live_empty_dashboard(live_client: TestClient):
    res = live_client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] is None
    assert data["decision_summary"]["overall_status"] == "data_unavailable"
    assert data["device_count"] == 0
    assert len(data["networks"]) == 2
    assert "top_affected_devices" not in data
    assert "current_finding" not in data


def test_live_mode_uses_scenario_override(live_client: TestClient):
    res = live_client.get("/api/dashboard", params={"scenario": "bridge_offline"})
    assert res.status_code == 200
    assert res.json()["scenario"] == "bridge_offline"


def test_create_and_fetch_report(mock_client: TestClient):
    created = mock_client.post("/api/reports").json()
    assert created["id"]
    fetched = mock_client.get(f"/api/reports/{created['id']}").json()
    assert fetched["id"] == created["id"]
