from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_SENTRY_DSN = os.environ.get("SENTRY_DSN")
_SENTRY_ENV = os.environ.get("SENTRY_ENV", "development")
_SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", "ingest-api@unknown")

_sentry_initialized = False


def init_sentry() -> None:
    """Lazy-init Sentry. No-op if DSN not set. Idempotent."""
    global _sentry_initialized
    if _sentry_initialized or not _SENTRY_DSN:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=_SENTRY_ENV,
            release=_SENTRY_RELEASE,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            before_send=_scrub_pii,
        )
        _sentry_initialized = True
        logger.info("sentry initialized env=%s release=%s", _SENTRY_ENV, _SENTRY_RELEASE)
    except ImportError:
        logger.warning("sentry-sdk not installed; skipping Sentry init")


def _scrub_pii(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip PII from Sentry events. PRD §14 — Sentry must not log payloads."""
    sensitive_keys = {"password", "api_key", "token", "secret", "authorization", "cookie"}
    for key in list(event.get("extra", {}).keys()):
        if any(s in key.lower() for s in sensitive_keys):
            event["extra"][key] = "[REDACTED]"
    for key in list(event.get("request", {}).get("headers", {}).keys()):
        if key.lower() in sensitive_keys:
            event["request"]["headers"][key] = "[REDACTED]"
    return event


def capture_exception(error: Exception, **context: Any) -> None:
    if not _sentry_initialized:
        return
    import sentry_sdk
    with sentry_sdk.push_scope() as scope:
        for k, v in context.items():
            scope.set_extra(k, v)
        sentry_sdk.capture_exception(error)
