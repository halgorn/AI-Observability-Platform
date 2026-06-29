"""Judge cache — sha256(model || input || output) → JudgeResult."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> Optional[dict]: ...
    async def set(self, key: str, value: dict, ttl_s: int = 30 * 86400) -> None: ...


def make_key(*, model: str, input: str, output: str, dimension: str) -> str:
    blob = json.dumps(
        {"model": model, "input": input, "output": output, "dimension": dimension},
        sort_keys=True,
        default=str,
    ).encode()
    return "judge:" + hashlib.sha256(blob).hexdigest()


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def get(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    async def set(self, key: str, value: dict, ttl_s: int = 30 * 86400) -> None:
        self._store[key] = value


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(url, decode_responses=True)
        self._client.ping()

    async def get(self, key: str) -> Optional[dict]:
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: dict, ttl_s: int = 30 * 86400) -> None:
        await self._client.set(key, json.dumps(value, default=str), ex=ttl_s)
