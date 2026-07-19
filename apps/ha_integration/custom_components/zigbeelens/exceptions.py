"""ZigbeeLens integration exceptions."""

from __future__ import annotations


class ZigbeeLensError(Exception):
    """Base ZigbeeLens integration error."""


class ZigbeeLensApiError(ZigbeeLensError):
    """Unexpected API failure."""


class ZigbeeLensConnectionError(ZigbeeLensApiError):
    """Core is not reachable."""


class ZigbeeLensAuthError(ZigbeeLensApiError):
    """Core rejected the HACS bearer credential (HTTP 401 on a protected route)."""


class ZigbeeLensInvalidResponseError(ZigbeeLensApiError):
    """Response was not valid ZigbeeLens JSON."""
