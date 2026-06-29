from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_ENABLED = bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def init_tracing(app):
    """Wire OpenTelemetry if endpoint is configured. No-op otherwise."""
    if not _ENABLED:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; tracing disabled")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("opentelemetry packages not installed; tracing disabled")
        return

    resource = Resource.create({
        "service.name": os.environ.get("OTEL_SERVICE_NAME", "ingest-api"),
        "service.version": os.environ.get("SENTRY_RELEASE", "0.1.0"),
        "deployment.environment": os.environ.get("SENTRY_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")
    logger.info("tracing initialized service=%s", os.environ.get("OTEL_SERVICE_NAME", "ingest-api"))


def init_metrics(app):
    """Wire Prometheus metrics. Always on (no external dep)."""
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        return
    Instrumentator(excluded_handlers=["/v1/healthz", "/v1/readyz"]).instrument(app).expose(app, endpoint="/metrics")


@contextmanager
def timed_operation(name: str, **attrs):
    """Lightweight timing log when tracing is not configured."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 100:
            logger.info("slow_op name=%s ms=%.1f %s", name, elapsed_ms, attrs)
