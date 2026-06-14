"""Logging configuration for Core."""

from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    level_name = os.environ.get("ZIGBEELENS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s:%(name)s:%(message)s",
        force=True,
    )
