"""Static UI serving for bundled / add-on deployments."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def resolve_static_dir() -> Path | None:
    """Return the directory containing a built UI, if one is available."""
    candidates: list[Path] = []
    env_dir = os.environ.get("ZIGBEELENS_STATIC_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend(
        [
            Path("/app/static"),
            Path(__file__).resolve().parents[3] / "static",
        ]
    )
    for candidate in candidates:
        index = candidate / "index.html"
        if index.is_file():
            return candidate
    return None


def mount_static_ui(app: FastAPI) -> bool:
    """Serve the built React UI from Core when static assets are present."""
    static_dir = resolve_static_dir()
    if static_dir is None:
        return False

    index_path = static_dir / "index.html"
    assets_dir = static_dir / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api") or full_path in {"docs", "openapi.json", "redoc"}:
            raise HTTPException(status_code=404, detail="Not found")
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)

    return True
