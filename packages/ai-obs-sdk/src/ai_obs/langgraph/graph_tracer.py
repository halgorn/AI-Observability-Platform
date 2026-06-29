"""LangGraph drop-in.

Usage:
    from ai_obs.langgraph.graph_tracer import traced_graph
    graph = traced_graph(builder.compile(checkpointer=saver), agent_name="planner")
"""
from __future__ import annotations

import logging
from typing import Any

from ..context import set_run_context
from ..tracer import get_tracer
from ..uuid7_compat import uuid7

logger = logging.getLogger(__name__)


class GraphTracer:
    """Captures LangGraph state machine via PostgresSaver checkpoints + callbacks.

    Hooks:
        on_chain_start -> step.start
        on_chain_end   -> step.end
        on_chain_error -> error
        on_tool_*      -> tool.invoke
        on_llm_*       -> llm.call
        on_handoff     -> handoff
    """

    def __init__(self, *, agent_name: str, run_id: str | None = None, org_id: str | None = None) -> None:
        self.agent_name = agent_name
        self.run_id = run_id or str(uuid7())
        self.org_id = org_id
        set_run_context(self.run_id, org_id=org_id)

    def on_chain_start(self, serialized: dict, inputs: dict, **kwargs) -> None:
        tracer = get_tracer()
        attrs = {
            "event_type": "step.start",
            "genai.agent.name": self.agent_name,
            "step": _extract_step(inputs),
        }
        self._ctx = tracer.start_span(f"agent.{self.agent_name}", kind="agent", attributes=attrs)

    def on_chain_end(self, outputs: dict, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_ctx"):
            tracer.end_span(self._ctx, result=outputs, error=None)
            del self._ctx

    def on_chain_error(self, error: Exception, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_ctx"):
            tracer.end_span(self._ctx, result=None, error=error)
            del self._ctx

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        tracer = get_tracer()
        name = serialized.get("name", "unknown")
        attrs = {
            "event_type": "tool.invoke",
            "genai.tool.name": name,
            "args_hash": _hash(input_str),
        }
        self._tool_ctx = tracer.start_span(f"tool.{name}", kind="tool", attributes=attrs)

    def on_tool_end(self, output: str, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_tool_ctx"):
            self._tool_ctx.attributes["result_hash"] = _hash(output)
            tracer.end_span(self._tool_ctx, result=output, error=None)
            del self._tool_ctx

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_tool_ctx"):
            tracer.end_span(self._tool_ctx, result=None, error=error)
            del self._tool_ctx

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        tracer = get_tracer()
        attrs = {
            "event_type": "llm.call",
            "genai.llm.model": serialized.get("name", "unknown/unknown"),
            "messages_hash": _hash(prompts),
            "messages_size": sum(len(p) for p in prompts),
        }
        self._llm_ctx = tracer.start_span(f"llm.{attrs['genai.llm.model']}", kind="llm", attributes=attrs)

    def on_llm_end(self, response: Any, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_llm_ctx"):
            usage = getattr(response, "llm_output", None) or {}
            token_usage = usage.get("token_usage", {}) or {}
            self._llm_ctx.attributes["genai.llm.tokens.input"] = token_usage.get("prompt_tokens", 0)
            self._llm_ctx.attributes["genai.llm.tokens.output"] = token_usage.get("completion_tokens", 0)
            try:
                gens = response.generations
                if gens and gens[0] and hasattr(gens[0][0], "finish_reason"):
                    self._llm_ctx.attributes["finish_reason"] = gens[0][0].finish_reason
                else:
                    self._llm_ctx.attributes["finish_reason"] = "stop"
            except (AttributeError, IndexError, TypeError):
                self._llm_ctx.attributes["finish_reason"] = "stop"
            cost = _cost_of_call(self._llm_ctx.attributes["genai.llm.model"], token_usage.get("prompt_tokens", 0), token_usage.get("completion_tokens", 0))
            if cost is not None:
                self._llm_ctx.attributes["genai.llm.cost.usd"] = cost
            tracer.end_span(self._llm_ctx, result=response, error=None)
            del self._llm_ctx

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        tracer = get_tracer()
        if hasattr(self, "_llm_ctx"):
            tracer.end_span(self._llm_ctx, result=None, error=error)
            del self._llm_ctx

    def on_handoff(self, *, to_agent: str, payload: Any, reason: str = "delegation") -> None:
        tracer = get_tracer()
        attrs = {
            "event_type": "handoff",
            "genai.handoff.from": self.agent_name,
            "genai.handoff.to": to_agent,
            "reason": reason,
            "payload_hash": _hash(payload),
        }
        ctx = tracer.start_span(f"handoff.{self.agent_name}_to_{to_agent}", kind="handoff", attributes=attrs)
        tracer.end_span(ctx, result=None, error=None)

    def on_checkpoint(self, *, step: int, state: Any) -> None:
        tracer = get_tracer()
        attrs = {
            "event_type": "checkpoint",
            "step": step,
            "state_hash": _hash(state),
        }
        ctx = tracer.start_span(f"checkpoint.{step}", kind="checkpoint", attributes=attrs)
        tracer.end_span(ctx, result=None, error=None)


def traced_graph(graph, *, agent_name: str, org_id: str | None = None):
    """Wrap a compiled LangGraph with GraphTracer callbacks.

    Returns the same graph instance with .stream() / .invoke() traced.
    """
    tracer = GraphTracer(agent_name=agent_name, org_id=org_id)
    try:
        from langchain_core.tracers import LangChainTracer
        from langchain_core.callbacks import BaseCallbackHandler

        class _Bridge(BaseCallbackHandler):
            def on_chain_start(self, serialized, inputs, **kw):
                tracer.on_chain_start(serialized, inputs, **kw)

            def on_chain_end(self, outputs, **kw):
                tracer.on_chain_end(outputs, **kw)

            def on_chain_error(self, error, **kw):
                tracer.on_chain_error(error, **kw)

            def on_tool_start(self, serialized, input_str, **kw):
                tracer.on_tool_start(serialized, input_str, **kw)

            def on_tool_end(self, output, **kw):
                tracer.on_tool_end(output, **kw)

            def on_tool_error(self, error, **kw):
                tracer.on_tool_error(error, **kw)

            def on_llm_start(self, serialized, prompts, **kw):
                tracer.on_llm_start(serialized, prompts, **kw)

            def on_llm_end(self, response, **kw):
                tracer.on_llm_end(response, **kw)

            def on_llm_error(self, error, **kw):
                tracer.on_llm_error(error, **kw)

        original_invoke = graph.invoke
        original_stream = graph.stream

        def invoke(*args, **kwargs):
            callbacks = kwargs.get("config", {}).get("callbacks", [])
            if not isinstance(callbacks, list):
                callbacks = [callbacks]
            callbacks.append(_Bridge())
            cfg = dict(kwargs.get("config", {}))
            cfg["callbacks"] = callbacks
            kwargs["config"] = cfg
            return original_invoke(*args, **kwargs)

        def stream(*args, **kwargs):
            callbacks = kwargs.get("config", {}).get("callbacks", [])
            if not isinstance(callbacks, list):
                callbacks = [callbacks]
            callbacks.append(_Bridge())
            cfg = dict(kwargs.get("config", {}))
            cfg["callbacks"] = callbacks
            kwargs["config"] = cfg
            yield from original_stream(*args, **kwargs)

        graph.invoke = invoke
        graph.stream = stream
    except ImportError:
        logger.warning("langchain-core not installed; GraphTracer hooks inactive")
    return graph


def _hash(obj: Any) -> str:
    import hashlib, json
    blob = json.dumps(obj, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _extract_step(inputs: Any) -> int:
    if isinstance(inputs, dict):
        return inputs.get("step", 0)
    return 0


def _cost_of_call(model: str, tokens_in: int, tokens_out: int) -> float | None:
    try:
        from ..pricing import cost_of_call
        return cost_of_call(model=model, tokens_in=tokens_in, tokens_out=tokens_out)
    except Exception:
        return None
