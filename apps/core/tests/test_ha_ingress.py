"""Track 4G Home Assistant ingress peer trust and identity."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from zigbeelens.api.auth import AUTH_DETAIL, AuthIdentity
from zigbeelens.config.ingress_trust import (
    ADDON_SUPERVISOR_INGRESS_PEER,
    canonicalize_ingress_trusted_proxy,
    normalize_ha_user_id,
)
from zigbeelens.config.models import SecurityConfig, SecurityMode
from zigbeelens.main import create_app
from zigbeelens.security.ingress import HomeAssistantIngressIdentity

VALID_TOKEN = "c" * 32
VALID_USER_ID = "0123456789abcdef0123456789abcdef"
TRUSTED = ADDON_SUPERVISOR_INGRESS_PEER
NEAR_PEER = "172.30.32.1"
OTHER_PEER = "172.30.32.3"


def _write_config(path: Path, *, security: str) -> None:
    path.write_text(
        f"""
mode:
  mock: true
storage:
  path: {path.parent / "ingress.sqlite"}
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
{security}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _ingress_security(
    *,
    token: str | None = None,
    proxy_only: bool = True,
    peer: str = TRUSTED,
) -> str:
    lines = [
        "security:",
        "  mode: home_assistant_ingress",
        "  ingress_trusted_proxies:",
        f"    - {peer}",
        f"  ingress_proxy_only: {'true' if proxy_only else 'false'}",
    ]
    if token is not None:
        lines.insert(2, f"  api_token: {token}")
    return "\n".join(lines) + "\n"


def _client(
    tmp_path: Path,
    monkeypatch,
    *,
    security: str,
    peer: tuple[str, int] = (TRUSTED, 50000),
) -> TestClient:
    cfg = tmp_path / "config.yaml"
    _write_config(cfg, security=security)
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    return TestClient(create_app(str(cfg)), client=peer)


def _identity_headers(user_id: str = VALID_USER_ID) -> dict[str, str]:
    return {
        "X-Remote-User-Id": user_id,
        "X-Remote-User-Name": "admin",
        "X-Remote-User-Display-Name": "Admin User",
    }


def _bearer(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_uniform_401(res) -> None:
    assert res.status_code == 401
    assert res.json() == {"detail": AUTH_DETAIL}
    assert VALID_USER_ID not in res.text
    assert VALID_TOKEN not in res.text
    assert "X-Remote-User" not in res.text


def test_normalize_ha_user_id_accepts_exact_32_hex_only():
    assert normalize_ha_user_id(VALID_USER_ID) == VALID_USER_ID
    assert normalize_ha_user_id(VALID_USER_ID.upper()) == VALID_USER_ID
    assert normalize_ha_user_id("01234567-89ab-cdef-0123-456789abcdef") is None
    assert normalize_ha_user_id("{0123456789abcdef0123456789abcdef}") is None
    assert normalize_ha_user_id("") is None
    assert normalize_ha_user_id(" admin ") is None
    assert normalize_ha_user_id("not-a-uuid") is None
    assert normalize_ha_user_id("0123456789abcdef0123456789abcde") is None


def test_trusted_proxy_rejects_cidr_hostname_and_unspecified():
    with pytest.raises(Exception):
        canonicalize_ingress_trusted_proxy("172.30.32.0/24")
    with pytest.raises(Exception):
        canonicalize_ingress_trusted_proxy("supervisor.local")
    with pytest.raises(Exception):
        canonicalize_ingress_trusted_proxy("0.0.0.0")
    with pytest.raises(Exception):
        canonicalize_ingress_trusted_proxy("::")
    assert canonicalize_ingress_trusted_proxy("172.30.32.2") == "172.30.32.2"


def test_ingress_identity_repr_hides_user_id():
    identity = HomeAssistantIngressIdentity(user_id=VALID_USER_ID)
    assert VALID_USER_ID not in repr(identity)
    auth = AuthIdentity("home_assistant_ingress", ingress_user_id=VALID_USER_ID)
    assert VALID_USER_ID not in repr(auth)


def test_trusted_peer_valid_identity_authenticates(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        res = client.get("/api/dashboard", headers=_identity_headers())
        assert res.status_code == 200
        assert VALID_USER_ID not in res.text
        status = client.get("/api/auth/session", headers=_identity_headers()).json()
        assert status == {
            "authenticated": True,
            "auth_method": "home_assistant_ingress",
            "browser_session_enabled": False,
            "home_assistant_ingress_enabled": True,
            "expires_at": None,
            "csrf_token": None,
        }
        assert VALID_USER_ID not in str(status)


def test_trusted_peer_missing_identity_protects_routes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard"))
        _assert_uniform_401(client.get("/api/dashboard"))
        status = client.get("/api/auth/session").json()
        assert status["authenticated"] is False
        assert status["home_assistant_ingress_enabled"] is True
        assert status["csrf_token"] is None


@pytest.mark.parametrize(
    "user_id",
    [
        "",
        " short ",
        "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        "0123456789abcdef0123456789abcde!",
        VALID_USER_ID + "," + VALID_USER_ID,
    ],
)
def test_trusted_peer_malformed_identity_is_401(tmp_path, monkeypatch, user_id: str):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard"))
        res = client.get("/api/dashboard", headers={"X-Remote-User-Id": user_id})
        _assert_uniform_401(res)
        assert user_id.strip() not in res.text if user_id.strip() else True


def test_trusted_peer_duplicate_identity_header_is_401(tmp_path, monkeypatch):
    import asyncio

    from zigbeelens.config import load_config
    from zigbeelens.security.ingress import HomeAssistantIngressBoundaryMiddleware

    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, security=_ingress_security())
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg_path))
    cfg = load_config(cfg_path)
    mw = HomeAssistantIngressBoundaryMiddleware(
        lambda _s, _r, _d: None,  # type: ignore[misc]
        config=cfg,
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/dashboard",
        "headers": [
            (b"x-remote-user-id", VALID_USER_ID.encode("ascii")),
            (b"x-remote-user-id", ("a" * 32).encode("ascii")),
        ],
        "client": (TRUSTED, 50000),
        "query_string": b"",
        "server": ("test", 80),
        "scheme": "http",
        "asgi": {"version": "3.0"},
    }
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(mw(scope, receive, send))
    assert any(
        m.get("status") == 401 for m in sent if m["type"] == "http.response.start"
    )


def test_untrusted_peer_spoof_is_ignored(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(),
        peer=(NEAR_PEER, 50000),
    ) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard"))
        _assert_uniform_401(client.get("/api/dashboard", headers=_identity_headers()))


@pytest.mark.parametrize(
    "peer",
    [NEAR_PEER, OTHER_PEER, "10.0.0.5", "127.0.0.1", "::1"],
)
def test_near_and_loopback_peers_cannot_assert_identity(tmp_path, monkeypatch, peer: str):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(proxy_only=False),
        peer=(peer, 50000),
    ) as client:
        _assert_uniform_401(client.get("/api/dashboard", headers=_identity_headers()))


def test_forwarded_headers_do_not_change_trust(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(),
        peer=(NEAR_PEER, 50000),
    ) as client:
        headers = {
            **_identity_headers(),
            "X-Forwarded-For": TRUSTED,
            "X-Real-IP": TRUSTED,
            "Forwarded": f"for={TRUSTED}",
        }
        _assert_uniform_401(client.get("/api/dashboard", headers=headers))


def test_bearer_precedence_over_ingress(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN),
        peer=(TRUSTED, 50000),
    ) as client:
        res = client.get(
            "/api/auth/session",
            headers={**_identity_headers(), **_bearer()},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["authenticated"] is True
        assert body["auth_method"] == "bearer"


def test_bearer_precedes_malformed_and_duplicate_ingress_identity(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN),
        peer=(TRUSTED, 50000),
    ) as client:
        assert (
            client.get(
                "/api/dashboard",
                headers={
                    **_bearer(),
                    "X-Remote-User-Id": "not-a-valid-user-id!!!!!!!!!!!!!",
                },
            ).status_code
            == 200
        )
        # Duplicate identity headers: bearer still wins (middleware never parses them).
        from zigbeelens.config import load_config
        from zigbeelens.security.ingress import HomeAssistantIngressBoundaryMiddleware
        import asyncio

        cfg = load_config(tmp_path / "config.yaml")
        seen: list[str] = []

        async def inner(scope, receive, send):
            seen.append("ok")
            body = b'{"ok":true}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        mw = HomeAssistantIngressBoundaryMiddleware(inner, config=cfg)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard",
            "headers": [
                (b"authorization", f"Bearer {VALID_TOKEN}".encode("ascii")),
                (b"x-remote-user-id", VALID_USER_ID.encode("ascii")),
                (b"x-remote-user-id", ("a" * 32).encode("ascii")),
            ],
            "client": (TRUSTED, 50000),
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
            "asgi": {"version": "3.0"},
        }
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(mw(scope, receive, send))
        assert seen == ["ok"]
        assert any(
            m.get("status") == 200 for m in sent if m["type"] == "http.response.start"
        )


def test_wrong_or_malformed_bearer_does_not_fall_back_to_ingress(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN),
    ) as client:
        for auth in (
            f"Bearer {'e' * 32}",
            "Bearer not-a-valid-token-shape!!!!!!!!!!!!",
        ):
            res = client.get(
                "/api/dashboard",
                headers={**_identity_headers(), "Authorization": auth},
            )
            _assert_uniform_401(res)


def test_proxy_only_denies_untrusted_static(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(proxy_only=True),
        peer=(NEAR_PEER, 50000),
    ) as client:
        _assert_uniform_401(client.get("/"))
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/version").status_code == 200
        assert client.get("/api/auth/session").status_code == 200


def test_proxy_only_allows_valid_bearer_api_not_static(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN, proxy_only=True),
        peer=(NEAR_PEER, 50000),
    ) as client:
        assert client.get("/api/dashboard", headers=_bearer()).status_code == 200
        _assert_uniform_401(client.get("/api/dashboard", headers=_identity_headers()))
        _assert_uniform_401(client.get("/", headers=_bearer()))
        _assert_uniform_401(client.get("/assets/app.js", headers=_bearer()))
        _assert_uniform_401(client.get("/topology/home", headers=_bearer()))
        _assert_uniform_401(client.get("/api-malicious", headers=_bearer()))
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/version").status_code == 200
        assert client.get("/api/auth/session").status_code == 200


def test_ingress_mutation_without_csrf(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        res = client.post(
            "/api/reports",
            json={"format": "json"},
            headers=_identity_headers(),
        )
        assert res.status_code == 200
        assert VALID_USER_ID not in res.text


def test_ingress_mutation_malformed_body_after_auth(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        res = client.post(
            "/api/reports",
            content=b"{not-json",
            headers={**_identity_headers(), "Content-Type": "application/json"},
        )
        assert res.status_code == 422


def test_unauthenticated_malformed_mutation_is_401_before_body(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(),
        peer=(NEAR_PEER, 50000),
    ) as client:
        res = client.post(
            "/api/reports",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
        _assert_uniform_401(res)


def test_ingress_sse_requires_identity_before_work(tmp_path, monkeypatch):
    from fastapi.responses import JSONResponse

    import zigbeelens.main as main_mod

    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
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
        finally:
            ctx.data.dashboard = original_dashboard
            ctx.broadcaster.subscribe = original_subscribe

        monkeypatch.setattr(
            main_mod,
            "EventSourceResponse",
            lambda _gen: JSONResponse({"stream": "started"}),
        )
        ok = client.get("/api/events/stream", headers=_identity_headers())
        assert ok.status_code == 200
        assert ok.json() == {"stream": "started"}
        assert (
            client.get("/api/v1/events/stream", headers=_identity_headers()).status_code
            == 200
        )


def test_ingress_report_download(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as client:
        created = client.post(
            "/api/reports",
            json={"format": "json"},
            headers=_identity_headers(),
        ).json()
        report_id = created["id"]
        dl = client.get(
            f"/api/reports/{report_id}/download",
            headers=_identity_headers(),
        )
        assert dl.status_code == 200
        assert VALID_USER_ID not in dl.text
        assert VALID_USER_ID not in (dl.headers.get("content-disposition") or "")

        missing = client.get(
            "/api/reports/does-not-exist/download",
            headers=_identity_headers(),
        )
        assert missing.status_code == 404
        assert VALID_USER_ID not in missing.text

        _assert_uniform_401(client.get(f"/api/reports/{report_id}/download"))


def test_untrusted_download_spoof_401(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, security=_ingress_security()) as trusted:
        created = trusted.post(
            "/api/reports",
            json={"format": "json"},
            headers=_identity_headers(),
        ).json()
        report_id = created["id"]
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(),
        peer=(NEAR_PEER, 50000),
    ) as untrusted:
        _assert_uniform_401(
            untrusted.get(
                f"/api/reports/{report_id}/download",
                headers=_identity_headers(),
            )
        )
        _assert_uniform_401(
            untrusted.get("/api/reports/missing/download", headers=_identity_headers())
        )


def test_local_mode_ignores_ingress_headers(tmp_path, monkeypatch):
    security = "security:\n  mode: local\n"
    with _client(
        tmp_path,
        monkeypatch,
        security=security,
        peer=(TRUSTED, 50000),
    ) as client:
        # trusted-local open: dashboard works without identity
        assert client.get("/api/dashboard").status_code == 200
        # spoofed headers must not change auth method
        status = client.get("/api/auth/session", headers=_identity_headers()).json()
        assert status["auth_method"] == "trusted_local"
        assert status["home_assistant_ingress_enabled"] is False


def test_openapi_has_ingress_extension_not_remote_user_scheme(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN, proxy_only=False),
        peer=("127.0.0.1", 50000),
    ) as client:
        schema = client.get("/openapi.json", headers=_bearer()).json()
        text = str(schema)
        assert "X-Remote-User-Id" not in text
        assert "x-remote-user-id" not in text.lower()
        schemes = schema.get("components", {}).get("securitySchemes", {})
        assert "BearerAuth" in schemes or any("bearer" in str(v).lower() for v in schemes.values())
        dashboard = schema["paths"]["/api/dashboard"]["get"]
        assert dashboard.get("x-zigbeelens-home-assistant-ingress") is True


def test_config_status_ingress_fields(tmp_path, monkeypatch):
    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(token=VALID_TOKEN),
    ) as client:
        status = client.get(
            "/api/config/status",
            headers=_identity_headers(),
        ).json()["security"]
        assert status["ingress_identity_enforced"] is True
        assert status["ingress_trusted_proxy_count"] == 1
        assert status["ingress_proxy_only"] is True
        assert status["ingress_bearer_fallback_enabled"] is True
        assert status["trusted_local_open"] is False
        assert status["read_routes_require_authentication"] is True
        assert status["read_routes_require_bearer"] is False
        assert TRUSTED not in str(status)
        assert VALID_USER_ID not in str(status)


def test_zero_sql_for_untrusted_spoof(tmp_path, monkeypatch):
    from performance.query_instrumentation import install_counter

    with _client(
        tmp_path,
        monkeypatch,
        security=_ingress_security(),
        peer=(NEAR_PEER, 50000),
    ) as client:
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        counter = install_counter(ctx.repo)
        before = counter.stats.copy()
        _assert_uniform_401(client.get("/api/dashboard", headers=_identity_headers()))
        delta = counter.stats.delta(before)
        assert delta.execute_count == 0
        assert delta.commit_count == 0
        assert delta.rollback_count == 0


def test_security_config_rejects_duplicate_proxies():
    with pytest.raises(Exception):
        SecurityConfig(
            mode=SecurityMode.home_assistant_ingress,
            ingress_trusted_proxies=["172.30.32.2", "172.30.32.2"],
        )


def test_trusted_peer_without_identity_blocks_session_fallback(tmp_path, monkeypatch):
    """Cookie must not rescue a trusted ingress peer that lacks X-Remote-User-Id."""
    from performance.query_instrumentation import install_counter

    session_secret = "s" * 32
    security = (
        "security:\n"
        "  mode: home_assistant_ingress\n"
        f"  api_token: {VALID_TOKEN}\n"
        f"  session_secret: {session_secret}\n"
        "  ingress_trusted_proxies:\n"
        f"    - {TRUSTED}\n"
        "  ingress_proxy_only: false\n"
    )
    # Bootstrap session from an untrusted peer (generic fallback allowed).
    with _client(
        tmp_path,
        monkeypatch,
        security=security,
        peer=(NEAR_PEER, 50000),
    ) as untrusted:
        login = untrusted.post("/api/auth/session", headers=_bearer())
        assert login.status_code == 200
        assert untrusted.get("/api/dashboard").status_code == 200
        cookies = untrusted.cookies

    with _client(
        tmp_path,
        monkeypatch,
        security=security,
        peer=(TRUSTED, 50000),
    ) as trusted:
        trusted.cookies.update(cookies)
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        ctx.data.dashboard = MagicMock(side_effect=AssertionError("dashboard"))
        counter = install_counter(ctx.repo)
        before = counter.stats.copy()
        status = trusted.get("/api/auth/session").json()
        assert status["authenticated"] is False
        assert status["auth_method"] is None
        assert status["home_assistant_ingress_enabled"] is True
        _assert_uniform_401(trusted.get("/api/dashboard"))
        delta = counter.stats.delta(before)
        assert delta.execute_count == 0


def test_untrusted_peer_may_use_session_when_not_proxy_only(tmp_path, monkeypatch):
    session_secret = "s" * 32
    security = (
        "security:\n"
        "  mode: home_assistant_ingress\n"
        f"  api_token: {VALID_TOKEN}\n"
        f"  session_secret: {session_secret}\n"
        "  ingress_trusted_proxies:\n"
        f"    - {TRUSTED}\n"
        "  ingress_proxy_only: false\n"
    )
    with _client(
        tmp_path,
        monkeypatch,
        security=security,
        peer=(NEAR_PEER, 50000),
    ) as client:
        assert client.post("/api/auth/session", headers=_bearer()).status_code == 200
        assert client.get("/api/dashboard").status_code == 200


def test_ingress_cors_wraps_boundary_401(tmp_path, monkeypatch):
    allowed = "https://ha.example"
    security = (
        "security:\n"
        "  mode: home_assistant_ingress\n"
        f"  api_token: {VALID_TOKEN}\n"
        "  ingress_trusted_proxies:\n"
        f"    - {TRUSTED}\n"
        "  ingress_proxy_only: true\n"
        "  cors_allowed_origins:\n"
        f"    - {allowed}\n"
    )
    with _client(
        tmp_path,
        monkeypatch,
        security=security,
        peer=(NEAR_PEER, 50000),
    ) as client:
        from performance.query_instrumentation import install_counter
        from zigbeelens.app import context as ctx_mod

        ctx = ctx_mod.get_context()
        counter = install_counter(ctx.repo)
        before = counter.stats.copy()
        preflight = client.options(
            "/api/dashboard",
            headers={
                "Origin": allowed,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code in {200, 204}
        assert preflight.headers.get("access-control-allow-origin") == allowed
        assert preflight.headers.get("access-control-allow-credentials") == "true"
        assert "nosniff" in (preflight.headers.get("x-content-type-options") or "").lower()
        delta = counter.stats.delta(before)
        assert delta.execute_count == 0

        denied = client.get(
            "/api/dashboard",
            headers={"Origin": allowed, **_identity_headers()},
        )
        _assert_uniform_401(denied)
        assert denied.headers.get("access-control-allow-origin") == allowed
        assert denied.headers.get("access-control-allow-credentials") == "true"
        assert "origin" in (denied.headers.get("vary") or "").lower()

        other = client.get(
            "/api/dashboard",
            headers={"Origin": "https://evil.example", **_identity_headers()},
        )
        _assert_uniform_401(other)
        assert other.headers.get("access-control-allow-origin") is None
        assert other.headers.get("access-control-allow-credentials") is None


def test_path_allows_direct_bearer_is_exact():
    from zigbeelens.security.ingress import path_allows_direct_bearer

    assert path_allows_direct_bearer("/api/dashboard") is True
    assert path_allows_direct_bearer("/api/v1/dashboard") is True
    assert path_allows_direct_bearer("/api") is True
    assert path_allows_direct_bearer("/openapi.json") is True
    assert path_allows_direct_bearer("/api-malicious") is False
    assert path_allows_direct_bearer("/") is False
    assert path_allows_direct_bearer("/topology/home") is False
