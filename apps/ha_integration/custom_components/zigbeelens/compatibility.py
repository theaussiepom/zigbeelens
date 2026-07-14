"""Core version and decision-contract compatibility helpers for the HACS companion.

Phase 5E-1 establishes the soft gate for shared decisions. Older Core builds that
omit decision capability flags must not cause hard failures — companion decision
display (5E-2) simply stays unavailable.
"""

from __future__ import annotations

from typing import Any

# Must match apps/core/.../api/summary.py DECISION_CONTRACT_VERSION.
DECISION_CONTRACT_VERSION = 1

# Absolute minimum Core this integration expects for basic health/dashboard use.
MIN_CORE_VERSION = (0, 1, 0)


def parse_core_version(version: str | None) -> tuple[int, ...] | None:
    """Parse a dotted Core version into an int tuple; ignore pre-release suffixes."""
    if not version or not isinstance(version, str):
        return None
    cleaned = version.strip().split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for piece in cleaned.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) if parts else None


def core_version_compatible(version: str | None, *, minimum: tuple[int, ...] = MIN_CORE_VERSION) -> bool:
    """Return True when version is missing (unknown) or at/above minimum."""
    parsed = parse_core_version(version)
    if parsed is None:
        return True
    return parsed >= minimum


def decision_contract_version(capabilities: dict[str, Any] | None) -> int:
    if not isinstance(capabilities, dict):
        return 0
    raw = capabilities.get("decision_contract_version")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def supports_companion_decisions(capabilities: dict[str, Any] | None) -> bool:
    """Soft gate: True only when Core advertises the companion decision contract."""
    if not isinstance(capabilities, dict):
        return False
    if decision_contract_version(capabilities) < DECISION_CONTRACT_VERSION:
        return False
    caps = capabilities.get("capabilities")
    if not isinstance(caps, dict):
        return False
    return caps.get("companion_decision_summary") is True and caps.get("shared_decisions") is True
