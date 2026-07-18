"""Logging configuration for Core."""

from __future__ import annotations

import logging
import os

from zigbeelens.config.redaction import redact_request_target

_UVICORN_ACCESS_FILTER_ATTR = "_zigbeelens_uvicorn_access_redaction"


class UvicornAccessSecretRedactionFilter(logging.Filter):
    """Redact secret query values from recognised uvicorn.access records.

    Uvicorn's supported access ``LogRecord.args`` shape is::

        (client_addr, method, full_path, http_version, status_code)

    Unexpected shapes are suppressed so an unsanitized request target is never
    emitted. Recognised records are always kept after redaction.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        args = record.args
        if (
            not isinstance(args, tuple)
            or len(args) != 5
            or not isinstance(args[2], str)
        ):
            return False
        client_addr, method, full_path, http_version, status_code = args
        record.args = (
            client_addr,
            method,
            redact_request_target(full_path),
            http_version,
            status_code,
        )
        return True


def install_uvicorn_access_redaction_filter() -> None:
    """Attach the uvicorn.access redaction filter at most once."""
    access_logger = logging.getLogger("uvicorn.access")
    for existing in access_logger.filters:
        if getattr(existing, _UVICORN_ACCESS_FILTER_ATTR, False):
            return
    filt = UvicornAccessSecretRedactionFilter()
    setattr(filt, _UVICORN_ACCESS_FILTER_ATTR, True)
    access_logger.addFilter(filt)


def configure_logging() -> None:
    level_name = os.environ.get("ZIGBEELENS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s:%(name)s:%(message)s",
        force=True,
    )
    install_uvicorn_access_redaction_filter()
