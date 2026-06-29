"""Tests for analytics: cost aggregation, handoff graph, diff."""
from __future__ import annotations

import pytest

from app.analytics import build_handoff_graph, compute_cost_diff, parse_window
from app.routers.analytics import _parse_window_unused as rw_parse


def test_handoff_graph_empty():
    assert build_handoff_graph([]) == []


def test_handoff_graph_single_edge():
    events = [
        {"type": "handoff", "payload": {"from": "planner", "to": "executor"}, "error_code": None},
    ]
    g = build_handoff_graph(events)
    assert len(g) == 1
    assert g[0]["from"] == "planner"
    assert g[0]["to"] == "executor"
    assert g[0]["success_count"] == 1
    assert g[0]["total_count"] == 1
    assert g[0]["success_rate"] == 1.0


def test_handoff_graph_aggregates_multiple_calls():
    events = [
        {"type": "handoff", "payload": {"from": "p", "to": "e"}, "error_code": None},
        {"type": "handoff", "payload": {"from": "p", "to": "e"}, "error_code": "REJECTED"},
        {"type": "handoff", "payload": {"from": "p", "to": "r"}, "error_code": None},
    ]
    g = build_handoff_graph(events)
    by_key = {(e["from"], e["to"]): e for e in g}
    assert by_key[("p", "e")]["total_count"] == 2
    assert by_key[("p", "e")]["success_count"] == 1
    assert by_key[("p", "e")]["success_rate"] == 0.5
    assert by_key[("p", "r")]["total_count"] == 1
    assert by_key[("p", "r")]["success_rate"] == 1.0


def test_handoff_graph_sorted_by_count():
    events = [
        {"type": "handoff", "payload": {"from": "a", "to": "b"}, "error_code": None},
    ] * 3 + [
        {"type": "handoff", "payload": {"from": "a", "to": "c"}, "error_code": None},
    ] * 5
    g = build_handoff_graph(events)
    assert g[0]["to"] == "c"
    assert g[0]["total_count"] == 5
    assert g[1]["to"] == "b"


def test_handoff_graph_skips_non_handoff():
    events = [
        {"type": "llm.call", "payload": {"from": "x", "to": "y"}, "error_code": None},
    ]
    assert build_handoff_graph(events) == []


def test_cost_diff_no_change():
    events = [
        {"type": "llm.call", "cost_usd": 0.001, "tokens_in": 100, "tokens_out": 50},
    ]
    a = compute_cost_diff(events, events)
    assert a["a"]["cost_usd"] == a["b"]["cost_usd"]
    assert a["delta"]["cost_usd"] == 0
    assert a["ratio"]["cost_usd"] == 1.0


def test_cost_diff_increase():
    a_events = [
        {"type": "llm.call", "cost_usd": 0.001, "tokens_in": 100, "tokens_out": 50},
    ]
    b_events = [
        {"type": "llm.call", "cost_usd": 0.005, "tokens_in": 200, "tokens_out": 100},
        {"type": "tool.invoke", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0},
    ]
    d = compute_cost_diff(a_events, b_events)
    assert d["b"]["cost_usd"] == 0.005
    assert d["delta"]["cost_usd"] == 0.004
    assert d["b"]["llm_calls"] == 1
    assert d["b"]["tool_calls"] == 1
    assert d["b"]["errors"] == 0


def test_cost_diff_handles_zero_a():
    a = []
    b = [{"type": "llm.call", "cost_usd": 0.001}]
    d = compute_cost_diff(a, b)
    assert d["ratio"]["cost_usd"] == float("inf")


def test_parse_window_days():
    assert parse_window("7d") == 7
    assert parse_window("30d") == 30


def test_parse_window_hours():
    assert parse_window("24h") == 1
    assert parse_window("48h") == 2


def test_parse_window_minutes():
    assert parse_window("30m") == 1


def test_parse_window_default():
    assert parse_window("garbage") == 7


def test_parse_window_router_alias():
    assert rw_parse("7d") == 7
