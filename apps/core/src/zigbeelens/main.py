from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from zigbeelens import __version__
from zigbeelens.api.auth import require_read_access
from zigbeelens.api.openapi_security import apply_openapi_security
from zigbeelens.api.routes import include_api_routers
from zigbeelens.app.context import bootstrap, get_context, reset_context
from zigbeelens.config import AppConfig, load_effective_config, resolve_config_path
from zigbeelens.logging_config import configure_logging
from zigbeelens.security.headers import (
    ExactCORSMiddleware,
    SecurityHeadersMiddleware,
    cors_middleware_kwargs,
)
from zigbeelens.security.ingress import HomeAssistantIngressBoundaryMiddleware
from zigbeelens.static import mount_static_ui

logger = logging.getLogger(__name__)

# Canonical first-party Uvicorn: never rewrite ASGI scope from forwarding headers.
_UVICORN_NO_PROXY_TRUST = {
    "proxy_headers": False,
    "forwarded_allow_ips": "",
}


class LazyASGIApp:
    """Import-safe ASGI entry that builds one concrete FastAPI app on first use.

    Importing ``zigbeelens.main`` performs no YAML or secret I/O. External runners
    (``uvicorn zigbeelens.main:app``) trigger a single ``create_app()`` at first
    ASGI startup. Production ``run_server`` bypasses this wrapper and passes a
    concrete app built from an already-resolved ``AppConfig``.
    """

    __slots__ = ("_lock", "_app")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._app: FastAPI | None = None

    def __repr__(self) -> str:
        # Never expose config paths or secret material.
        return "LazyASGIApp(resolved)" if self._app is not None else "LazyASGIApp()"

    def _ensure(self) -> FastAPI:
        app = self._app
        if app is not None:
            return app
        with self._lock:
            if self._app is None:
                self._app = create_app()
            return self._app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app: ASGIApp = self._ensure()
        await app(scope, receive, send)


def _openapi_enabled() -> bool:
    value = os.environ.get("ZIGBEELENS_OPENAPI_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _resolve_app_config(
    config_path: str | None,
    *,
    resolved_config: AppConfig | None,
) -> tuple[AppConfig, str | None]:
    """Resolve one immutable AppConfig for middleware and lifespan bootstrap."""
    if resolved_config is not None:
        path = config_path or os.environ.get("ZIGBEELENS_CONFIG")
        if path is None:
            path = str(resolve_config_path())
        return resolved_config, path
    path = config_path or os.environ.get("ZIGBEELENS_CONFIG")
    if not path:
        path = str(resolve_config_path())
    return load_effective_config(path), path


def create_app(
    config_path: str | None = None,
    *,
    resolved_config: AppConfig | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Resolves one effective AppConfig for CORS/CSP middleware and lifespan
    bootstrap. When *resolved_config* is provided (production launcher), secret
    files are not reread. TestClient and ASGI callers may omit it and load from
    *config_path* / ``ZIGBEELENS_CONFIG``.
    """
    cfg, resolved_config_path = _resolve_app_config(
        config_path, resolved_config=resolved_config
    )
    openapi_enabled = _openapi_enabled()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        reset_context()
        ctx = bootstrap(config=cfg, config_path=resolved_config_path)
        ctx.broadcaster.set_loop(asyncio.get_running_loop())
        app.state.ctx = ctx
        yield
        reset_context()

    app = FastAPI(
        title="ZigbeeLens",
        description="Read-only observability console for Zigbee2MQTT networks",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Last added = outermost. Security headers wrap ingress-boundary and CORS
    # so 401/OPTIONS responses also receive nosniff/referrer/permissions.
    app.add_middleware(ExactCORSMiddleware, **cors_middleware_kwargs(cfg))
    app.add_middleware(HomeAssistantIngressBoundaryMiddleware, config=cfg)
    app.add_middleware(SecurityHeadersMiddleware, config=cfg)

    @app.get("/healthz", include_in_schema=True, response_model=None)
    def healthz():
        """Minimal public readiness probe — no security or inventory details."""
        try:
            ctx = get_context()
        except RuntimeError:
            return JSONResponse({"status": "degraded"}, status_code=503)
        if not ctx.config_loaded or not ctx.db.ping():
            return JSONResponse({"status": "degraded"}, status_code=503)
        return {"status": "ok"}

    include_api_routers(app, prefix="/api")
    include_api_routers(app, prefix="/api/v1")

    # NOTE: SSE routes must be registered BEFORE mount_static_ui(), whose
    # catch-all `/{full_path:path}` would otherwise shadow them and 404 the
    # event stream (only reproducible when static UI is mounted, i.e. in the
    # built image), leaving the UI permanently "reconnecting".
    async def _events_stream() -> EventSourceResponse:
        async def generator():
            ctx = get_context()
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "type": "heartbeat",
                        "mock_mode": ctx.config.mode.mock,
                        "uptime_seconds": ctx.uptime_seconds(),
                    }
                ),
            }
            dash = ctx.data.dashboard()
            yield {
                "event": "dashboard_update",
                "data": json.dumps(
                    {"type": "dashboard_update", "dashboard": json.loads(dash.model_dump_json())}
                ),
            }

            async for item in ctx.broadcaster.subscribe():
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"]),
                }

        return EventSourceResponse(generator())

    @app.get("/api/events/stream", dependencies=[Depends(require_read_access)])
    async def events_stream() -> EventSourceResponse:
        return await _events_stream()

    @app.get("/api/v1/events/stream", dependencies=[Depends(require_read_access)])
    async def events_stream_v1() -> EventSourceResponse:
        return await _events_stream()

    if openapi_enabled:

        def custom_openapi() -> dict:
            if app.openapi_schema is not None:
                return app.openapi_schema
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            app.openapi_schema = apply_openapi_security(schema)
            return app.openapi_schema

        app.openapi = custom_openapi  # type: ignore[method-assign]

        @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_read_access)])
        def openapi_json() -> dict:
            return app.openapi()

        @app.get("/docs", include_in_schema=False, dependencies=[Depends(require_read_access)])
        def swagger_ui():
            return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title)

        @app.get("/redoc", include_in_schema=False, dependencies=[Depends(require_read_access)])
        def redoc_ui():
            return get_redoc_html(openapi_url="/openapi.json", title=app.title)

    if not mount_static_ui(app):

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            # Public product-shell identity only — no operational or auth state.
            return {"name": "ZigbeeLens Core", "version": __version__}

    return app


# External ASGI: ``uvicorn zigbeelens.main:app``. Lazily loads one AppConfig.
app = LazyASGIApp()


def run_server(
    config_path: str | Path | None = None,
    *,
    reload: bool = False,
) -> None:
    """Canonical first-party launcher: one effective AppConfig owns the bind."""
    import uvicorn

    path = Path(config_path) if config_path else resolve_config_path()
    os.environ["ZIGBEELENS_CONFIG"] = str(path)
    cfg = load_effective_config(path)

    logger.info(
        "Starting ZigbeeLens (host=%s port=%s reload=%s config=%s)",
        cfg.server.host,
        cfg.server.port,
        reload,
        path,
    )

    if reload:
        # Local development only. The listening host/port still come from the
        # effective AppConfig; the reloader may reread config for app code.
        uvicorn.run(
            "zigbeelens.main:app",
            host=cfg.server.host,
            port=cfg.server.port,
            reload=True,
            factory=False,
            **_UVICORN_NO_PROXY_TRUST,
        )
        return

    application = create_app(config_path=str(path), resolved_config=cfg)
    uvicorn.run(
        application,
        host=cfg.server.host,
        port=cfg.server.port,
        reload=False,
        **_UVICORN_NO_PROXY_TRUST,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="zigbeelens", description="ZigbeeLens Core")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable Uvicorn reload (local development only)",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="Path to config YAML (default: ZIGBEELENS_CONFIG or config/config.yaml)",
    )
    args = parser.parse_args(argv)
    run_server(config_path=args.config_path, reload=args.reload)


if __name__ == "__main__":
    main()
