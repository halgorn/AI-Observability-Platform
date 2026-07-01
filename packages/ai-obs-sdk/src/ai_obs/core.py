"""Core types — Tracer, SpanContext.

This module is intentionally import-free of other ai_obs modules to avoid
circular imports. tracer.py and context.py both import from here.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

_run_id_var: ContextVar[str | None] = ContextVar("ai_obs_run_id", default=None)
_span_id_var: ContextVar[str | None] = ContextVar("ai_obs_span_id", default=None)
_parent_span_id_var: ContextVar[str | None] = ContextVar("ai_obs_parent_span_id", default=None)
_org_id_var: ContextVar[str | None] = ContextVar("ai_obs_org_id", default=None)


def set_run_context(run_id: str, org_id: str | None = None) -> None:
    _run_id_var.set(run_id)
    if org_id:
        _org_id_var.set(org_id)


def current_run_id() -> str | None:
    return _run_id_var.get()


def current_span_id() -> str | None:
    return _span_id_var.get()


def current_parent_span_id() -> str | None:
    return _parent_span_id_var.get()


def set_parent_span_id(span_id: str | None) -> None:
    _parent_span_id_var.set(span_id)


def set_span_id(span_id: str | None) -> None:
    _span_id_var.set(span_id)


class Tracer:
    def __init__(self, config: Any) -> None:
        self.config = config
        self._otel = self._init_otel()
        self._buffer: list[dict] = []
        self._buffer_lock = threading.Lock()
        self._hostname = socket.gethostname()
        self._pid = os.getpid()
        self._stopped = False
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self._flush_thread.start()

    def _periodic_flush(self) -> None:
        while not self._stopped:
            time.sleep(5)
            try:
                self._flush()
            except Exception:
                pass

    def _init_otel(self) -> Any:
        if not self.config.endpoint:
            return None
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            logger.warning("opentelemetry packages not installed; OTel disabled")
            return None
        resource = Resource.create({
            "service.name": self.config.service_name,
            "service.version": self.config.service_version,
            "deployment.environment": self.config.environment,
            "host.name": self._hostname,
            "process.pid": self._pid,
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=self.config.endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        return trace.get_tracer(self.config.service_name)

    def start_span(self, name: str, *, kind: str, attributes: dict[str, Any]) -> "SpanContext":
        parent = current_parent_span_id()
        span_id = uuid.uuid4().hex[:16]
        set_span_id(span_id)
        set_parent_span_id(span_id)
        sampled = self._should_sample(kind=kind, attributes=attributes)
        otel_span = None
        if self._otel and sampled:
            otel_span = self._otel.start_span(name, attributes=attributes)
            otel_span.set_attribute("genai.run.id", current_run_id() or "")
        return SpanContext(
            tracer=self,
            name=name,
            span_id=span_id,
            parent_span_id=parent,
            otel_span=otel_span,
            attributes=attributes,
            started_at=time.time(),
            sampled=sampled,
        )

    def _should_sample(self, *, kind: str, attributes: dict[str, Any]) -> bool:
        if attributes.get("error") is not None or attributes.get("error_code"):
            return True
        if attributes.get("event_type") in ("run.start", "run.end"):
            return True
        import random
        return random.random() < self.config.sample_rate

    def flush(self) -> None:
        self._flush()

    def end_span(self, ctx: "SpanContext", result: Any, error: Exception | None) -> None:
        ctx.ended_at = time.time()
        ctx.duration_ms = int((ctx.ended_at - ctx.started_at) * 1000)
        if error is not None:
            ctx.attributes["error"] = True
            ctx.attributes["error.type"] = type(error).__name__
            ctx.attributes["error.message"] = str(error)[:200]
        if ctx.otel_span is not None:
            if error is not None:
                try:
                    from opentelemetry.trace import Status, StatusCode
                    ctx.otel_span.set_status(Status(StatusCode.ERROR, str(error)[:200]))
                except Exception:
                    pass
            ctx.otel_span.end()
        if ctx.sampled:
            event = self._build_event(ctx, result=result, error=error)
            self._emit_langfuse(event)
            self._emit(event)
        set_span_id(ctx.parent_span_id)
        set_parent_span_id(ctx.parent_span_id)

    def _build_event(self, ctx: "SpanContext", *, result: Any, error: Exception | None) -> dict:
        from .context import build_event_dict
        return build_event_dict(ctx, result=result, error=error, tracer=self)

    def _emit_langfuse(self, event: dict) -> None:
        try:
            from .exporters.langfuse import is_enabled as _lf_enabled, export_event as _lf_export
            if _lf_enabled():
                _lf_export(event)
        except Exception as e:
            import traceback
            logger.warning("langfuse export dispatch failed: %s\n%s", e, traceback.format_exc())

    def _emit(self, event: dict) -> None:
        with self._buffer_lock:
            self._buffer.append(event)
        if len(self._buffer) >= 100:
            self._flush()

    def _flush(self) -> None:
        with self._buffer_lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()
        self._send_batch(batch)

    def _send_batch(self, batch: list[dict]) -> None:
        endpoint = self.config.endpoint or os.environ.get("AI_OBS_INGEST_URL", "http://localhost:8000")
        url = f"{endpoint.rstrip('/')}/v1/events"
        headers = {}
        token = os.environ.get("AI_OBS_SERVICE_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            import httpx
            with httpx.Client(timeout=5.0) as c:
                c.post(url, json=batch, headers=headers)
        except Exception as e:
            logger.warning("failed to emit %d events: %s", len(batch), e)

    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._flush()


class SpanContext:
    __slots__ = ("tracer", "name", "span_id", "parent_span_id", "otel_span", "attributes", "started_at", "ended_at", "duration_ms", "sampled", "_token")

    def __init__(self, *, tracer: "Tracer", name: str, span_id: str, parent_span_id: str | None, otel_span: Any, attributes: dict, started_at: float, sampled: bool) -> None:
        self.tracer = tracer
        self.name = name
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.otel_span = otel_span
        self.attributes = attributes
        self.started_at = started_at
        self.ended_at: float | None = None
        self.duration_ms: int | None = None
        self.sampled = sampled
        self._token: Any = None
