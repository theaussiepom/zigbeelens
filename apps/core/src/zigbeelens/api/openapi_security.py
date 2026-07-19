"""Deterministic OpenAPI security scheme post-processing for Track 4C."""

from __future__ import annotations

from typing import Any

from zigbeelens.security.browser_sessions import SESSION_COOKIE_NAME

BEARER_SCHEME = "BearerAuth"
BROWSER_SESSION_SCHEME = "BrowserSession"
CSRF_SCHEME = "CsrfToken"
CSRF_HEADER_NAME = "X-ZigbeeLens-CSRF-Token"

PUBLIC_PATHS = {
    "/healthz",
    "/api/version",
    "/api/v1/version",
    "/api/auth/session",
    "/api/v1/auth/session",
}

BEARER_ONLY_POST = {
    "/api/auth/session",
    "/api/v1/auth/session",
}

MUTATION_METHODS = {"post", "put", "patch", "delete"}


def security_schemes() -> dict[str, dict[str, Any]]:
    return {
        BEARER_SCHEME: {"type": "http", "scheme": "bearer"},
        BROWSER_SESSION_SCHEME: {
            "type": "apiKey",
            "in": "cookie",
            "name": SESSION_COOKIE_NAME,
        },
        CSRF_SCHEME: {
            "type": "apiKey",
            "in": "header",
            "name": CSRF_HEADER_NAME,
        },
    }


def _is_read_security_path(path: str, method: str) -> bool:
    if path in PUBLIC_PATHS and method == "get":
        return False
    if path in BEARER_ONLY_POST and method == "post":
        return False
    return True


def apply_openapi_security(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite operation security to the Track 4C bearer/session/CSRF contract."""
    components = schema.setdefault("components", {})
    components["securitySchemes"] = security_schemes()

    paths = schema.get("paths") or {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            method_l = method.lower()
            if path in PUBLIC_PATHS and method_l == "get":
                operation.pop("security", None)
                continue
            if path in BEARER_ONLY_POST and method_l == "post":
                operation["security"] = [{BEARER_SCHEME: []}]
                continue
            if method_l in MUTATION_METHODS:
                operation["security"] = [
                    {BEARER_SCHEME: []},
                    {BROWSER_SESSION_SCHEME: [], CSRF_SCHEME: []},
                ]
                continue
            if _is_read_security_path(path, method_l):
                operation["security"] = [
                    {BEARER_SCHEME: []},
                    {BROWSER_SESSION_SCHEME: []},
                ]
            # Safe vendor note: Supervisor ingress may authorize; clients cannot
            # activate this by forging X-Remote-User-* headers themselves.
            if path.startswith("/api") and path not in PUBLIC_PATHS:
                operation["x-zigbeelens-home-assistant-ingress"] = True
    return schema
