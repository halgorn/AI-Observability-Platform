"""Tests for ReplayEngine."""
from __future__ import annotations

import pytest

from app.engine import ReplayEngine
from app.mock import MockLayer
from app.session import ReplaySession, canonical_hash


def test_create_session_has_seed_from_run_id():
    s = ReplaySession.create(run_id="abc", total_steps=10)
    assert s.session_id
    assert s.run_id == "abc"
    assert s.total_steps == 10
    assert s.seed != 0


def test_session_seed_deterministic():
    s1 = ReplaySession.create(run_id="fixed-run", total_steps=5)
    s2 = ReplaySession.create(run_id="fixed-run", total_steps=5)
    assert s1.seed == s2.seed


def test_session_seed_differs_for_different_runs():
    s1 = ReplaySession.create(run_id="run-a", total_steps=5)
    s2 = ReplaySession.create(run_id="run-b", total_steps=5)
    assert s1.seed != s2.seed


def test_session_starts_ready():
    s = ReplaySession.create(run_id="r", total_steps=10)
    assert s.status == "ready"
    assert s.current_step == 0
    assert s.mock_llm is True


def test_session_to_dict_roundtrip():
    s = ReplaySession.create(run_id="r", total_steps=10)
    s.current_step = 3
    s.mock_tools.add("search")
    d = s.to_dict()
    assert d["current_step"] == 3
    assert "search" in d["mock_tools"]


def test_load_creates_session():
    engine = ReplayEngine()
    events = [
        {"span_id": "a", "type": "llm.call", "duration_ms": 100,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
         "payload": {}, "attributes": {}},
    ]
    s = engine.load("r1", events, [])
    assert s.run_id == "r1"
    assert s.total_steps == 1
    assert s.session_id in engine._sessions


def test_load_empty_raises():
    engine = ReplayEngine()
    with pytest.raises(ValueError, match="no events"):
        engine.load("r", [], [])


def test_toggle_mock_llm():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "llm.call", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    updated = engine.toggle_mock(s.session_id, target="llm", value=False)
    assert updated.mock_llm is False


def test_toggle_mock_tool():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "tool.invoke", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    updated = engine.toggle_mock(s.session_id, target="tool", value="search.web")
    assert "search.web" in updated.mock_tools


def test_toggle_mock_unknown_raises():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "x", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    with pytest.raises(ValueError, match="unknown"):
        engine.toggle_mock(s.session_id, target="weird", value=True)


def test_get_returns_session():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "x", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    assert engine.get(s.session_id) is s
    assert engine.get("nonexistent") is None


def test_step_advances_counter():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "x", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    asyncio_run(engine.step(s.session_id, n=1))
    s2 = engine.get(s.session_id)
    assert s2.current_step == 1


def test_step_past_end_marks_done():
    engine = ReplayEngine()
    s = engine.load("r", [{"span_id": "a", "type": "x", "duration_ms": 0,
                          "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
                          "payload": {}, "attributes": {}}], [])
    asyncio_run(engine.step(s.session_id, n=10))
    s2 = engine.get(s.session_id)
    assert s2.status == "done"


def test_replay_full_marks_done():
    engine = ReplayEngine()
    events = [
        {"span_id": f"e{i}", "type": "x", "duration_ms": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
         "payload": {}, "attributes": {}}
        for i in range(3)
    ]
    s = engine.load("r", events, [])
    asyncio_run(engine.replay_full(s.session_id))
    s2 = engine.get(s.session_id)
    assert s2.status == "done"
    assert s2.current_step == 3


def test_canonical_hash_deterministic():
    a = canonical_hash({"x": 1, "y": [1, 2]})
    b = canonical_hash({"y": [1, 2], "x": 1})
    assert a == b


def test_canonical_hash_ignores_none():
    a = canonical_hash({"x": 1, "y": None})
    b = canonical_hash({"x": 1})
    assert a == b


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
