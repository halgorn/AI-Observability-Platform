"""Tests for Langfuse exporter — no real Langfuse needed, mocks the client."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from ai_obs.exporters import langfuse
from ai_obs.exporters.langfuse import export_event, is_enabled, _classify_kind, _to_dt


def test_is_enabled_false_without_env(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert is_enabled() is False


def test_is_enabled_true_with_env(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    assert is_enabled() is True


def test_classify_kind():
    assert _classify_kind({"type": "llm.call"}) == "generation"
    assert _classify_kind({"type": "tool.invoke"}) == "span"
    assert _classify_kind({"type": "handoff"}) == "span"
    assert _classify_kind({"type": "run.start"}) == "span"
    assert _classify_kind({}) == "span"


def test_to_dt_handles_none():
    assert _to_dt(None) is None


def test_to_dt_handles_datetime():
    from datetime import datetime, timezone
    dt = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    assert _to_dt(dt) == dt


def test_to_dt_handles_epoch():
    result = _to_dt(1700000000.0)
    assert result is not None
    assert result.tzinfo is not None
    assert result.timestamp() == 1700000000.0


def test_to_dt_handles_iso_string():
    from datetime import datetime
    result = _to_dt("2026-06-29T12:00:00+00:00")
    assert result.year == 2026


def test_export_event_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    event = {"type": "llm.call", "run_id": "r1", "span_id": "s1", "llm_model": "x"}
    export_event(event)


def test_export_event_calls_generation_for_llm(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    mock_client = MagicMock()
    langfuse._get_client = lambda: mock_client
    event = {
        "type": "llm.call", "run_id": "r1", "span_id": "s1",
        "llm_model": "openai/gpt-4o-mini", "tokens_in": 100, "tokens_out": 50,
        "cost_usd": 0.001, "duration_ms": 1234, "agent": "planner",
        "started_at": "2026-06-29T12:00:00+00:00",
        "ended_at": "2026-06-29T12:00:01+00:00",
        "payload": {"messages_hash": "sha256:abc", "finish_reason": "stop"},
        "attributes": {},
    }
    export_event(event)
    assert mock_client.generation.call_count == 1, f"got {mock_client.generation.call_count}"
    assert mock_client.span.call_count == 0


def test_export_event_calls_span_for_tool(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    mock_client = MagicMock()
    monkeypatch.setattr(langfuse, "_get_client", lambda: mock_client)
    event = {
        "type": "tool.invoke", "run_id": "r1", "span_id": "s1",
        "tool": "browser.fetch", "duration_ms": 500,
        "payload": {}, "attributes": {},
    }
    export_event(event)
    assert mock_client.span.call_count == 1
    assert mock_client.generation.call_count == 0


def test_export_event_handles_exception(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    mock_client = MagicMock()
    mock_client.generation.side_effect = RuntimeError("langfuse down")
    monkeypatch.setattr(langfuse, "_get_client", lambda: mock_client)
    event = {"type": "llm.call", "run_id": "r1", "span_id": "s1", "llm_model": "x",
             "payload": {}, "attributes": {}}
    export_event(event)


def test_export_event_returns_when_client_none(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(langfuse, "_get_client", lambda: None)
    event = {"type": "llm.call", "run_id": "r1", "span_id": "s1", "llm_model": "x",
             "payload": {}, "attributes": {}}
    export_event(event)
    langfuse._client = None


def test_full_pipeline_dual_exports(monkeypatch):
    """End-to-end: @observe emits to both our collector and Langfuse."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    mock_client = MagicMock()
    monkeypatch.setattr(langfuse, "_get_client", lambda: mock_client)

    cap = {"events": []}
    def _capture(event):
        cap["events"].append(event)

    from ai_obs.tracer import reset_tracer, get_tracer
    reset_tracer()
    tracer = get_tracer()
    tracer.config.sample_rate = 1.0
    tracer._emit = _capture

    from ai_obs import observe
    @observe(llm="openai/gpt-4o-mini")
    def call(p: str) -> str:
        return "ok"

    call("hi")
    assert mock_client.generation.call_count == 1, f"expected 1, got {mock_client.generation.call_count}"
    assert len(cap["events"]) == 1
    reset_tracer()
