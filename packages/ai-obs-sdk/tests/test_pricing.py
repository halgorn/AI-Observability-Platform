"""Tests for pricing table — mirror of specs/domains/06-cost.md §Pricing."""
from __future__ import annotations

import pytest

from ai_obs.pricing import PRICING, cost_of_call


def test_all_pricing_models_have_required_fields():
    for model, p in PRICING.items():
        assert "in" in p, f"missing 'in' for {model}"
        assert "out" in p, f"missing 'out' for {model}"
        assert "cache_in" in p, f"missing 'cache_in' for {model}"
        assert "since" in p, f"missing 'since' for {model}"


def test_cost_of_call_gpt4o_mini():
    cost = cost_of_call(model="openai/gpt-4o-mini", tokens_in=1_000_000, tokens_out=0)
    assert cost == pytest.approx(0.150, rel=1e-6)


def test_cost_of_call_gpt4o():
    cost = cost_of_call(model="openai/gpt-4o", tokens_in=0, tokens_out=1_000_000)
    assert cost == pytest.approx(10.000, rel=1e-6)


def test_cost_of_call_cached_uses_cache_rate():
    normal = cost_of_call(model="openai/gpt-4o-mini", tokens_in=1000, tokens_out=0, cached=False)
    cached = cost_of_call(model="openai/gpt-4o-mini", tokens_in=1000, tokens_out=0, cached=True)
    assert cached < normal
    assert cached == pytest.approx(normal / 2, rel=1e-6)


def test_cost_of_call_unknown_returns_none():
    assert cost_of_call(model="foo/bar", tokens_in=100, tokens_out=0) is None


def test_cost_of_call_zero_tokens():
    assert cost_of_call(model="openai/gpt-4o-mini", tokens_in=0, tokens_out=0) == 0.0
