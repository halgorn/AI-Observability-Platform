from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class HealthCheck(Protocol):
    name: str
    async def check(self) -> tuple[bool, str | None]: ...


@dataclass
class CheckResult:
    name: str
    healthy: bool
    detail: str | None
    latency_ms: float


async def _check(name: str, coro_factory) -> CheckResult:
    start = time.perf_counter()
    try:
        healthy, detail = await asyncio.wait_for(coro_factory(), timeout=2.0)
        latency = (time.perf_counter() - start) * 1000
        return CheckResult(name, healthy, detail, latency)
    except asyncio.TimeoutError:
        return CheckResult(name, False, "timeout", 2000.0)
    except Exception as e:
        return CheckResult(name, False, str(e)[:100], (time.perf_counter() - start) * 1000)


class PostgresHealth:
    name = "postgres"

    def __init__(self, dsn: str | None) -> None:
        self.dsn = dsn or os.environ.get("POSTGRES_DSN")

    async def check(self) -> tuple[bool, str | None]:
        if not self.dsn:
            return True, "not configured"
        try:
            import asyncpg
            conn = await asyncpg.connect(self.dsn, timeout=2.0)
            try:
                val = await conn.fetchval("SELECT 1")
                return (val == 1), None
            finally:
                await conn.close()
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:80]}"


class RedisHealth:
    name = "redis"

    def __init__(self, url: str | None) -> None:
        self.url = url or os.environ.get("REDIS_URL")

    async def check(self) -> tuple[bool, str | None]:
        if not self.url:
            return True, "not configured"
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self.url, decode_responses=True, socket_timeout=2.0)
            try:
                pong = await r.ping()
                return (pong is True), None
            finally:
                await r.close()
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:80]}"


class KafkaHealth:
    name = "kafka"

    def __init__(self, brokers: str | None) -> None:
        self.brokers = brokers or os.environ.get("KAFKA_BROKERS")

    async def check(self) -> tuple[bool, str | None]:
        if not self.brokers:
            return True, "not configured"
        try:
            from aiokafka import AIOKafkaProducer
            producer = AIOKafkaProducer(bootstrap_servers=self.brokers, request_timeout_ms=2000)
            await producer.start()
            try:
                return True, None
            finally:
                await producer.stop()
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:80]}"


async def run_checks(checks: list[HealthCheck]) -> dict:
    results = await asyncio.gather(
        *[_check(c.name, c.check) for c in checks],
        return_exceptions=False,
    )
    overall = all(r.healthy for r in results)
    return {
        "status": "ok" if overall else "degraded",
        "checks": {
            r.name: {
                "healthy": r.healthy,
                "detail": r.detail,
                "latency_ms": round(r.latency_ms, 1),
            }
            for r in results
        },
    }
