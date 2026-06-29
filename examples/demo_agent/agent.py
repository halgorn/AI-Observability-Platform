"""Demo agent that exercises the AI Observability Platform.

Simulates a 3-step LangGraph-style agent that:
  1. planner.think (LLM call)
  2. tool.browser_fetch (tool call, can fail with TIMEOUT)
  3. handoff planner -> executor

Generates 8-10 events with realistic latency, cost, and one error.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
import uuid

from ai_obs import handoff, observe, run


@observe(agent="planner")
def think(question: str) -> dict:
    time.sleep(random.uniform(0.05, 0.15))
    return {"plan": f"1. search for {question!r}\n2. summarize top 3"}


@observe(tool="browser.fetch")
def fetch(url: str) -> str:
    time.sleep(random.uniform(0.1, 0.3))
    if random.random() < 0.15:
        raise TimeoutError(f"browser.fetch {url} exceeded 5s")
    return f"<html><body>Mock content for {url}</body></html>"


@observe(tool="search.web")
def search(query: str) -> list[dict]:
    time.sleep(random.uniform(0.05, 0.2))
    return [
        {"title": f"Result {i}", "url": f"https://example.com/{i}"} for i in range(3)
    ]


@observe(agent="executor")
def execute(plan: str) -> str:
    time.sleep(random.uniform(0.05, 0.1))
    return f"Executed: {plan}"


async def amain() -> str:
    question = "What is the capital of France?"
    with run(agent="orchestrator", input=question) as r:
        handoff(to="planner", payload={"step": 1}, reason="delegation")
        plan = think(question)
        handoff(to="executor", payload={"step": 2}, reason="delegation")
        try:
            html = fetch(f"https://en.wikipedia.org/wiki/{question.split()[-1]}")
            urls = search("Paris France capital")
            result = execute(plan["plan"])
        except TimeoutError:
            result = "executor fell back to cached answer"
    return f"run_id={r.run_id} result={result!r}"


def main():
    os.environ.setdefault("AI_OBS_INGEST_URL", os.environ.get("AI_OBS_INGEST_URL", "http://localhost:8000"))
    print(asyncio.run(amain()))


if __name__ == "__main__":
    main()
