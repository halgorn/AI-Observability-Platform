"""Tests for ai-obs-sdk."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_obs import handoff, observe, run
from ai_obs.context import current_run_id
from ai_obs.decorators import _hash
from ai_obs.tracer import reset_tracer
from ai_obs.redact.pii import redact_obj, redact_str, scan_pii


class _Capture:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, event: dict) -> None:
        self.events.append(event)


@pytest.fixture
def capture():
    from ai_obs.tracer import get_tracer
    from ai_obs.tracer import TracerConfig
    reset_tracer()
    cap = _Capture()
    tracer = get_tracer()
    tracer.config.sample_rate = 1.0
    tracer._emit = cap
    yield cap
    reset_tracer()


def test_observe_sync_emits_event(capture):
    @observe(agent="planner")
    def think(x: int) -> int:
        return x * 2

    assert think(21) == 42
    assert len(capture.events) == 1
    e = capture.events[0]
    assert e["type"] == "step.start"
    assert e["attributes"]["genai.agent.name"] == "planner"


def test_observe_requires_exactly_one_target():
    with pytest.raises(ValueError):
        @observe(agent="x", tool="y")
        def f(): pass


def test_observe_async_emits_event(capture):
    @observe(tool="browser.fetch")
    async def fetch(url: str) -> str:
        return f"fetched {url}"

    result = asyncio.run(fetch("http://x.com"))
    assert result == "fetched http://x.com"
    assert capture.events[0]["type"] == "tool.invoke"
    assert capture.events[0]["attributes"]["genai.tool.name"] == "browser.fetch"


def test_observe_re_raises_exception(capture):
    @observe(agent="planner")
    def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        fail()
    assert capture.events[0]["attributes"]["error"] is True


def test_run_context_propagates_run_id(capture):
    with run(agent="orchestrator", input="test") as r:
        assert current_run_id() == r.run_id
        handoff(to="executor", payload={"plan": "x"})

    assert r.run_id
    assert any(e["type"] == "handoff" for e in capture.events)


def test_handoff_emits_event(capture):
    with run(agent="orchestrator", input="x"):
        handoff(to="executor", payload={"step": 1}, reason="delegation")

    handoff_event = next(e for e in capture.events if e["type"] == "handoff")
    assert handoff_event["attributes"]["genai.handoff.from"] == "orchestrator"
    assert handoff_event["attributes"]["genai.handoff.to"] == "executor"
    assert handoff_event["attributes"]["reason"] == "delegation"


def test_handoff_outside_run_raises():
    from ai_obs.context import _run_id_var
    _run_id_var.set(None)
    with pytest.raises(RuntimeError, match="run"):
        handoff(to="x", payload={})


def test_hash_deterministic():
    a = _hash({"a": 1, "b": [1, 2]})
    b = _hash({"b": [1, 2], "a": 1})
    assert a == b


def test_scan_pii_detects_email():
    assert "email" in scan_pii("contact user@example.com")


def test_redact_str_replaces_email():
    out = redact_str("contact user@example.com")
    assert "[REDACTED:email]" in out
    assert "user@example.com" not in out


def test_redact_obj_nested():
    obj = {"payload": {"input": "user@example.com"}, "ok": True}
    out = redact_obj(obj)
    assert "[REDACTED:email]" in out["payload"]["input"]
    assert out["ok"] is True


def test_redact_idempotent():
    once = redact_str("user@example.com")
    twice = redact_str(once)
    assert once == twice


def test_run_emits_run_start_and_end(capture):
    with run(agent="orchestrator", input="x") as r:
        pass

    types = [e["type"] for e in capture.events]
    assert "run.start" in types
    assert r.run_id


def test_observe_tool_records_result(capture):
    @observe(tool="search.web")
    def search(q: str) -> str:
        return f"result for {q}"

    assert search("ai obs") == "result for ai obs"
    tool_event = next(e for e in capture.events if e["type"] == "tool.invoke")
    assert tool_event["tool"] == "search.web"
    assert tool_event["attributes"]["genai.tool.name"] == "search.web"


def test_observe_llm_records_model(capture):
    @observe(llm="openai/gpt-4o-mini")
    def generate(prompt: str) -> str:
        return "ok"

    generate("hello")
    llm_event = next(e for e in capture.events if e["type"] == "llm.call")
    assert llm_event["llm_model"] == "openai/gpt-4o-mini"
    assert llm_event["payload"]["model"] == "openai/gpt-4o-mini"
