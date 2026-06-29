"""Tests for trace builder."""
from __future__ import annotations

from app.trace_builder import build_trace


def test_empty_events():
    result = build_trace([])
    assert result["roots"] == []
    assert result["summary"]["total_events"] == 0


def test_single_event_becomes_root():
    events = [
        {"span_id": "0aaa", "parent_span_id": None, "type": "llm.call",
         "llm_model": "openai/gpt-4o-mini", "duration_ms": 100, "cost_usd": 0.001,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": "2026-06-29T12:00:00.1Z",
         "payload": {}, "attributes": {}},
    ]
    result = build_trace(events)
    assert len(result["roots"]) == 1
    assert result["roots"][0]["name"] == "llm.call:openai/gpt-4o-mini"
    assert result["roots"][0]["kind"] == "llm"
    assert result["summary"]["total_cost_usd"] == 0.001


def test_hierarchy():
    events = [
        {"span_id": "parent", "parent_span_id": None, "type": "step.start",
         "agent": "orchestrator", "duration_ms": 1000, "cost_usd": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None, "payload": {}, "attributes": {}},
        {"span_id": "child1", "parent_span_id": "parent", "type": "tool.invoke",
         "tool": "search", "duration_ms": 300, "cost_usd": 0.0001,
         "started_at": "2026-06-29T12:00:00.1Z", "ended_at": None, "payload": {}, "attributes": {}},
        {"span_id": "child2", "parent_span_id": "parent", "type": "llm.call",
         "llm_model": "openai/gpt-4o-mini", "duration_ms": 500, "cost_usd": 0.001,
         "started_at": "2026-06-29T12:00:00.4Z", "ended_at": None, "payload": {}, "attributes": {}},
    ]
    result = build_trace(events)
    assert len(result["roots"]) == 1
    root = result["roots"][0]
    assert len(root["children"]) == 2
    names = sorted(c["name"] for c in root["children"])
    assert "tool.search" in names
    assert "llm.call:openai/gpt-4o-mini" in names


def test_orphan_child_promoted_to_root():
    events = [
        {"span_id": "child", "parent_span_id": "missing", "type": "tool.invoke",
         "tool": "x", "duration_ms": 100, "cost_usd": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None, "payload": {}, "attributes": {}},
    ]
    result = build_trace(events)
    assert len(result["roots"]) == 1


def test_error_event_marked_as_error():
    events = [
        {"span_id": "1", "parent_span_id": None, "type": "error",
         "error_code": "TOOL_TIMEOUT", "duration_ms": 100, "cost_usd": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None, "payload": {}, "attributes": {}},
    ]
    result = build_trace(events)
    assert result["roots"][0]["status"] == "error"


def test_handoff_event_uses_payload_names():
    events = [
        {"span_id": "h1", "parent_span_id": None, "type": "handoff",
         "duration_ms": 50, "cost_usd": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
         "payload": {"from": "planner", "to": "executor"}, "attributes": {}},
    ]
    result = build_trace(events)
    assert "planner" in result["roots"][0]["name"]
    assert "executor" in result["roots"][0]["name"]


def test_aggregates_cost_and_duration():
    events = [
        {"span_id": "a", "parent_span_id": None, "type": "llm.call",
         "duration_ms": 100, "cost_usd": 0.001,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None, "payload": {}, "attributes": {}},
        {"span_id": "b", "parent_span_id": None, "type": "llm.call",
         "duration_ms": 200, "cost_usd": 0.002,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None, "payload": {}, "attributes": {}},
    ]
    result = build_trace(events)
    assert result["summary"]["total_cost_usd"] == 0.003
    assert result["summary"]["total_duration_ms"] == 200
    assert result["summary"]["total_events"] == 2


def test_checkpoint_event_includes_step():
    events = [
        {"span_id": "c1", "parent_span_id": None, "type": "checkpoint",
         "duration_ms": 10, "cost_usd": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
         "payload": {"step": 5}, "attributes": {}},
    ]
    result = build_trace(events)
    assert "step5" in result["roots"][0]["name"]
    assert result["roots"][0]["kind"] == "checkpoint"
