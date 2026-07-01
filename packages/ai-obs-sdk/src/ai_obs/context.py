"""Event building + contextvar helpers.

Imports Tracer and SpanContext from core to break circular dependency.
"""
from __future__ import annotations

import datetime
import time
from contextvars import ContextVar
from typing import Any

from .redact.pii import redact_obj, scan_pii

_run_id_var: ContextVar[str | None] = ContextVar("ai_obs_run_id", default=None)
_span_id_var: ContextVar[str | None] = ContextVar("ai_obs_span_id", default=None)
_parent_span_id_var: ContextVar[str | None] = ContextVar("ai_obs_parent_span_id", default=None)
_org_id_var: ContextVar[str | None] = ContextVar("ai_obs_org_id", default=None)
_pending_tokens_in_var: ContextVar[int] = ContextVar("ai_obs_pending_tokens_in", default=0)
_pending_tokens_out_var: ContextVar[int] = ContextVar("ai_obs_pending_tokens_out", default=0)
_pending_cost_var: ContextVar[float] = ContextVar("ai_obs_pending_cost_usd", default=0.0)


def set_run_context(run_id: str, org_id: str | None = None) -> None:
    _run_id_var.set(run_id)
    if org_id:
        _org_id_var.set(org_id)


def add_pending_llm(*, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0) -> None:
    """Acumula tokens/custo de chamadas LLM feitas de fora do RunContext.

    Usado quando uma chamada LLM é feita em código que não tem acesso direto
    ao RunContext (ex.: run_adk_agent dentro de uma task Celery). Os valores
    são somados a contextvars e mesclados no RunContext quando run() termina.
    """
    if tokens_in:
        _pending_tokens_in_var.set(_pending_tokens_in_var.get() + int(tokens_in))
    if tokens_out:
        _pending_tokens_out_var.set(_pending_tokens_out_var.get() + int(tokens_out))
    if cost_usd:
        _pending_cost_var.set(_pending_cost_var.get() + float(cost_usd))


def drain_pending_llm() -> tuple[int, int, float]:
    """Consome e zera os contextvars pendentes. Retorna (in, out, usd)."""
    in_t = _pending_tokens_in_var.get()
    out_t = _pending_tokens_out_var.get()
    cost = _pending_cost_var.get()
    _pending_tokens_in_var.set(0)
    _pending_tokens_out_var.set(0)
    _pending_cost_var.set(0.0)
    return in_t, out_t, cost


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


def build_event_dict(ctx: Any, *, result: Any, error: Exception | None, tracer: Any) -> dict:
    """Build our `Event` shape from a SpanContext."""
    event_type = ctx.attributes.get("event_type", "step.start")
    payload = _build_payload(event_type=event_type, ctx=ctx, result=result, error=error)
    event = {
        "run_id": current_run_id() or ctx.attributes.get("genai.run.id"),
        "span_id": ctx.span_id,
        "parent_span_id": ctx.parent_span_id,
        "type": event_type,
        "started_at": _to_iso(ctx.started_at),
        "ended_at": _to_iso(ctx.ended_at),
        "duration_ms": ctx.duration_ms,
        "payload": payload,
        "attributes": _redact(ctx.attributes, tracer.config.pii_mode, tracer.config.redact_keys),
        "agent": ctx.attributes.get("genai.agent.name"),
        "tool": ctx.attributes.get("genai.tool.name"),
        "llm_model": ctx.attributes.get("genai.llm.model"),
    }
    if error is not None:
        event["error_code"] = "UNKNOWN"
    if "genai.llm.tokens.input" in ctx.attributes:
        event["tokens_in"] = ctx.attributes["genai.llm.tokens.input"]
    if "genai.llm.tokens.output" in ctx.attributes:
        event["tokens_out"] = ctx.attributes["genai.llm.tokens.output"]
    if "genai.llm.cost.usd" in ctx.attributes:
        event["cost_usd"] = ctx.attributes["genai.llm.cost.usd"]
    return event


def _to_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()


def _build_payload(*, event_type: str, ctx: Any, result: Any, error: Exception | None) -> dict:
    if event_type == "llm.call":
        return {
            "model": ctx.attributes.get("genai.llm.model", "unknown/unknown"),
            "messages_hash": ctx.attributes.get("messages_hash", "sha256:" + "0" * 64),
            "messages_size": ctx.attributes.get("messages_size", 0),
            "finish_reason": ctx.attributes.get("finish_reason", "stop"),
        }
    if event_type == "tool.invoke":
        return {
            "tool": ctx.attributes.get("genai.tool.name", "unknown"),
            "args_hash": ctx.attributes.get("args_hash", "sha256:" + "0" * 64),
            "side_effect": ctx.attributes.get("side_effect", False),
        }
    if event_type == "handoff":
        return {
            "from": ctx.attributes.get("genai.handoff.from", ""),
            "to": ctx.attributes.get("genai.handoff.to", ""),
            "reason": ctx.attributes.get("reason", "delegation"),
            "payload_hash": ctx.attributes.get("payload_hash", "sha256:" + "0" * 64),
        }
    if event_type == "error":
        return {
            "code": ctx.attributes.get("error_code", "UNKNOWN"),
            "message": ctx.attributes.get("error.message", "unknown")[:500],
            "retryable": ctx.attributes.get("retryable", False),
        }
    if event_type == "step.start":
        return {
            "step": ctx.attributes.get("step", 0),
            "agent": ctx.attributes.get("genai.agent.name") or None,
        }
    if event_type == "run.start":
        return {
            "input_hash": ctx.attributes.get("input_hash", "sha256:" + "0" * 64),
            "input_size": ctx.attributes.get("input_size", 0),
            "agent": ctx.attributes.get("genai.agent.name") or "unknown",
            "thread_id": ctx.attributes.get("thread_id"),
            "prompt_version": ctx.attributes.get("prompt_version"),
        }
    if event_type == "run.end":
        return {
            "status": ctx.attributes.get("status", "succeeded"),
            "total_steps": ctx.attributes.get("total_steps", 0),
            "total_tokens": ctx.attributes.get("total_tokens", 0),
            "total_cost_usd": ctx.attributes.get("total_cost_usd", 0.0),
        }
    if event_type == "checkpoint":
        return {
            "step": ctx.attributes.get("step", 0),
            "state_hash": ctx.attributes.get("state_hash", "sha256:" + "0" * 64),
        }
    return {}


def _redact(attributes: dict, pii_mode: str, redact_keys: list[str]) -> dict:
    if pii_mode == "passthrough":
        return attributes
    out = dict(attributes)
    for key in redact_keys:
        if key in out:
            out[key] = "[REDACTED]"
    pii_hits = scan_pii(str(out))
    if pii_hits:
        if pii_mode == "strict":
            raise ValueError(f"PII detected: {pii_hits}")
        out = redact_obj(out)
    return out
