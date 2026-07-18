"""Minimal Docker HEALTHCHECK probe — no AppConfig or secret loading."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

DEFAULT_PORT = 8377


def resolve_healthcheck_port(environ: dict[str, str] | None = None) -> int:
    """Return the effective healthcheck port from ZIGBEELENS_PORT or 8377."""
    env = os.environ if environ is None else environ
    raw = env.get("ZIGBEELENS_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ZIGBEELENS_PORT must be an integer") from exc
    if not (1 <= port <= 65535):
        raise ValueError("ZIGBEELENS_PORT must be between 1 and 65535")
    return port


def healthcheck_url(environ: dict[str, str] | None = None) -> str:
    port = resolve_healthcheck_port(environ)
    return f"http://127.0.0.1:{port}/api/health"


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    try:
        url = healthcheck_url()
        urllib.request.urlopen(url, timeout=5)  # noqa: S310 — loopback health probe only
    except (ValueError, OSError, urllib.error.URLError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
