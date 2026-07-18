"""Track 4B bearer authentication matrix: modes, headers, SSE, downloads, OpenAPI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from zigbeelens.api.auth import AUTH_DETAIL
from zigbeelens.main import create_app

VALID_TOKEN = "b" * 32
OTHER_TOKEN = "e" * 32


def _write_config(path: Path, *, security: str = "") -> None:
    path.write_text(
        f"""
mode:
  mock: true
storage:
  path: {path.parent / "bearer.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{security}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _bearer(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client(tmp_path: Path, monkeypatch, *, security: str = "") -> TestClient:
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, security=security)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)))


def _assert_uniform_401(res) -> None:
    assert res.status_code == 401
    assert res.json() == {"detail": AUTH_DETAIL}
    assert res.headers.get("www-authenticate") == "Bearer"
    assert "no-store" in (res.headers.get("cache-control") or "").lower()
    assert VALID_TOKEN not in res.text
    assert OTHER_TOKEN not in res.text


def test_local_token_protects_reads_mutations_sse_downloads(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        assert client.get("/api/version").status_code == 200
        assert client.get("/api/v1/version").status_code == 200
        assert client.get("/healthz").json() == {"status": "ok"}

        for path in (
            "/api/health",
            "/api/dashboard",
            "/api/config/status",
            "/api/capabilities",
            "/api/events/stream",
            "/api/reports/missing/download",
        ):
            _assert_uniform_401(client.get(path))

        _assert_uniform_401(client.post("/api/reports", json={"format": "json"}))

        assert client.get("/api/health", headers=_bearer()).status_code == 200
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
        assert client.get("/api/v1/dashboard", headers=_bearer()).status_code == 200
        assert (
            client.post(
                "/api/reports",
                json={"format": "json"},
                headers=_bearer(),
            ).status_code
            == 200
        )

        status = client.get("/api/config/status", headers=_bearer()).json()["security"]
        assert status["trusted_local_open"] is False
        assert status["bearer_auth_enabled"] is True
        assert status["browser_session_enabled"] is False
        assert status["read_routes_require_authentication"] is True
        assert status["mutation_routes_require_authentication"] is True
        assert status["read_routes_require_bearer"] is True
        assert status["mutation_routes_require_bearer"] is True
        assert status["ingress_identity_enforced"] is False


def test_authenticated_mode_requires_token_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(
        cfg,
        security="security:\n  mode: authenticated\n",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    from zigbeelens.config import ConfigError, load_config

    with pytest.raises(ConfigError, match="api_token"):
        load_config(cfg)


def test_authenticated_mode_enforces_bearer(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  mode: authenticated\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        _assert_uniform_401(client.get("/api/dashboard"))
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
        assert client.get("/healthz").status_code == 200


def test_ingress_mode_requires_token_and_uses_bearer_fallback(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, security="security:\n  mode: home_assistant_ingress\n")
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    from zigbeelens.config import ConfigError, load_config

    with pytest.raises(ConfigError, match="api_token"):
        load_config(cfg)

    with _client(
        tmp_path,
        monkeypatch,
        security=(
            f"security:\n  mode: home_assistant_ingress\n  api_token: {VALID_TOKEN}\n"
        ),
    ) as client:
        _assert_uniform_401(
            client.get(
                "/api/dashboard",
                headers={"X-Hass-User-ID": "ignored", "X-Forwarded-User": "ignored"},
            )
        )
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
        status = client.get("/api/config/status", headers=_bearer()).json()["security"]
        assert status["ingress_identity_enforced"] is False
        assert status["bearer_auth_enabled"] is True


@pytest.mark.parametrize(
    "header",
    [
        f"Bearer {VALID_TOKEN}",
        f"bearer {VALID_TOKEN}",
        f"BEARER {VALID_TOKEN}",
    ],
)
def test_bearer_scheme_case_insensitive(tmp_path, monkeypatch, header: str):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        assert (
            client.get("/api/dashboard", headers={"Authorization": header}).status_code
            == 200
        )


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": f"Bearer {OTHER_TOKEN}"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer"},
        {"Authorization": f"Basic {VALID_TOKEN}"},
        {"Authorization": f"Bearer {VALID_TOKEN}, Bearer {VALID_TOKEN}"},
        {"Authorization": f"Bearer {VALID_TOKEN} "},
        {"X-ZigbeeLens-Api-Key": VALID_TOKEN},
        {"Cookie": f"token={VALID_TOKEN}"},
    ],
)
def test_invalid_auth_material_uniform_401(tmp_path, monkeypatch, headers: dict):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        _assert_uniform_401(client.get("/api/dashboard", headers=headers))
        _assert_uniform_401(
            client.get(f"/api/dashboard?token={VALID_TOKEN}", headers=headers)
        )


def test_duplicate_authorization_headers_fail():
    from fastapi import HTTPException
    from starlette.requests import Request

    from zigbeelens.api.auth import _extract_bearer_token

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (b"authorization", f"Bearer {VALID_TOKEN}".encode()),
            (b"authorization", f"Bearer {VALID_TOKEN}".encode()),
        ],
    }
    with pytest.raises(HTTPException) as exc_info:
        _extract_bearer_token(Request(scope))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == AUTH_DETAIL


def test_sse_requires_bearer_and_skips_work(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        original_dashboard = ctx.data.dashboard
        original_subscribe = ctx.broadcaster.subscribe
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard called"))
        ctx.broadcaster.subscribe = MagicMock(
            side_effect=AssertionError("subscribe called")
        )
        try:
            _assert_uniform_401(client.get("/api/events/stream"))
            _assert_uniform_401(client.get("/api/v1/events/stream"))
            _assert_uniform_401(
                client.get(f"/api/events/stream?access_token={VALID_TOKEN}")
            )
        finally:
            ctx.data.dashboard = original_dashboard
            ctx.broadcaster.subscribe = original_subscribe

        # Authenticated requests must pass the read dependency before stream creation.
        # Replace EventSourceResponse so TestClient does not drain the infinite generator.
        from fastapi.responses import JSONResponse

        import zigbeelens.main as main_mod

        monkeypatch.setattr(
            main_mod,
            "EventSourceResponse",
            lambda _gen: JSONResponse({"stream": "started"}),
        )
        ok = client.get("/api/events/stream", headers=_bearer())
        assert ok.status_code == 200
        assert ok.json() == {"stream": "started"}
        ok_v1 = client.get("/api/v1/events/stream", headers=_bearer())
        assert ok_v1.status_code == 200


def test_report_download_auth_order(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        created = client.post(
            "/api/reports",
            json={"format": "json", "redaction": {"profile": "standard"}},
            headers=_bearer(),
        )
        assert created.status_code == 200
        report_id = created.json()["id"]

        _assert_uniform_401(client.get(f"/api/reports/{report_id}/download"))
        _assert_uniform_401(
            client.get(
                f"/api/reports/{report_id}/download",
                headers={"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            )
        )
        _assert_uniform_401(
            client.get(f"/api/reports/missing/download?token={VALID_TOKEN}")
        )
        missing = client.get("/api/reports/missing/download", headers=_bearer())
        assert missing.status_code == 404

        ok = client.get(f"/api/reports/{report_id}/download", headers=_bearer())
        assert ok.status_code == 200
        assert "attachment" in ok.headers.get("content-disposition", "")
        v1 = client.get(f"/api/v1/reports/{report_id}/download", headers=_bearer())
        assert v1.status_code == 200
        assert v1.content == ok.content


def test_unauthorized_dashboard_does_no_composition(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard called"))
        _assert_uniform_401(client.get("/api/dashboard"))


def test_capabilities_advertise_auth_support_not_token_state(mock_client: TestClient):
    body = mock_client.get("/api/capabilities").json()
    caps = body["capabilities"]
    assert caps["bearer_authentication"] is True
    assert caps["browser_session_authentication"] is True
    assert caps["csrf_protection"] is True
    assert caps["exact_cors_allowlist"] is True
    assert caps["content_security_policy"] is True
    assert caps["frame_ancestor_allowlist"] is True
    assert caps["browser_origin_validation"] is True
    assert caps["home_assistant_ingress_identity"] is False


def test_openapi_protected_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        _assert_uniform_401(client.get("/openapi.json"))
        _assert_uniform_401(client.get("/docs"))
        schema = client.get("/openapi.json", headers=_bearer())
        assert schema.status_code == 200
        assert "paths" in schema.json()
        assert VALID_TOKEN not in schema.text
        assert client.get("/docs", headers=_bearer()).status_code == 200


def _operation_security(schema: dict, path: str, method: str) -> list | None:
    ops = schema["paths"][path][method]
    return ops.get("security")


def test_openapi_security_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        schema = client.get("/openapi.json", headers=_bearer()).json()
        schemes = schema["components"]["securitySchemes"]
        assert set(schemes) == {"BearerAuth", "BrowserSession", "CsrfToken"}
        assert schemes["BearerAuth"] == {"type": "http", "scheme": "bearer"}
        assert schemes["BrowserSession"]["in"] == "cookie"
        assert schemes["CsrfToken"]["in"] == "header"

        for path in (
            "/api/dashboard",
            "/api/events/stream",
            "/api/reports/{report_id}/download",
        ):
            security = _operation_security(schema, path, "get")
            assert {"BearerAuth": []} in security
            assert {"BrowserSession": []} in security
        mutation = _operation_security(schema, "/api/reports", "post")
        assert {"BearerAuth": []} in mutation
        assert {"BrowserSession": [], "CsrfToken": []} in mutation

        for path in (
            "/api/version",
            "/api/v1/version",
            "/healthz",
            "/api/auth/session",
            "/api/v1/auth/session",
        ):
            op = schema["paths"][path]["get"]
            assert not op.get("security"), path

        assert VALID_TOKEN not in client.get("/openapi.json", headers=_bearer()).text


def test_openapi_disabled_and_trusted_open_docs(tmp_path, monkeypatch):
    monkeypatch.delenv("ZIGBEELENS_OPENAPI_ENABLED", raising=False)
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404

    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200


def test_healthz_minimal_and_public(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert set(res.json()) == {"status"}
        detailed = client.get("/api/health")
        _assert_uniform_401(detailed)
        ok = client.get("/api/health", headers=_bearer())
        assert ok.status_code == 200
        assert "collector" in ok.json()


def test_public_root_fallback_is_minimal(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    monkeypatch.setattr("zigbeelens.main.mount_static_ui", lambda _app: False)
    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert res.json() == {
            "name": "ZigbeeLens Core",
            "version": res.json()["version"],
        }
        assert set(res.json()) == {"name", "version"}
        assert "data_mode" not in res.json()
        assert "docs" not in res.json()
        assert "security" not in res.json()
        assert "mock_mode" not in res.json()

    with _client(tmp_path, monkeypatch) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert set(res.json()) == {"name", "version"}
        assert client.get("/api/version").status_code == 200
        assert client.get("/api/v1/version").status_code == 200


def test_unauthorized_endpoints_do_zero_work(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter

    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        from zigbeelens.app import context as ctx_mod
        import zigbeelens.api.routes as routes_mod
        import zigbeelens.main as main_mod

        ctx = ctx_mod.get_context()
        counter = install_counter(ctx.repo)

        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard"))
        ctx.data.report_preview = MagicMock(side_effect=AssertionError("preview"))
        ctx.data.get_stored_report = MagicMock(side_effect=AssertionError("download"))
        monkeypatch.setattr(
            routes_mod,
            "generate_report",
            MagicMock(side_effect=AssertionError("create")),
        )
        monkeypatch.setattr(
            routes_mod,
            "get_topology_service",
            MagicMock(side_effect=AssertionError("capture")),
        )
        monkeypatch.setattr(
            routes_mod,
            "apply_ha_enrichment",
            MagicMock(side_effect=AssertionError("enrich")),
        )
        monkeypatch.setattr(
            routes_mod,
            "clear_ha_enrichment",
            MagicMock(side_effect=AssertionError("clear")),
        )
        monkeypatch.setattr(
            main_mod,
            "EventSourceResponse",
            MagicMock(side_effect=AssertionError("sse")),
        )

        before = counter.stats.copy()
        for call in (
            lambda: client.get("/api/dashboard"),
            lambda: client.get("/api/reports/preview"),
            lambda: client.post("/api/reports", json={"format": "json"}),
            lambda: client.get("/api/reports/missing/download"),
            lambda: client.post(
                "/api/topology/home/capture",
                json={"confirmed": True},
            ),
            lambda: client.post("/api/enrichment/homeassistant", json={}),
            lambda: client.delete("/api/enrichment/homeassistant"),
            lambda: client.get("/api/events/stream"),
        ):
            _assert_uniform_401(call())

        after = counter.stats
        assert after.execute_count == before.execute_count
        assert after.executemany_count == before.executemany_count
        assert after.commit_count == before.commit_count
        assert after.rollback_count == before.rollback_count


_MALFORMED_JSON_MUTATIONS = (
    "/api/reports",
    "/api/v1/reports",
    "/api/topology/home/capture",
    "/api/v1/topology/home/capture",
    "/api/enrichment/homeassistant",
    "/api/v1/enrichment/homeassistant",
)


def test_malformed_json_rejected_before_body_decode(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter
    from starlette.requests import Request

    import zigbeelens.api.auth as auth_mod
    import zigbeelens.api.routes as routes_mod

    body_reads = {"n": 0}
    original_body = Request.body

    async def counting_body(self):
        body_reads["n"] += 1
        return await original_body(self)

    monkeypatch.setattr(Request, "body", counting_body)
    compare_calls = {"n": 0}
    original_compare = auth_mod._token_matches

    def counting_compare(provided: str, expected: str) -> bool:
        compare_calls["n"] += 1
        return original_compare(provided, expected)

    monkeypatch.setattr(auth_mod, "_token_matches", counting_compare)

    with _client(
        tmp_path,
        monkeypatch,
        security=f"security:\n  api_token: {VALID_TOKEN}\n",
    ) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        counter = install_counter(ctx.repo)
        generate_report = MagicMock(side_effect=AssertionError("create"))
        get_topology = MagicMock(side_effect=AssertionError("capture"))
        apply_enrichment = MagicMock(side_effect=AssertionError("enrich"))
        monkeypatch.setattr(routes_mod, "generate_report", generate_report)
        monkeypatch.setattr(routes_mod, "get_topology_service", get_topology)
        monkeypatch.setattr(routes_mod, "apply_ha_enrichment", apply_enrichment)

        headers_json = {"Content-Type": "application/json"}
        unauthorized_headers = (
            {},
            {"Authorization": f"Bearer {OTHER_TOKEN}"},
            {"X-ZigbeeLens-Api-Key": VALID_TOKEN},
            {},  # query token below
        )

        before = counter.stats.copy()
        body_reads["n"] = 0
        for path in _MALFORMED_JSON_MUTATIONS:
            for headers in unauthorized_headers[:3]:
                res = client.post(
                    path,
                    content="{",
                    headers={**headers_json, **headers},
                )
                _assert_uniform_401(res)
            res = client.post(
                f"{path}?token={VALID_TOKEN}",
                content="{",
                headers=headers_json,
            )
            _assert_uniform_401(res)

        assert body_reads["n"] == 0
        assert generate_report.call_count == 0
        assert get_topology.call_count == 0
        assert apply_enrichment.call_count == 0
        after = counter.stats
        assert after.execute_count == before.execute_count
        assert after.commit_count == before.commit_count
        assert after.rollback_count == before.rollback_count

        # Correct bearer: auth succeeds, then FastAPI returns JSON validation error.
        compare_calls["n"] = 0
        body_reads["n"] = 0
        for path in _MALFORMED_JSON_MUTATIONS:
            res = client.post(
                path,
                content="{",
                headers={**headers_json, **_bearer()},
            )
            assert res.status_code == 422, path
            assert "json" in res.text.lower() or "decode" in res.text.lower()
        assert body_reads["n"] >= 1
        # One comparison per request (preflight); dependency reuses cached identity.
        assert compare_calls["n"] == len(_MALFORMED_JSON_MUTATIONS)
        assert generate_report.call_count == 0
        assert get_topology.call_count == 0
        assert apply_enrichment.call_count == 0


def test_malformed_json_trusted_open_keeps_validation(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        for path in _MALFORMED_JSON_MUTATIONS:
            res = client.post(
                path,
                content="{",
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 422, path

