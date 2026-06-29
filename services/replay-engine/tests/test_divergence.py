"""Tests for divergence detection."""
from __future__ import annotations

from app.divergence import check_divergence


def test_llm_no_divergence_same_output():
    result = check_divergence(
        original={"model": "openai/gpt-4o-mini", "output": "hello"},
        replayed={"model": "openai/gpt-4o-mini", "output": "hello"},
        kind="llm",
    )
    assert result is None


def test_llm_diverges_on_output():
    result = check_divergence(
        original={"model": "openai/gpt-4o-mini", "output": "hello"},
        replayed={"model": "openai/gpt-4o-mini", "output": "goodbye"},
        kind="llm",
    )
    assert result is not None
    assert "output" in result


def test_llm_diverges_on_model_change():
    result = check_divergence(
        original={"model": "openai/gpt-4o", "output": "hi"},
        replayed={"model": "anthropic/claude", "output": "hi"},
        kind="llm",
    )
    assert result is not None
    assert "model" in result


def test_tool_no_divergence_same_args():
    result = check_divergence(
        original={"tool": "search", "args_hash": "sha256:abc"},
        replayed={"tool": "search", "args_hash": "sha256:abc"},
        kind="tool",
    )
    assert result is None


def test_tool_diverges_on_args_hash():
    result = check_divergence(
        original={"tool": "search", "args_hash": "sha256:abc"},
        replayed={"tool": "search", "args_hash": "sha256:def"},
        kind="tool",
    )
    assert result is not None
    assert "args" in result


def test_tool_diverges_on_name():
    result = check_divergence(
        original={"tool": "search", "args_hash": "sha256:abc"},
        replayed={"tool": "browser", "args_hash": "sha256:abc"},
        kind="tool",
    )
    assert result is not None
    assert "tool" in result


def test_handoff_no_divergence():
    result = check_divergence(
        original={"from": "planner", "to": "executor"},
        replayed={"from": "planner", "to": "executor"},
        kind="handoff",
    )
    assert result is None


def test_handoff_diverges_on_target():
    result = check_divergence(
        original={"from": "planner", "to": "executor"},
        replayed={"from": "planner", "to": "reviewer"},
        kind="handoff",
    )
    assert result is not None
    assert "to" in result
