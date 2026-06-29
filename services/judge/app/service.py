"""Judge service — LLM-as-judge async, with cache + multi-judge scoring.

Spec: specs/domains/07-judge.md
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from .cache import Cache, InMemoryCache, make_key
from .prompts import get_prompt, list_dimensions

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    model: str
    dimension: str
    score: float
    rationale: str
    cache_hit: bool
    prompt_version: str
    raw: dict | None = None

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "dimension": self.dimension,
            "score": self.score,
            "rationale": self.rationale,
            "cache_hit": self.cache_hit,
            "prompt_version": self.prompt_version,
        }


class JudgeClient(Protocol):
    async def complete(self, *, model: str, system: str, user: str, temperature: float = 0.0) -> str: ...


class StubJudgeClient:
    """For tests and dev: returns deterministic score based on input length."""

    async def complete(self, *, model: str, system: str, user: str, temperature: float = 0.0) -> str:
        score = min(1.0, max(0.0, len(user) % 100 / 100))
        return json.dumps({"score": score, "rationale": f"stub: {len(user)} chars"})


class OpenAIJudgeClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, *, model: str, system: str, user: str, temperature: float = 0.0) -> str:
        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=200,
        )
        return resp.choices[0].message.content or ""


class JudgeService:
    def __init__(
        self,
        *,
        client: JudgeClient | None = None,
        cache: Cache | None = None,
        model: str = "openai/gpt-4o-mini",
        n_judges: int = 3,
    ) -> None:
        self.client = client or StubJudgeClient()
        self.cache = cache or InMemoryCache()
        self.model = model
        self.n_judges = n_judges

    async def judge(
        self,
        *,
        input: str,
        output: str,
        dimension: str = "factuality",
        prompt_version: str = "v1",
    ) -> JudgeResult:
        prompt = get_prompt(dimension, version=prompt_version)
        user = prompt.format(input=input, output=output)
        key = make_key(model=self.model, input=input, output=output, dimension=dimension)
        cached = await self.cache.get(key)
        if cached is not None:
            return JudgeResult(
                model=self.model, dimension=dimension,
                score=cached["score"], rationale=cached["rationale"],
                cache_hit=True, prompt_version=prompt_version, raw=cached,
            )
        results = await asyncio.gather(*[
            self._call_judge(user) for _ in range(self.n_judges)
        ], return_exceptions=True)
        scores = [r["score"] for r in results if isinstance(r, dict)]
        rationales = [r.get("rationale", "") for r in results if isinstance(r, dict)]
        if not scores:
            raise RuntimeError("all judge calls failed")
        avg = sum(scores) / len(scores)
        if len(scores) > 1:
            stddev = (sum((s - avg) ** 2 for s in scores) / len(scores)) ** 0.5
            score = avg
            if stddev > 0.3:
                logger.warning("judge disagreement dimension=%s stddev=%.2f", dimension, stddev)
        else:
            score = avg
        rationale = rationales[0] if rationales else ""
        result = {"score": score, "rationale": rationale}
        await self.cache.set(key, result)
        return JudgeResult(
            model=self.model, dimension=dimension,
            score=score, rationale=rationale,
            cache_hit=False, prompt_version=prompt_version, raw=result,
        )

    async def _call_judge(self, user: str) -> dict:
        try:
            raw = await self.client.complete(
                model=self.model,
                system="You are an objective evaluator. Always respond with valid JSON only.",
                user=user,
            )
        except Exception as e:
            logger.warning("judge call failed: %s", e)
            return {"score": 0.5, "rationale": f"error: {type(e).__name__}"}
        return _parse_json_response(raw)

    async def compare_runs(
        self,
        *,
        run_a: dict,
        run_b: dict,
        dimension: str = "factuality",
    ) -> dict:
        a = await self.judge(input=run_a.get("input", ""), output=run_a.get("output", ""), dimension=dimension)
        b = await self.judge(input=run_b.get("input", ""), output=run_b.get("output", ""), dimension=dimension)
        return {
            "dimension": dimension,
            "a": a.to_dict(),
            "b": b.to_dict(),
            "delta": b.score - a.score,
            "winner": "b" if b.score > a.score else "a" if a.score > b.score else "tie",
        }


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = _JSON_RE.search(raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"score": 0.5, "rationale": "unparseable response"}
