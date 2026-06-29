"""Tracer config + global state.

Spec: specs/domains/03-tracing.md
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TracerConfig:
    endpoint: str = field(default_factory=lambda: os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""))
    service_name: str = field(default_factory=lambda: os.environ.get("OTEL_SERVICE_NAME", "ai-agent"))
    service_version: str = field(default_factory=lambda: os.environ.get("OTEL_SERVICE_VERSION", "0.1.0"))
    environment: str = field(default_factory=lambda: os.environ.get("OTEL_ENV", "development"))
    sample_rate: float = field(default_factory=lambda: float(os.environ.get("AI_OBS_SAMPLE_RATE", "0.1")))
    sample_errors: bool = True
    redact_keys: list[str] = field(default_factory=lambda: ["password", "api_key", "token", "secret", "ssn", "cpf", "email"])
    max_payload_bytes: int = 5 * 1024 * 1024
    pii_mode: str = field(default_factory=lambda: os.environ.get("PII_MODE", "redact"))


_state_lock = threading.Lock()
_tracer: "Any | None" = None


def get_tracer() -> "Any":
    from .core import Tracer
    global _tracer
    with _state_lock:
        if _tracer is None:
            _tracer = Tracer(TracerConfig())
        return _tracer


def reset_tracer() -> None:
    """Reset for tests. Idempotent."""
    global _tracer
    with _state_lock:
        if _tracer is not None:
            _tracer.shutdown()
        _tracer = None
