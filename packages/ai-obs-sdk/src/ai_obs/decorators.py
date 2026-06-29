"""@observe decorator + run/handoff/trace_context API."""
from __future__ import annotations

import asyncio
import functools
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from .context import set_run_context
from .core import SpanContext
from .tracer import get_tracer


def observe(*, agent: str | None = None, tool: str | None = None, llm: str | None = None) -> Callable:
    """Decorator that emits an event for the wrapped function.

    Exactly one of agent/tool/llm must be set. Mutually exclusive.
    """
    keys = [k for k, v in (("agent", agent), ("tool", tool), ("llm", llm)) if v is not None]
    if len(keys) != 1:
        raise ValueError("@observe requires exactly one of agent=, tool=, or llm=")
    kind = keys[0]
    target = {"agent": agent, "tool": tool, "llm": llm}[kind]
    event_type = {"agent": "step.start", "tool": "tool.invoke", "llm": "llm.call"}[kind]
    attr_key = {"agent": "genai.agent.name", "tool": "genai.tool.name", "llm": "genai.llm.model"}[kind]
    span_name = f"{kind}.{target}"

    def decorator(fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                return await _run_async(fn, args, kwargs, kind, target, event_type, attr_key, span_name)
            return async_wrapper
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            return _run_sync(fn, args, kwargs, kind, target, event_type, attr_key, span_name)
        return sync_wrapper
    return decorator


def _run_sync(fn, args, kwargs, kind, target, event_type, attr_key, span_name):
    tracer = get_tracer()
    attrs = {attr_key: target, "event_type": event_type}
    ctx = tracer.start_span(span_name, kind=kind, attributes=attrs)
    try:
        result = fn(*args, **kwargs)
    except Exception as e:
        tracer.end_span(ctx, result=None, error=e)
        raise
    tracer.end_span(ctx, result=result, error=None)
    return result


async def _run_async(fn, args, kwargs, kind, target, event_type, attr_key, span_name):
    tracer = get_tracer()
    attrs = {attr_key: target, "event_type": event_type}
    ctx = tracer.start_span(span_name, kind=kind, attributes=attrs)
    try:
        result = await fn(*args, **kwargs)
    except Exception as e:
        tracer.end_span(ctx, result=None, error=e)
        raise
    tracer.end_span(ctx, result=result, error=None)
    return result


@contextmanager
def run(*, agent: str, input: Any, org_id: str | None = None) -> Iterator["RunContext"]:
    """Context manager for a complete agent run.

    Generates a UUIDv7 run_id, propagates via contextvar, emits run.start + run.end.
    """
    from .uuid7_compat import uuid7
    run_id = str(uuid7())
    set_run_context(run_id, org_id=org_id)
    tracer = get_tracer()
    attrs = {"event_type": "run.start", "genai.agent.name": agent, "input": _truncate(input)}
    ctx = tracer.start_span(f"agent.{agent}", kind="agent", attributes=attrs)
    rc = RunContext(agent=agent, run_id=run_id, span=ctx)
    rc._emit_start()
    try:
        yield rc
    except Exception as e:
        rc._emit_end(status="failed", error=e)
        tracer.end_span(ctx, result=None, error=e)
        raise
    rc._emit_end(status="succeeded", error=None)
    tracer.end_span(ctx, result=None, error=None)


def handoff(*, to: str, payload: Any, reason: str = "delegation") -> None:
    """Top-level handoff helper — must be called inside a `run()` context."""
    from .context import current_run_id
    if current_run_id() is None:
        raise RuntimeError("handoff() must be called within a run() context")
    from .tracer import get_tracer
    tracer = get_tracer()
    attrs = {
        "event_type": "handoff",
        "genai.handoff.from": _current_agent(),
        "genai.handoff.to": to,
        "reason": reason,
        "payload_hash": _hash(payload),
    }
    ctx = tracer.start_span(f"handoff.{_current_agent()}_to_{to}", kind="handoff", attributes=attrs)
    tracer.end_span(ctx, result=None, error=None)


def _current_agent() -> str:
    return _agent_var.get() or "unknown"


class RunContext:
    def __init__(self, *, agent: str, run_id: str, span: SpanContext) -> None:
        self.agent = agent
        self.run_id = run_id
        self.span = span
        _agent_var.set(agent)

    def __exit__(self, *args):
        _agent_var.set(None)

    def handoff(self, *, to: str, payload: Any, reason: str = "delegation") -> None:
        from .tracer import get_tracer
        tracer = get_tracer()
        attrs = {
            "event_type": "handoff",
            "genai.handoff.from": self.agent,
            "genai.handoff.to": to,
            "reason": reason,
            "payload_hash": _hash(payload),
        }
        ctx = tracer.start_span(f"handoff.{self.agent}_to_{to}", kind="handoff", attributes=attrs)
        tracer.end_span(ctx, result=None, error=None)

    def checkpoint(self, *, step: int, state: Any) -> None:
        from .tracer import get_tracer
        tracer = get_tracer()
        attrs = {
            "event_type": "checkpoint",
            "step": step,
            "state_hash": _hash(state),
        }
        ctx = tracer.start_span(f"checkpoint.{step}", kind="checkpoint", attributes=attrs)
        tracer.end_span(ctx, result=None, error=None)

    def _emit_start(self) -> None:
        self.span.attributes["run_id"] = self.run_id
        self.span.attributes["run.start"] = True

    def _emit_end(self, *, status: str, error: Exception | None) -> None:
        self.span.attributes["run.end"] = True
        self.span.attributes["status"] = status


_agent_var: ContextVar[str | None] = ContextVar("ai_obs_current_agent", default=None)


@contextmanager
def trace_context(*, traceparent: str | None = None) -> Iterator[None]:
    """Restore a trace context from a W3C traceparent header.

    Format: 00-{trace_id_32hex}-{span_id_16hex}-{flags_2hex}
    """
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) == 4:
            from .tracer import _parent_span_id_var
            _parent_span_id_var.set(parts[2])
    yield


def _hash(obj: Any) -> str:
    import hashlib, json
    blob = json.dumps(obj, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _truncate(obj: Any, max_bytes: int = 1024) -> Any:
    blob = str(obj).encode()
    if len(blob) <= max_bytes:
        return obj
    return blob[:max_bytes].decode("utf-8", errors="replace") + "..."
