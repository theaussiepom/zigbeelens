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


def _safe_static_file(root: Path, full_path: str) -> Path | None:
    """Return a file under *root* or None if the path escapes the static tree."""
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def mount_static_ui(app: FastAPI) -> bool:
    """Serve the built React UI from Core when static assets are present."""
    static_dir = resolve_static_dir()
    if static_dir is None:
        return False

    root = static_dir.resolve()
    index_path = root / "index.html"
    assets_dir = root / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api") or full_path in {"docs", "openapi.json", "redoc"}:
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _safe_static_file(root, full_path)
        if candidate is not None:
            return FileResponse(candidate)
        # The UI is built with a relative base (`./`) so it works under Home
        # Assistant Ingress. On a deep-link refresh (e.g. /topology/home/graph)
        # the browser therefore requests assets relative to the page path
        # (/topology/home/assets/…). Serve such requests from the real static
        # tree instead of falling back to index.html, which would hand the
        # browser HTML where it expects a module script and blank the page.
        if "assets/" in full_path:
            asset_path = "assets/" + full_path.rsplit("assets/", 1)[1]
            candidate = _safe_static_file(root, asset_path)
            if candidate is not None:
                return FileResponse(candidate)
        basename = full_path.rsplit("/", 1)[-1]
        if "." in basename:
            candidate = _safe_static_file(root, basename)
            if candidate is not None:
                return FileResponse(candidate)
        return FileResponse(index_path)

    return True
