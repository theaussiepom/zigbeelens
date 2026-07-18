"""Secret-free security posture helpers."""

from __future__ import annotations

import logging

from zigbeelens.config.models import AppConfig
from zigbeelens.config.security_types import (
    SecurityMode,
    bearer_auth_enabled,
    browser_sessions_enabled,
    is_loopback_bind,
    trusted_local_open,
)
from zigbeelens.schemas import SecurityConfigStatus
from zigbeelens.security.browser_sessions import resolve_session_cookie_secure

logger = logging.getLogger(__name__)


def build_security_config_status(config: AppConfig) -> SecurityConfigStatus:
    token_configured = config.security.api_token is not None
    bearer_enabled = bearer_auth_enabled(config)
    sessions_enabled = browser_sessions_enabled(config)
    auth_required = bearer_enabled
    # Deprecated fields: bearer-only when sessions are not an alternative.
    bearer_only_required = auth_required and not sessions_enabled
    cors_count = len(config.security.cors_allowed_origins)
    frame_count = len(config.security.frame_ancestor_origins)
    return SecurityConfigStatus(
        mode=config.security.mode,
        loopback_bind=is_loopback_bind(config.server.host),
        api_token_configured=token_configured,
        session_secret_configured=config.security.session_secret is not None,
        bearer_auth_enabled=bearer_enabled,
        browser_session_enabled=sessions_enabled,
        csrf_protection_enabled=sessions_enabled,
        session_cookie_secure=resolve_session_cookie_secure(config),
        read_routes_require_authentication=auth_required,
        mutation_routes_require_authentication=auth_required,
        read_routes_require_bearer=bearer_only_required,
        mutation_routes_require_bearer=bearer_only_required,
        ingress_identity_enforced=False,
        trusted_local_open=trusted_local_open(config),
        legacy_mutation_guard_enabled=False,
        cors_allowed_origins_count=cors_count,
        credentialed_cors_enabled=cors_count > 0,
        frame_ancestor_origins_count=frame_count,
        external_framing_enabled=frame_count > 0,
        content_security_policy_enabled=True,
        session_origin_validation_enabled=sessions_enabled,
    )


def log_security_posture(config: AppConfig) -> None:
    """Emit deterministic, secret-free startup security posture logs."""
    status = build_security_config_status(config)
    logger.info(
        "Security posture: mode=%s loopback_bind=%s api_token_configured=%s "
        "session_secret_configured=%s bearer_auth_enabled=%s "
        "browser_session_enabled=%s csrf_protection_enabled=%s "
        "session_cookie_secure=%s session_ttl_seconds=%s trusted_local_open=%s "
        "ingress_identity_enforced=%s cors_allowed_origins_count=%s "
        "credentialed_cors_enabled=%s frame_ancestor_origins_count=%s "
        "external_framing_enabled=%s content_security_policy_enabled=%s "
        "session_origin_validation_enabled=%s",
        status.mode.value,
        status.loopback_bind,
        status.api_token_configured,
        status.session_secret_configured,
        status.bearer_auth_enabled,
        status.browser_session_enabled,
        status.csrf_protection_enabled,
        status.session_cookie_secure,
        config.security.session_ttl_seconds,
        status.trusted_local_open,
        status.ingress_identity_enforced,
        status.cors_allowed_origins_count,
        status.credentialed_cors_enabled,
        status.frame_ancestor_origins_count,
        status.external_framing_enabled,
        status.content_security_policy_enabled,
        status.session_origin_validation_enabled,
    )

    if status.session_secret_configured and not status.api_token_configured:
        logger.warning(
            "security.session_secret is configured without an API token; browser "
            "sessions remain disabled because no bearer bootstrap credential exists."
        )

    if (
        config.security.session_cookie_secure is False
        and not status.loopback_bind
    ):
        logger.warning(
            "session_cookie_secure=false while Core is bound to a non-loopback "
            "address (%s); browser session cookies may cross the network without "
            "the Secure attribute.",
            config.server.host,
        )

    if status.trusted_local_open:
        logger.info(
            "API access is trusted-open: protected read routes, mutations, SSE, and "
            "report downloads are open because security.mode=local and no API token "
            "is configured. No browser session is needed."
        )
        if not status.loopback_bind:
            logger.warning(
                "Core is bound to a non-loopback address (%s) with security.mode=local "
                "and no API token configured. All API routes are open; restrict network "
                "access or configure an API token for bearer authentication.",
                config.server.host,
            )
        return

    if status.external_framing_enabled:
        logger.info(
            "External framing is enabled for exact configured frame ancestors only "
            "(count=%s). Framing permission is not authentication.",
            status.frame_ancestor_origins_count,
        )

    if (
        status.browser_session_enabled
        and status.credentialed_cors_enabled
        and not status.loopback_bind
    ):
        has_http_cors = any(
            origin.startswith("http://")
            for origin in config.security.cors_allowed_origins
        )
        if has_http_cors:
            logger.warning(
                "Browser sessions are enabled with non-loopback bind and HTTP "
                "CORS origins (count=%s); cookie transport may be unsuitable "
                "without TLS. Origin values are not logged.",
                status.cors_allowed_origins_count,
            )

    if status.browser_session_enabled:
        logger.info(
            "Bearer and same-origin browser sessions are accepted for protected "
            "reads, SSE, and downloads. Cookie-authenticated mutations require an "
            "exact browser Origin and the CSRF header. "
            "session_cookie_secure=%s session_ttl_seconds=%s.",
            status.session_cookie_secure,
            config.security.session_ttl_seconds,
        )
    elif status.bearer_auth_enabled:
        logger.info(
            "Bearer authentication is enabled: protected reads, mutations, SSE, and "
            "report downloads require Authorization: Bearer. Browser sessions are "
            "not configured."
        )

    if status.mode is SecurityMode.authenticated and not status.browser_session_enabled:
        logger.info(
            "security.mode=authenticated: protected routes require Authorization: Bearer."
        )

    if status.mode is SecurityMode.home_assistant_ingress:
        logger.warning(
            "security.mode=home_assistant_ingress: temporary bearer/session "
            "authentication fallback may operate; Home Assistant ingress identity "
            "validation is not active. Do not treat arbitrary reverse-proxy headers "
            "as authenticated."
        )
