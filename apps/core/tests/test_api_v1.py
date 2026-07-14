"""API v1 alias, capabilities, and status endpoint tests."""

from fastapi.testclient import TestClient


def test_v1_dashboard_matches_api_dashboard(mock_client: TestClient):
    legacy = mock_client.get("/api/dashboard")
    v1 = mock_client.get("/api/v1/dashboard")
    assert legacy.status_code == 200
    assert v1.status_code == 200
    assert legacy.json() == v1.json()


def test_v1_health_works(mock_client: TestClient):
    res = mock_client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert "collector" in body


def test_v1_health_matches_legacy(mock_client: TestClient):
    legacy = mock_client.get("/api/health").json()
    v1 = mock_client.get("/api/v1/health").json()
    assert legacy == v1


def test_v1_capabilities(mock_client: TestClient):
    res = mock_client.get("/api/v1/capabilities")
    assert res.status_code == 200
    body = res.json()
    assert body["product"] == "zigbeelens"
    assert "version" in body
    assert body["decision_contract_version"] == 1
    caps = body["capabilities"]
    assert caps["dashboard"] is True
    assert caps["sse"] is True
    assert caps["reports"] is True
    assert caps["read_only_observability"] is True
    assert caps["mock_scenarios"] is True
    assert caps["home_assistant_enrichment"] is True
    assert caps["shared_decisions"] is True
    assert caps["companion_decision_summary"] is True
    assert isinstance(caps["mqtt_discovery"], bool)
    assert isinstance(caps["topology"], bool)
    assert isinstance(caps["mqtt_collector"], bool)
    surfaces = body["decision_surfaces"]
    assert surfaces["dashboard_investigation_priorities"] is True
    assert surfaces["dashboard_data_coverage_warnings"] is True
    assert surfaces["device_story"] is True
    assert surfaces["report_device_stories"] is True


def test_v1_status(mock_client: TestClient):
    res = mock_client.get("/api/v1/status")
    assert res.status_code == 200
    body = res.json()
    assert body["product"] == "zigbeelens"
    assert body["status"] in {"ok", "degraded"}
    assert body["data_mode"] == "mock"
    assert "collectors" in body
    assert "mqtt" in body["collectors"]
    assert "zigbee2mqtt" in body["collectors"]
    assert "storage" in body
    assert "reports" in body


def test_v1_status_does_not_expose_secrets(live_client: TestClient):
    from zigbeelens.app.context import get_context

    ctx = get_context()
    ctx.repo.update_collector_status(
        enabled=True,
        connected=False,
        subscribed_topics_count=0,
        last_error="Connection refused mqtt://user:secret@broker:1883",
    )
    res = live_client.get("/api/v1/status")
    assert res.status_code == 200
    payload = res.text.lower()
    assert "secret" not in payload
    assert "password" not in payload


def test_v1_reports_routes(mock_client: TestClient):
    preview_legacy = mock_client.get("/api/reports/preview")
    preview_v1 = mock_client.get("/api/v1/reports/preview")
    assert preview_legacy.status_code == 200
    assert preview_v1.status_code == 200
    legacy_body = preview_legacy.json()
    v1_body = preview_v1.json()
    assert legacy_body["product"] == v1_body["product"]
    assert legacy_body["scope"] == v1_body["scope"]

    created = mock_client.post("/api/v1/reports").json()
    assert created["id"]
    fetched = mock_client.get(f"/api/v1/reports/{created['id']}")
    assert fetched.status_code == 200


def test_v1_public_routes_still_have_legacy_aliases(mock_client: TestClient):
    routes = [
        "/api/version",
        "/api/v1/version",
        "/api/scenarios",
        "/api/v1/scenarios",
        "/api/config/status",
        "/api/v1/config/status",
        "/api/networks",
        "/api/v1/networks",
        "/api/incidents",
        "/api/v1/incidents",
        "/api/enrichment/status",
        "/api/v1/enrichment/status",
    ]
    for path in routes:
        res = mock_client.get(path)
        assert res.status_code == 200, path


def test_v1_events_stream_route_registered(live_client: TestClient):
    paths = {route.path for route in live_client.app.routes if hasattr(route, "path")}
    assert "/api/events/stream" in paths
    assert "/api/v1/events/stream" in paths
