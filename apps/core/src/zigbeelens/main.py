from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from zigbeelens import __version__
from zigbeelens.api.auth import OptionalApiKeyMiddleware
from zigbeelens.api.routes import router
from zigbeelens.app.context import bootstrap, get_context, reset_context
from zigbeelens.config import AppConfig, load_effective_config, resolve_config_path
from zigbeelens.logging_config import configure_logging
from zigbeelens.static import mount_static_ui

logger = logging.getLogger(__name__)


def _openapi_enabled() -> bool:
    value = os.environ.get("ZIGBEELENS_OPENAPI_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def create_app(
    config_path: str | None = None,
    *,
    resolved_config: AppConfig | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    When *resolved_config* is provided (production launcher), lifespan bootstraps
    from that instance and does not reread secret files. TestClient and ASGI
    callers may omit it and load from *config_path* / ``ZIGBEELENS_CONFIG``.
    """
    resolved_config_path = config_path or os.environ.get("ZIGBEELENS_CONFIG")
    openapi_enabled = _openapi_enabled()
    preloaded = resolved_config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        reset_context()
        if preloaded is not None:
            ctx = bootstrap(config=preloaded, config_path=resolved_config_path)
        else:
            ctx = bootstrap(config_path=resolved_config_path)
        ctx.broadcaster.set_loop(asyncio.get_running_loop())
        app.state.ctx = ctx
        yield
        reset_context()

    app = FastAPI(
        title="ZigbeeLens",
        description="Read-only observability console for Zigbee2MQTT networks",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if openapi_enabled else None,
        redoc_url="/redoc" if openapi_enabled else None,
        openapi_url="/openapi.json" if openapi_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(OptionalApiKeyMiddleware)

    @app.middleware("http")
    async def allow_embedded_ui(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets"):
            response.headers["Content-Security-Policy"] = "frame-ancestors *"
        return response

    app.include_router(router, prefix="/api")
    app.include_router(router, prefix="/api/v1")

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

    @app.get("/api/events/stream")
    async def events_stream() -> EventSourceResponse:
        return await _events_stream()

    @app.get("/api/v1/events/stream")
    async def events_stream_v1() -> EventSourceResponse:
        return await _events_stream()

    if not mount_static_ui(app):

        @app.get("/")
        def root() -> dict[str, str]:
            ctx = get_context()
            payload = {
                "name": "ZigbeeLens Core",
                "version": __version__,
                "data_mode": "mock" if ctx.config.mode.mock else "live",
            }
            if openapi_enabled:
                payload["docs"] = "/docs"
            return payload

    return app


app = create_app()


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
        )
        return

    application = create_app(config_path=str(path), resolved_config=cfg)
    uvicorn.run(
        application,
        host=cfg.server.host,
        port=cfg.server.port,
        reload=False,
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
