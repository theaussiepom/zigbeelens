"""HACS Core origin validation agrees with Core grammar on shared vectors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zigbeelens.core_origin import InvalidCoreOrigin, canonicalize_core_origin

CORE_VECTORS = Path(__file__).resolve().parents[2] / "core" / "tests" / "fixtures" / "http_origin_vectors.json"
VECTORS = json.loads(CORE_VECTORS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS, ids=[c["input"][:40] for c in VECTORS])
def test_hacs_matches_shared_vectors(case: dict) -> None:
    raw = case["input"]
    if case.get("reject"):
        with pytest.raises(InvalidCoreOrigin) as exc_info:
            canonicalize_core_origin(raw)
        assert "pass" not in str(exc_info.value)
        assert "token=" not in str(exc_info.value)
    else:
        assert canonicalize_core_origin(raw) == case["canonical"]


def test_normalize_rejects_userinfo_and_path():
    from zigbeelens.config_flow import _normalize_core_url

    with pytest.raises(ValueError):
        _normalize_core_url("https://user:secret@host.example")
    with pytest.raises(ValueError):
        _normalize_core_url("https://host.example/api")
