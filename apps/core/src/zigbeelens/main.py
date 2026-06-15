from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from zigbeelens import __version__
from zigbeelens.api.routes import router
from zigbeelens.app.context import bootstrap, get_context, reset_context
from zigbeelens.logging_config import configure_logging
from zigbeelens.static import mount_static_ui

logger = logging.getLogger(__name__)


def _openapi_enabled() -> bool:
    import os

    value = os.environ.get("ZIGBEELENS_OPENAPI_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def create_app(config_path: str | None = None) -> FastAPI:
    import os

    resolved_config_path = config_path or os.environ.get("ZIGBEELENS_CONFIG")
    openapi_enabled = _openapi_enabled()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        reset_context()
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


def main() -> None:
    import os

    import uvicorn

    from zigbeelens.config import load_config

    config_path = os.environ.get("ZIGBEELENS_CONFIG")
    cfg = load_config(config_path)
    uvicorn.run(
        "zigbeelens.main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=True,
        factory=False,
        app_dir="src",
    )


if __name__ == "__main__":
    main()
