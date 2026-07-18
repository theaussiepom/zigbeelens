"""Regression inventory: every /api and /api/v1 route has an explicit policy."""

from __future__ import annotations

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from zigbeelens.api.auth import require_mutation_access, require_read_access
from zigbeelens.main import create_app

PUBLIC_API_PATHS = {
    "/api/version",
    "/api/v1/version",
}

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# methods + suffix that must exist under both /api and /api/v1
REQUIRED_ALIASED_KEYS = {
    "GET /version",
    "GET /health",
    "GET /config/status",
    "GET /dashboard",
    "GET /events/stream",
    "GET /reports/{report_id}/download",
    "POST /reports",
    "DELETE /reports/{report_id}",
    "POST /topology/{network_id}/capture",
    "POST /enrichment/homeassistant",
    "DELETE /enrichment/homeassistant",
}


def _dependency_calls(dependant) -> set[object]:
    calls: set[object] = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            calls.add(dep.call)
        calls |= _dependency_calls(dep)
    return calls


def _route_calls(route: APIRoute) -> set[object]:
    return _dependency_calls(route.dependant)


def _depends_calls(depends_list) -> set[object]:
    calls: set[object] = set()
    for item in depends_list or ():
        dependency = getattr(item, "dependency", None)
        if dependency is not None:
            calls.add(dependency)
    return calls


def _iter_api_routes(app):
    """Yield (methods, full_path, dependency_calls) for API routes."""
    for entry in app.routes:
        if isinstance(entry, APIRoute):
            path = entry.path
            if path.startswith("/api/") or path.startswith("/api/v1/"):
                yield set(entry.methods or ()), path, _route_calls(entry)
            continue
        if type(entry).__name__ != "_IncludedRouter":
            continue
        prefix = entry.include_context.prefix or ""
        if not (prefix.startswith("/api")):
            continue
        router_calls = _depends_calls(entry.original_router.dependencies)
        include_calls = _depends_calls(entry.include_context.dependencies)
        base_calls = router_calls | include_calls
        for route in entry.original_router.routes:
            if not isinstance(route, APIRoute):
                continue
            full_path = prefix.rstrip("/") + route.path
            yield set(route.methods or ()), full_path, base_calls | _route_calls(route)


def test_api_routes_have_explicit_access_policy(mock_client: TestClient):
    classified: dict[str, str] = {}
    for methods, path, calls in _iter_api_routes(mock_client.app):
        has_read = require_read_access in calls
        has_mutation = require_mutation_access in calls

        if path in PUBLIC_API_PATHS:
            assert not has_read and not has_mutation, path
            policy = "public"
        elif has_mutation and not has_read:
            assert methods & MUTATION_METHODS, path
            policy = "mutation"
        elif has_read and not has_mutation:
            policy = "read"
        else:
            raise AssertionError(
                f"Route {methods} {path} missing explicit policy (deps={calls})"
            )

        key = f"{','.join(sorted(methods))} {path}"
        classified[key] = policy

    assert classified

    public_paths = {
        key.split(" ", 1)[1]
        for key, policy in classified.items()
        if policy == "public"
    }
    assert public_paths == PUBLIC_API_PATHS

    # methods + suffix -> { "/api": policy, "/api/v1": policy }
    by_alias_key: dict[str, dict[str, str]] = {}
    for key, policy in classified.items():
        methods_s, path = key.split(" ", 1)
        if path.startswith("/api/v1"):
            prefix = "/api/v1"
            suffix = path[len("/api/v1") :]
        elif path.startswith("/api"):
            prefix = "/api"
            suffix = path[len("/api") :]
        else:
            raise AssertionError(path)
        alias_key = f"{methods_s} {suffix}"
        by_alias_key.setdefault(alias_key, {})[prefix] = policy

    for alias_key, aliases in by_alias_key.items():
        assert set(aliases) == {"/api", "/api/v1"}, (
            f"alias set incomplete for {alias_key}: {sorted(aliases)}"
        )
        assert len(set(aliases.values())) == 1, (
            f"alias policy mismatch for {alias_key}: {aliases}"
        )

    for required in REQUIRED_ALIASED_KEYS:
        assert required in by_alias_key, f"missing required aliased route {required}"
        assert set(by_alias_key[required]) == {"/api", "/api/v1"}

    for key, policy in classified.items():
        methods, _path = key.split(" ", 1)
        method_set = set(methods.split(","))
        if method_set & MUTATION_METHODS:
            assert policy == "mutation", key


def test_healthz_is_public_and_static_outside_api_policy(mock_client: TestClient):
    healthz = [
        route
        for route in mock_client.app.routes
        if isinstance(route, APIRoute) and route.path == "/healthz"
    ]
    assert len(healthz) == 1
    assert require_read_access not in _route_calls(healthz[0])
    assert require_mutation_access not in _route_calls(healthz[0])
    assert mock_client.get("/healthz").status_code == 200


def test_openapi_routes_use_read_policy_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_OPENAPI_ENABLED", "true")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / "openapi.sqlite"}
networks: []
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
    with TestClient(create_app(str(cfg))) as client:
        for path in ("/openapi.json", "/docs", "/redoc"):
            routes = [
                route
                for route in client.app.routes
                if isinstance(route, APIRoute) and route.path == path
            ]
            assert routes, path
            assert require_read_access in _route_calls(routes[0]), path
