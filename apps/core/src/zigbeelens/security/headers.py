"""Pure ASGI security-header and Content-Security-Policy middleware."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from zigbeelens.config.models import AppConfig

GENERAL_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), "
        "usb=(), serial=(), bluetooth=()"
    ),
}

# Bundled production UI — no unsafe-inline/eval for scripts.
_UI_CSP_BASE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("default-src", ("'self'",)),
    ("base-uri", ("'none'",)),
    ("object-src", ("'none'",)),
    ("script-src", ("'self'",)),
    (
        "style-src",
        ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com"),
    ),
    ("font-src", ("'self'", "https://fonts.gstatic.com", "data:")),
    ("img-src", ("'self'", "data:")),
    (
        "connect-src",
        ("'self'", "https://fonts.googleapis.com", "https://fonts.gstatic.com"),
    ),
    ("form-action", ("'self'",)),
    ("frame-src", ("'none'",)),
    ("manifest-src", ("'self'",)),
    ("worker-src", ("'self'",)),
)

# FastAPI Swagger UI / ReDoc CDN bootstrap (docs-only; never applied to UI).
_DOCS_CDN = "https://cdn.jsdelivr.net"
_DOCS_CSP_BASE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("default-src", ("'self'",)),
    ("base-uri", ("'none'",)),
    ("object-src", ("'none'",)),
    ("script-src", ("'self'", "'unsafe-inline'", _DOCS_CDN)),
    ("style-src", ("'self'", "'unsafe-inline'", _DOCS_CDN)),
    ("font-src", ("'self'", _DOCS_CDN, "data:")),
    ("img-src", ("'self'", "data:", _DOCS_CDN)),
    ("connect-src", ("'self'",)),
    ("form-action", ("'self'",)),
    ("frame-src", ("'none'",)),
)


def _frame_ancestors(frame_origins: Iterable[str]) -> tuple[str, ...]:
    # 'self' first, then exact configured external origins (already canonical).
    seen: set[str] = {"'self'"}
    values: list[str] = ["'self'"]
    for origin in frame_origins:
        if origin in seen:
            continue
        # Origins are canonical; reject injection characters defensively.
        if any(ch in origin for ch in ("\r", "\n", ";", ",")):
            continue
        seen.add(origin)
        values.append(origin)
    return tuple(values)


def build_csp(
    *,
    frame_ancestor_origins: tuple[str, ...],
    docs: bool = False,
) -> str:
    """Build a deterministic CSP string from structured directives."""
    base = _DOCS_CSP_BASE if docs else _UI_CSP_BASE
    directives: list[str] = []
    for name, sources in base:
        directives.append(f"{name} {' '.join(sources)}")
    ancestors = _frame_ancestors(frame_ancestor_origins)
    directives.append(f"frame-ancestors {' '.join(ancestors)}")
    return "; ".join(directives)


def _is_html_content_type(headers: MutableMapping[bytes, bytes] | MutableHeaders) -> bool:
    if isinstance(headers, MutableHeaders):
        ctype = headers.get("content-type", "")
    else:
        raw = headers.get(b"content-type", b"")
        ctype = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else str(raw)
    return "text/html" in ctype.lower()


def _is_docs_path(path: str) -> bool:
    return path in {"/docs", "/redoc"} or path.startswith("/docs/") or path.startswith(
        "/redoc/"
    )


class SecurityHeadersMiddleware:
    """ASGI middleware that sets browser-safety headers on response start only.

    Does not buffer bodies — SSE, downloads, and streaming remain intact.
    """

    def __init__(self, app: ASGIApp, *, config: AppConfig) -> None:
        self.app = app
        self._frame_origins = config.security.frame_ancestor_origins
        self._ui_csp = build_csp(frame_ancestor_origins=self._frame_origins, docs=False)
        self._docs_csp = build_csp(frame_ancestor_origins=self._frame_origins, docs=True)
        self._external_framing = bool(self._frame_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in GENERAL_HEADERS.items():
                    headers[key] = value
                # Never set HSTS from Core (no trusted proxy/scheme model yet).
                if "strict-transport-security" in headers:
                    del headers["strict-transport-security"]

                if _is_html_content_type(headers):
                    if _is_docs_path(path):
                        headers["Content-Security-Policy"] = self._docs_csp
                    else:
                        headers["Content-Security-Policy"] = self._ui_csp
                    if self._external_framing:
                        # CSP frame-ancestors is authoritative for external embeds.
                        if "x-frame-options" in headers:
                            del headers["x-frame-options"]
                    else:
                        headers["X-Frame-Options"] = "SAMEORIGIN"
                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)


def cors_middleware_kwargs(config: AppConfig) -> dict[str, Any]:
    """Keyword arguments for Starlette CORSMiddleware from AppConfig."""
    origins = list(config.security.cors_allowed_origins)
    return {
        "allow_origins": origins,
        "allow_credentials": bool(origins),
        "allow_methods": ["GET", "HEAD", "OPTIONS", "POST", "DELETE"],
        "allow_headers": [
            "Accept",
            "Authorization",
            "Content-Type",
            "Last-Event-ID",
            "X-ZigbeeLens-CSRF-Token",
        ],
        "expose_headers": ["Content-Disposition"],
        "max_age": 600,
    }
