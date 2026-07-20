"""Async client for ZigbeeLens Core."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError
from aiohttp.client_exceptions import ClientConnectorError, ClientSSLError

from .api_token import optional_core_api_token
from .const import API_TIMEOUT
from .core_origin import InvalidCoreOrigin, canonicalize_core_origin
from .exceptions import (
    ZigbeeLensAuthError,
    ZigbeeLensConnectionError,
    ZigbeeLensInvalidResponseError,
)

_LOGGER = logging.getLogger(__name__)

_AUTH_REQUIRED = "Authentication required"
_INVALID_CORE_URL = "Invalid ZigbeeLens Core URL"
_INVALID_RESPONSE = "Invalid response from ZigbeeLens Core"
_NOT_ZIGBEELENS = "Endpoint is not ZigbeeLens Core"


class ZigbeeLensApiClient:
    """Read-only HTTP client for ZigbeeLens Core.

    When ``api_token`` is non-empty, protected requests send
    ``Authorization: Bearer <token>``. Public product discovery never
    includes Authorization.
    """

    __slots__ = ("_api_token", "_core_origin", "_session", "_verify_ssl")

    def __init__(
        self,
        session: ClientSession,
        core_url: str,
        *,
        verify_ssl: bool = False,
        api_token: str = "",
    ) -> None:
        self._session = session
        try:
            origin = canonicalize_core_origin(core_url)
        except InvalidCoreOrigin:
            raise ZigbeeLensInvalidResponseError(_INVALID_CORE_URL) from None
        try:
            token = optional_core_api_token(api_token)
        except ValueError:
            raise ZigbeeLensAuthError(_AUTH_REQUIRED) from None
        self._core_origin = origin
        self._verify_ssl = verify_ssl
        self._api_token = token

    @property
    def core_url(self) -> str:
        return self._core_origin

    @property
    def api_token_configured(self) -> bool:
        return bool(self._api_token)

    def __repr__(self) -> str:
        return (
            f"ZigbeeLensApiClient(core_url={self._core_origin!r}, "
            f"verify_ssl={self._verify_ssl!r}, "
            f"api_token_configured={self.api_token_configured!r})"
        )

    def api_url(self, path: str) -> str:
        """Join a fixed internal path onto the canonical origin (no urljoin authority swap)."""
        normalized = path.lstrip("/")
        if not normalized or normalized.startswith("//") or "://" in normalized:
            raise ZigbeeLensInvalidResponseError("Invalid ZigbeeLens API path")
        return f"{self._core_origin}/{normalized}"

    async def _request_json(self, path: str, *, protected: bool = True) -> dict[str, Any]:
        url = self.api_url(path)
        timeout = ClientTimeout(total=API_TIMEOUT)
        headers: dict[str, str] = {}
        if protected and self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        try:
            async with self._session.get(
                url,
                timeout=timeout,
                ssl=self._verify_ssl,
                headers=headers or None,
                allow_redirects=False,
            ) as response:
                status = response.status
                if 300 <= status < 400:
                    raise ZigbeeLensInvalidResponseError(_INVALID_RESPONSE) from None
                if status == 401:
                    if protected:
                        raise ZigbeeLensAuthError(_AUTH_REQUIRED) from None
                    raise ZigbeeLensInvalidResponseError(_INVALID_RESPONSE) from None
                if status >= 400:
                    raise ZigbeeLensInvalidResponseError(
                        f"ZigbeeLens Core returned HTTP {status}"
                    ) from None
                try:
                    payload = await response.json()
                except (ContentTypeError, ValueError):
                    raise ZigbeeLensInvalidResponseError("Invalid JSON from Core") from None
        except ZigbeeLensAuthError:
            raise
        except ZigbeeLensInvalidResponseError:
            raise
        except ClientSSLError:
            raise ZigbeeLensConnectionError("SSL error connecting to Core") from None
        except ClientConnectorError:
            raise ZigbeeLensConnectionError("Cannot connect to ZigbeeLens Core") from None
        except ClientError:
            raise ZigbeeLensConnectionError("Connection error talking to Core") from None
        except TimeoutError:
            raise ZigbeeLensConnectionError("Timed out connecting to Core") from None

        if not isinstance(payload, dict):
            raise ZigbeeLensInvalidResponseError("Expected JSON object from Core")
        return payload

    @staticmethod
    def _validate_health(payload: dict[str, Any]) -> None:
        for key in ("status", "version"):
            if key not in payload:
                raise ZigbeeLensInvalidResponseError("Health response missing required fields")

    @staticmethod
    def _validate_dashboard(payload: dict[str, Any]) -> None:
        # Contract-v2 dashboards are decision-led; keep validation factual/shape-light.
        if "generated_at" not in payload or "networks" not in payload:
            raise ZigbeeLensInvalidResponseError("Dashboard response missing required fields")

    async def async_get_health(self) -> dict[str, Any]:
        payload = await self._request_json("api/health", protected=True)
        self._validate_health(payload)
        return payload

    async def async_get_dashboard(self) -> dict[str, Any]:
        payload = await self._request_json("api/dashboard", protected=True)
        self._validate_dashboard(payload)
        return payload

    async def async_get_config_status(self) -> dict[str, Any]:
        payload = await self._request_json("api/config/status", protected=True)
        if "version" not in payload:
            raise ZigbeeLensInvalidResponseError("Config status missing version")
        return payload

    @staticmethod
    def _validate_capabilities(payload: dict[str, Any]) -> None:
        if payload.get("product") != "zigbeelens":
            raise ZigbeeLensInvalidResponseError("Capabilities response missing product")
        if "capabilities" not in payload or not isinstance(payload["capabilities"], dict):
            raise ZigbeeLensInvalidResponseError("Capabilities response missing capabilities")

    async def async_get_capabilities(self) -> dict[str, Any]:
        payload = await self._request_json("api/capabilities", protected=True)
        self._validate_capabilities(payload)
        return payload

    async def async_get_version(self) -> dict[str, Any]:
        """Public product probe — never sends Authorization."""
        return await self._request_json("api/version", protected=False)

    async def async_validate_core(self) -> dict[str, Any]:
        """Prove ZigbeeLens product identity publicly, then probe protected health."""
        version = await self.async_get_version()
        if version.get("name") != "zigbeelens-core":
            raise ZigbeeLensInvalidResponseError(_NOT_ZIGBEELENS)
        ver = version.get("version")
        if not isinstance(ver, str) or not ver.strip():
            raise ZigbeeLensInvalidResponseError(_INVALID_RESPONSE)
        return await self.async_get_health()
