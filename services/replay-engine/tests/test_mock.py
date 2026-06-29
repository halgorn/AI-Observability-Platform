"""Tests for MockLayer."""
from __future__ import annotations

import pytest

from app.mock import MockLayer


def test_mock_llm_default_returns_marker():
    m = MockLayer()
    result = m.call_llm(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
    assert result["cached"] is True
    assert result["output"] == "[MOCK_NO_RESPONSE]"


def test_mock_llm_registered_returns_registered():
    from app.mock import _hash_obj
    m = MockLayer()
    messages = [{"role": "user", "content": "hi"}]
    key_hash = _hash_obj(messages)
    m.register_llm("openai/gpt-4o-mini", key_hash, {"output": "hello", "tokens_in": 5, "tokens_out": 1, "cost_usd": 0.001})
    result = m.call_llm(model="openai/gpt-4o-mini", messages=messages)
    assert result["output"] == "hello"


def test_mock_llm_disabled_raises():
    m = MockLayer(mock_llm=False)
    with pytest.raises(RuntimeError, match="real LLM"):
        m.call_llm(model="x", messages=[])


def test_mock_tool_returns_marker_if_unregistered():
    m = MockLayer(mock_tools={"search"})
    result = m.call_tool(tool="search", args={"q": "x"})
    assert result["_mocked"] is True


def test_mock_tool_returns_registered():
    from app.mock import _hash_obj
    m = MockLayer(mock_tools={"search"})
    args = {"q": "x"}
    key_hash = _hash_obj(args)
    m.register_tool("search", key_hash, {"results": [1, 2, 3]})
    result = m.call_tool(tool="search", args=args)
    assert result == {"results": [1, 2, 3]}


def test_mock_tool_not_in_set_raises():
    m = MockLayer(mock_tools={"search"})
    with pytest.raises(RuntimeError, match="not in mock_tools"):
        m.call_tool(tool="browser", args={})


def test_empty_mock_tools_set_blocks_all_tools():
    m = MockLayer(mock_tools=set())
    with pytest.raises(RuntimeError):
        m.call_tool(tool="x", args={})


def test_mock_layer_default_state():
    m = MockLayer()
    assert m.mock_llm is True
    assert m.mock_tools == set()
    assert m.llm_responses == {}
    assert m.tool_responses == {}
