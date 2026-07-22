#!/usr/bin/env bash
# Runtime SQLite 3.34.1 smoke for Phase 7A migration 013.
# Uses python:3.12-slim-bullseye (linked SQLite 3.34.1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${ZIGBEELENS_SQLITE_SMOKE_IMAGE:-python:3.12-slim-bullseye}"

docker run --rm \
  -v "${ROOT}:/src:ro" \
  -w /src/apps/core \
  "${IMAGE}" \
  bash -lc '
    set -euo pipefail
    python - <<PY
import sqlite3
print("sqlite3.sqlite_version="+sqlite3.sqlite_version)
assert sqlite3.sqlite_version == "3.34.1", sqlite3.sqlite_version
PY
    pip install -q --disable-pip-version-check \
      pytest pydantic pydantic-settings pyyaml fastapi uvicorn \
      sse-starlette paho-mqtt itsdangerous idna httpx
    PYTHONPATH=src python -m pytest -q tests/performance/test_sqlite_3_34_1_smoke.py -s
  '
