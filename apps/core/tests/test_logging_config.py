"""Logging configuration tests."""

import logging

from zigbeelens.logging_config import configure_logging


def test_configure_logging_respects_env(monkeypatch):
    monkeypatch.setenv("ZIGBEELENS_LOG_LEVEL", "warning")
    configure_logging()
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("ZIGBEELENS_LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO
