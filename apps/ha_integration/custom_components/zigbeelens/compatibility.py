"""Core version and decision-contract compatibility helpers for the HACS companion.

Track 5 requires exact decision contract v2. Missing, older, newer, or malformed
contracts disable companion decision display — never fall back to Health/Lens.
"""

from __future__ import annotations

from typing import Any

# Must match apps/core/.../api/summary.py DECISION_CONTRACT_VERSION.
DECISION_CONTRACT_VERSION = 2

# Exact versions this HACS package understands. Do not treat newer as compatible.
SUPPORTED_DECISION_CONTRACT_VERSIONS = frozenset({2})

REQUIRED_COMPANION_CAPABILITIES = frozenset(
    {
        "shared_decisions",
        "companion_decision_summary",
        "decision_only_diagnostic_payloads",
    }
)

REQUIRED_COMPANION_DECISION_SURFACES = frozenset(
    {
        "dashboard_decision_summary",
        "dashboard_investigation_priorities",
        "dashboard_data_coverage_warnings",
        "network_decision_badges",
        "device_decision_badges",
    }
)

# Absolute minimum Core this integration expects for basic operational use.
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
    """Strict parse of decision_contract_version. Unsupported/malformed → 0."""
    if not isinstance(capabilities, dict):
        return 0
    raw = capabilities.get("decision_contract_version")
    if type(raw) is int:
        return raw if raw >= 0 else 0
    if isinstance(raw, str):
        cleaned = raw.strip()
        if cleaned.isdigit():
            return int(cleaned)
        return 0
    return 0


def supports_companion_decisions(capabilities: dict[str, Any] | None) -> bool:
    """Soft gate: True only for an exact supported companion decision contract."""
    if not isinstance(capabilities, dict):
        return False
    if decision_contract_version(capabilities) not in SUPPORTED_DECISION_CONTRACT_VERSIONS:
        return False
    caps = capabilities.get("capabilities")
    if not isinstance(caps, dict):
        return False
    for name in REQUIRED_COMPANION_CAPABILITIES:
        if caps.get(name) is not True:
            return False
    if caps.get("legacy_health_lens_payloads") is True:
        return False
    surfaces = capabilities.get("decision_surfaces")
    if not isinstance(surfaces, dict):
        return False
    for surface in REQUIRED_COMPANION_DECISION_SURFACES:
        if surfaces.get(surface) is not True:
            return False
    return True


def dashboard_decision_payload_valid(dashboard: dict[str, Any] | None) -> bool:
    """True when Dashboard advertises the contract-v2 decision surfaces."""
    if not isinstance(dashboard, dict):
        return False
    summary = dashboard.get("decision_summary")
    if not isinstance(summary, dict):
        return False
    if not isinstance(summary.get("overall_status"), str):
        return False
    if not isinstance(summary.get("status_counts"), dict):
        return False
    return (
        isinstance(dashboard.get("investigation_priorities"), list)
        and isinstance(dashboard.get("data_coverage_warnings"), list)
    )
