from __future__ import annotations

import asyncio


class InMemoryBus:
    """Redpanda stand-in for tests. Captures published + DLQ messages."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.dlq: list[tuple[dict, dict]] = []
        self._lock = asyncio.Lock()

    def __bool__(self) -> bool:
        return True

    async def publish(self, topic: str, event: dict) -> None:
        async with self._lock:
            self.published.append((topic, event))

    async def publish_dlq(self, event: dict, error: dict) -> None:
        async with self._lock:
            self.dlq.append((event, error))

    def by_topic(self, topic: str) -> list[dict]:
        return [e for t, e in self.published if t == topic]
