"""Tests for JudgeService."""
from __future__ import annotations

import json

import pytest

from app.cache import InMemoryCache, make_key
from app.prompts import list_dimensions, get_prompt
from app.service import (
    JudgeResult, JudgeService, StubJudgeClient, _parse_json_response, OpenAIJudgeClient,
)


def test_stub_judge_returns_deterministic():
    c = StubJudgeClient()
    import asyncio
    out = asyncio.run(c.complete(model="x", system="s", user="hello world"))
    assert "score" in out


def test_parse_json_response_valid():
    assert _parse_json_response('{"score": 0.5, "rationale": "ok"}') == {"score": 0.5, "rationale": "ok"}


def test_parse_json_response_with_surrounding_text():
    out = _parse_json_response('Here is my answer: {"score": 0.7, "rationale": "good"}')
    assert out["score"] == 0.7


def test_parse_json_response_unparseable():
    out = _parse_json_response("not json at all")
    assert out["score"] == 0.5
    assert "unparseable" in out["rationale"]


def test_make_key_deterministic():
    k1 = make_key(model="gpt-4o-mini", input="a", output="b", dimension="factuality")
    k2 = make_key(model="gpt-4o-mini", input="a", output="b", dimension="factuality")
    assert k1 == k2
    assert k1.startswith("judge:")


def test_make_key_differs_by_input():
    k1 = make_key(model="x", input="a", output="b", dimension="d")
    k2 = make_key(model="x", input="a2", output="b", dimension="d")
    assert k1 != k2


def test_make_key_differs_by_dimension():
    k1 = make_key(model="x", input="a", output="b", dimension="d1")
    k2 = make_key(model="x", input="a", output="b", dimension="d2")
    assert k1 != k2


def test_cache_set_get():
    c = InMemoryCache()
    import asyncio
    assert asyncio.run(c.get("k")) is None
    asyncio.run(c.set("k", {"x": 1}))
    assert asyncio.run(c.get("k")) == {"x": 1}


def test_judge_returns_cached():
    cache = InMemoryCache()
    service = JudgeService(client=StubJudgeClient(), cache=cache, n_judges=1)
    import asyncio
    r1 = asyncio.run(service.judge(input="a", output="b", dimension="factuality"))
    r2 = asyncio.run(service.judge(input="a", output="b", dimension="factuality"))
    assert r1.cache_hit is False
    assert r2.cache_hit is True
    assert r1.score == r2.score


def test_judge_averages_n_judges():
    service = JudgeService(client=StubJudgeClient(), cache=InMemoryCache(), n_judges=3)
    import asyncio
    r = asyncio.run(service.judge(input="a", output="b"))
    assert 0 <= r.score <= 1


def test_judge_with_unknown_dimension_raises():
    service = JudgeService(client=StubJudgeClient(), cache=InMemoryCache(), n_judges=1)
    import asyncio
    with pytest.raises(KeyError):
        asyncio.run(service.judge(input="a", output="b", dimension="nonexistent"))


def test_judge_prompt_version_used():
    service = JudgeService(client=StubJudgeClient(), cache=InMemoryCache(), n_judges=1)
    import asyncio
    r = asyncio.run(service.judge(input="a", output="b", dimension="factuality", prompt_version="v1"))
    assert r.prompt_version == "v1"


def test_compare_runs_returns_delta_and_winner():
    service = JudgeService(client=StubJudgeClient(), cache=InMemoryCache(), n_judges=1)
    import asyncio
    a_in, a_out = "short", "a" * 10
    b_in, b_out = "short", "b" * 90
    result = asyncio.run(service.compare_runs(
        run_a={"input": a_in, "output": a_out},
        run_b={"input": b_in, "output": b_out},
        dimension="factuality",
    ))
    assert "delta" in result
    assert result["winner"] in ("a", "b", "tie")


def test_list_dimensions_returns_all():
    dims = list_dimensions()
    assert "factuality" in dims
    assert "relevance" in dims
    assert "harmfulness" in dims
    assert "coherence" in dims
    assert "completeness" in dims


def test_get_prompt_returns_template():
    p = get_prompt("factuality")
    assert "{input}" in p
    assert "{output}" in p


def test_get_prompt_unknown_dimension_raises():
    with pytest.raises(KeyError):
        get_prompt("nonexistent")


def test_openai_client_imports():
    c = OpenAIJudgeClient(api_key="test-key")
    assert c._client is not None
