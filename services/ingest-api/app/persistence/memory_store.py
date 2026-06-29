from __future__ import annotations

import asyncio
from typing import Any


class InMemoryStore:
    """Postgres stand-in for tests. Idempotent by (run_id, span_id)."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], dict] = {}
        self._lock = asyncio.Lock()

    def __bool__(self) -> bool:
        return True

    async def insert(self, event: dict) -> bool:
        key = (event["run_id"], event["span_id"])
        async with self._lock:
            if key in self._events:
                return False
            self._events[key] = event
            return True

    async def fetch_one(self, run_id: str, span_id: str) -> dict | None:
        return self._events.get((run_id, span_id))

    def all(self) -> list[dict]:
        return list(self._events.values())

    def __len__(self) -> int:
        return len(self._events)
