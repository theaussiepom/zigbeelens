"""Compatibility helpers for Core version and decision contract."""

from __future__ import annotations

from zigbeelens.compatibility import (
    DECISION_CONTRACT_VERSION,
    core_version_compatible,
    decision_contract_version,
    parse_core_version,
    supports_companion_decisions,
)


def test_parse_core_version_handles_suffixes():
    assert parse_core_version("0.1.13") == (0, 1, 13)
    assert parse_core_version("0.1.13-edge") == (0, 1, 13)
    assert parse_core_version("1.2.3+build") == (1, 2, 3)
    assert parse_core_version("") is None
    assert parse_core_version(None) is None


def test_core_version_compatible_unknown_is_soft_ok():
    assert core_version_compatible(None) is True
    assert core_version_compatible("not-a-version") is True
    assert core_version_compatible("0.0.9") is False
    assert core_version_compatible("0.1.0") is True


def test_supports_companion_decisions_requires_contract():
    assert supports_companion_decisions(None) is False
    assert supports_companion_decisions({}) is False
    assert (
        supports_companion_decisions(
            {
                "decision_contract_version": DECISION_CONTRACT_VERSION,
                "capabilities": {"shared_decisions": True},
            }
        )
        is False
    )
    assert (
        supports_companion_decisions(
            {
                "decision_contract_version": DECISION_CONTRACT_VERSION,
                "capabilities": {
                    "shared_decisions": True,
                    "companion_decision_summary": True,
                },
            }
        )
        is True
    )
    assert decision_contract_version({"decision_contract_version": "1"}) == 1
    assert (
        supports_companion_decisions(
            {
                "decision_contract_version": 0,
                "capabilities": {
                    "shared_decisions": True,
                    "companion_decision_summary": True,
                },
            }
        )
        is False
    )
