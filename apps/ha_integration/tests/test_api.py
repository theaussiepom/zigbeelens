"""API client tests."""

from __future__ import annotations

import pytest
from aiohttp import ClientSession, web

from zigbeelens.api import ZigbeeLensApiClient
from zigbeelens.exceptions import ZigbeeLensConnectionError, ZigbeeLensInvalidResponseError


@pytest.fixture
async def core_app(aiohttp_server, sample_health, sample_dashboard, sample_config_status):
    async def health(_request):
        return web.json_response(sample_health)

    async def dashboard(_request):
        return web.json_response(sample_dashboard)

    async def config_status(_request):
        return web.json_response(sample_config_status)

    async def version(_request):
        return web.json_response({"version": "0.1.0", "name": "zigbeelens-core"})

    async def capabilities(_request):
        return web.json_response(
            {
                "product": "zigbeelens",
                "version": "0.1.0",
                "decision_contract_version": 1,
                "capabilities": {
                    "dashboard": True,
                    "shared_decisions": True,
                    "companion_decision_summary": True,
                },
                "decision_surfaces": {
                    "dashboard_investigation_priorities": True,
                    "dashboard_data_coverage_warnings": True,
                },
            }
        )

    app = web.Application()
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/dashboard", dashboard)
    app.router.add_get("/api/config/status", config_status)
    app.router.add_get("/api/version", version)
    app.router.add_get("/api/capabilities", capabilities)
    return await aiohttp_server(app)


@pytest.fixture
async def core_url(core_app):
    return str(core_app.make_url("/"))


@pytest.mark.asyncio
async def test_health_success(core_url, sample_health):
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, core_url)
        payload = await client.async_get_health()
    assert payload["status"] == sample_health["status"]


@pytest.mark.asyncio
async def test_dashboard_success(core_url):
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, core_url)
        payload = await client.async_get_dashboard()
    assert payload["overall_severity"] == "incident"


@pytest.mark.asyncio
async def test_url_join_handles_trailing_slash(core_url):
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, core_url + "/")
        assert client.api_url("api/health").endswith("/api/health")


@pytest.mark.asyncio
async def test_invalid_json(aiohttp_server):
    async def bad(_request):
        return web.Response(text="not-json", content_type="application/json")

    app = web.Application()
    app.router.add_get("/api/health", bad)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, str(server.make_url("/")))
        with pytest.raises(ZigbeeLensInvalidResponseError):
            await client.async_get_health()


@pytest.mark.asyncio
async def test_non_2xx(aiohttp_server):
    async def err(_request):
        raise web.HTTPBadRequest()

    app = web.Application()
    app.router.add_get("/api/health", err)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, str(server.make_url("/")))
        with pytest.raises(ZigbeeLensInvalidResponseError):
            await client.async_get_health()


@pytest.mark.asyncio
async def test_connection_error():
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, "http://127.0.0.1:1/")
        with pytest.raises(ZigbeeLensConnectionError):
            await client.async_get_health()


@pytest.mark.asyncio
async def test_capabilities_success(core_url):
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, core_url)
        payload = await client.async_get_capabilities()
    assert payload["product"] == "zigbeelens"
    assert payload["decision_contract_version"] == 1
    assert payload["capabilities"]["companion_decision_summary"] is True


@pytest.mark.asyncio
async def test_validate_core(core_url):
    async with ClientSession() as session:
        client = ZigbeeLensApiClient(session, core_url)
        health = await client.async_validate_core()
    assert health["status"] == "ok"
