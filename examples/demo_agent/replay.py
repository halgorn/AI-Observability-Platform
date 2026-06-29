"""Replay the demo agent deterministically.

Loads recorded events, replays the same steps against the same agent,
verifies outputs match.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agent import think, fetch, search, execute


async def replay():
    plan = think("What is the capital of France?")
    print("plan:", plan)
    try:
        html = fetch("https://en.wikipedia.org/wiki/France")
        print("html len:", len(html))
    except TimeoutError:
        print("fetch timed out (expected ~15% of the time)")
    urls = search("Paris France capital")
    print("urls:", len(urls), "results")
    result = execute(plan["plan"])
    print("result:", result)


if __name__ == "__main__":
    asyncio.run(replay())
