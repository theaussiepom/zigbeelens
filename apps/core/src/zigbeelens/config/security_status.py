"""Secret-free security posture helpers."""

from __future__ import annotations

import logging

from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import SecurityMode, is_loopback_bind
from zigbeelens.schemas import SecurityConfigStatus

logger = logging.getLogger(__name__)


def build_security_config_status(config: AppConfig) -> SecurityConfigStatus:
    token_configured = config.security.api_token is not None
    return SecurityConfigStatus(
        mode=config.security.mode,
        loopback_bind=is_loopback_bind(config.server.host),
        api_token_configured=token_configured,
        session_secret_configured=config.security.session_secret is not None,
        legacy_mutation_guard_enabled=token_configured,
    )


def log_security_posture(config: AppConfig) -> None:
    """Emit deterministic, secret-free startup security posture logs."""
    status = build_security_config_status(config)
    logger.info(
        "Security posture: mode=%s loopback_bind=%s api_token_configured=%s "
        "session_secret_configured=%s mutation_guard=%s",
        status.mode.value,
        status.loopback_bind,
        status.api_token_configured,
        status.session_secret_configured,
        "enabled" if status.legacy_mutation_guard_enabled else "disabled",
    )
    logger.info(
        "Current API protection is limited to the optional mutation-route API-key guard; "
        "read routes and event streams remain open."
    )

    if (
        status.mode is SecurityMode.local
        and not status.loopback_bind
        and not status.api_token_configured
    ):
        logger.warning(
            "Core is bound to a non-loopback address (%s) with security.mode=local and no "
            "API token configured. Built-in route authentication is not enabled; restrict "
            "network access or configure an API token for mutating routes.",
            config.server.host,
        )

    if status.mode is SecurityMode.authenticated:
        logger.warning(
            "security.mode=authenticated configures credentials, but this build still "
            "enforces only the legacy mutation-route API-key guard. Read routes and event "
            "streams are not authenticated yet."
        )

    if status.mode is SecurityMode.home_assistant_ingress:
        logger.warning(
            "security.mode=home_assistant_ingress is configured, but Home Assistant ingress "
            "identity enforcement is not active in this build. Do not treat an arbitrary "
            "reverse proxy as authenticated ingress."
        )
