"""Secret-free security posture helpers."""

from __future__ import annotations

import logging

from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import (
    SecurityMode,
    bearer_auth_enabled,
    is_loopback_bind,
    trusted_local_open,
)
from zigbeelens.schemas import SecurityConfigStatus

logger = logging.getLogger(__name__)


def build_security_config_status(config: AppConfig) -> SecurityConfigStatus:
    token_configured = config.security.api_token is not None
    bearer_enabled = bearer_auth_enabled(config)
    return SecurityConfigStatus(
        mode=config.security.mode,
        loopback_bind=is_loopback_bind(config.server.host),
        api_token_configured=token_configured,
        session_secret_configured=config.security.session_secret is not None,
        bearer_auth_enabled=bearer_enabled,
        read_routes_require_bearer=bearer_enabled,
        mutation_routes_require_bearer=bearer_enabled,
        ingress_identity_enforced=False,
        trusted_local_open=trusted_local_open(config),
        legacy_mutation_guard_enabled=False,
    )


def log_security_posture(config: AppConfig) -> None:
    """Emit deterministic, secret-free startup security posture logs."""
    status = build_security_config_status(config)
    logger.info(
        "Security posture: mode=%s loopback_bind=%s api_token_configured=%s "
        "session_secret_configured=%s bearer_auth_enabled=%s trusted_local_open=%s "
        "ingress_identity_enforced=%s",
        status.mode.value,
        status.loopback_bind,
        status.api_token_configured,
        status.session_secret_configured,
        status.bearer_auth_enabled,
        status.trusted_local_open,
        status.ingress_identity_enforced,
    )

    if status.trusted_local_open:
        logger.info(
            "API access is trusted-open: protected read routes, mutations, SSE, and "
            "report downloads are open because security.mode=local and no API token "
            "is configured."
        )
        if not status.loopback_bind:
            logger.warning(
                "Core is bound to a non-loopback address (%s) with security.mode=local "
                "and no API token configured. All API routes are open; restrict network "
                "access or configure an API token for bearer authentication.",
                config.server.host,
            )
        return

    if status.mode is SecurityMode.local and status.bearer_auth_enabled:
        logger.info(
            "Bearer authentication is enabled: protected reads, mutations, SSE, and "
            "report downloads require Authorization: Bearer."
        )
        return

    if status.mode is SecurityMode.authenticated:
        logger.info(
            "security.mode=authenticated: protected reads, mutations, SSE, and "
            "report downloads require Authorization: Bearer."
        )
        return

    if status.mode is SecurityMode.home_assistant_ingress:
        logger.warning(
            "security.mode=home_assistant_ingress: temporary bearer authentication "
            "fallback is active; Home Assistant ingress identity validation is not "
            "active. Do not treat arbitrary reverse-proxy headers as authenticated."
        )
