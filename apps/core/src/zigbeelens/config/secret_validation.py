"""Shared secret-value predicates that never echo rejected input."""

from __future__ import annotations

import unicodedata


def contains_control_characters(value: str) -> bool:
    """Return True if *value* contains any Unicode control character (Cc)."""
    return any(unicodedata.category(ch) == "Cc" for ch in value)
