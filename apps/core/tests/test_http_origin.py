"""Canonical HTTP origin grammar and SecurityConfig origin lists."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from zigbeelens.config.http_origin import (
    InvalidHttpOrigin,
    canonicalize_http_origin,
    canonicalize_http_origins,
)
from zigbeelens.config.models import SecurityConfig

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "http_origin_vectors.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", VECTORS, ids=[c["input"][:40] for c in VECTORS])
def test_origin_vectors(case: dict) -> None:
    raw = case["input"]
    if case.get("reject"):
        with pytest.raises(InvalidHttpOrigin) as exc_info:
            canonicalize_http_origin(raw)
        # Never echo credential-bearing or rejected input.
        assert raw not in str(exc_info.value) or raw in {"null", ""}
        if "pass@" in raw or "token=" in raw:
            assert "pass" not in str(exc_info.value)
            assert "token" not in str(exc_info.value)
    else:
        assert canonicalize_http_origin(raw) == case["canonical"]


def test_deduplicates_canonical_origins() -> None:
    assert canonicalize_http_origins(
        ["HTTP://LOCALHOST:80/", "http://localhost", "https://a.example"]
    ) == ("http://localhost", "https://a.example")


def test_security_config_origin_lists() -> None:
    cfg = SecurityConfig(
        cors_allowed_origins=["HTTPS://UI.Example:443/"],
        frame_ancestor_origins=["https://ha.example", "https://ha.example"],
    )
    assert cfg.cors_allowed_origins == ("https://ui.example",)
    assert cfg.frame_ancestor_origins == ("https://ha.example",)


def test_security_config_rejects_unsafe_origins() -> None:
    with pytest.raises(ValidationError):
        SecurityConfig(cors_allowed_origins=["https://user:pass@evil.example"])
    with pytest.raises(ValidationError):
        SecurityConfig(frame_ancestor_origins=["https://*.example.com"])
