"""Tests for LangGraph GraphTracer (no langchain-core required)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_obs.langgraph.graph_tracer import GraphTracer
from ai_obs.tracer import reset_tracer
from ai_obs.pricing import cost_of_call


class _Capture:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, event: dict) -> None:
        self.events.append(event)


@pytest.fixture
def capture():
    reset_tracer()
    from ai_obs.tracer import get_tracer
    cap = _Capture()
    tracer = get_tracer()
    tracer.config.sample_rate = 1.0
    tracer._emit = cap
    yield cap
    reset_tracer()


def test_graph_tracer_on_chain_start_end(capture):
    gt = GraphTracer(agent_name="planner", run_id="019065a1-7c8e-7abc-9def-1234567890ab")
    gt.on_chain_start({}, {"step": 1, "messages": []})
    gt.on_chain_end({"output": "x"})

    types = [e["type"] for e in capture.events]
    assert "step.start" in types


def test_graph_tracer_on_llm_start_end_records_tokens(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_llm_start({"name": "openai/gpt-4o-mini"}, ["hello"])
    response = MagicMock()
    response.llm_output = {"token_usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    response.generations = [[[MagicMock(finish_reason="stop")]]]
    gt.on_llm_end(response)

    llm_event = next(e for e in capture.events if e["type"] == "llm.call")
    assert llm_event["tokens_in"] == 100
    assert llm_event["tokens_out"] == 50
    assert llm_event["cost_usd"] > 0


def test_graph_tracer_on_tool_emits(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_tool_start({"name": "browser.fetch"}, "http://x.com")
    gt.on_tool_end("<html>...</html>")

    tool_event = next(e for e in capture.events if e["type"] == "tool.invoke")
    assert tool_event["tool"] == "browser.fetch"


def test_graph_tracer_on_handoff(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_handoff(to_agent="executor", payload={"step": 1})

    h = next(e for e in capture.events if e["type"] == "handoff")
    assert h["attributes"]["genai.handoff.to"] == "executor"


def test_graph_tracer_on_checkpoint(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_checkpoint(step=3, state={"messages": []})

    c = next(e for e in capture.events if e["type"] == "checkpoint")
    assert c["attributes"]["step"] == 3


def test_graph_tracer_on_chain_error_marks_error(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_chain_start({}, {"step": 1})
    gt.on_chain_error(ValueError("oops"))

    e = capture.events[0]
    assert e["attributes"]["error"] is True
    assert e["attributes"]["error.type"] == "ValueError"


def test_graph_tracer_on_tool_error_marks_error(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_tool_start({"name": "search"}, "query")
    gt.on_tool_error(RuntimeError("tool failed"))

    assert capture.events[0]["attributes"]["error"] is True


def test_graph_tracer_on_llm_error_marks_error(capture):
    gt = GraphTracer(agent_name="planner")
    gt.on_llm_start({"name": "openai/gpt-4o"}, ["hi"])
    gt.on_llm_error(RuntimeError("rate limit"))

    assert capture.events[0]["attributes"]["error"] is True


def test_cost_of_call_known_model():
    cost = cost_of_call(model="openai/gpt-4o-mini", tokens_in=1000, tokens_out=500)
    assert cost == pytest.approx(0.00045, rel=1e-6)


def test_cost_of_call_unknown_model():
    assert cost_of_call(model="unknown/model", tokens_in=100, tokens_out=50) is None
