"""ClickHouse mirror — receives events from Redpanda, writes to columnar store.

Specs/domains/08-storage.md §ClickHouse:
  PARTITION BY toYYYYMM(started_at)
  ORDER BY (run_id, started_at, span_id)
  TTL started_at + INTERVAL 1 YEAR
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)


class ClickHouseMirror:
    """Consumes events from Redpanda and writes to ClickHouse."""

    def __init__(self, *, bootstrap_servers: str, clickhouse_url: str, topic: str = "events.raw", group_id: str = "ch-mirror") -> None:
        self.bootstrap_servers = bootstrap_servers
        self.clickhouse_url = clickhouse_url
        self.topic = topic
        self.group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._stopped = False

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        await self._ensure_table()
        asyncio.create_task(self._run())

    async def _ensure_table(self) -> None:
        try:
            from aioch import Client
            client = Client(self.clickhouse_url)
            await client.execute("""
                CREATE TABLE IF NOT EXISTS events_ch (
                    id UInt64,
                    run_id UUID,
                    span_id FixedString(16),
                    parent_span_id Nullable(FixedString(16)),
                    type LowCardinality(String),
                    agent LowCardinality(String),
                    tool LowCardinality(String),
                    llm_model LowCardinality(String),
                    duration_ms UInt32,
                    tokens_in UInt32,
                    tokens_out UInt32,
                    cost_usd Float64,
                    error_code LowCardinality(String),
                    started_at DateTime64(9),
                    payload String CODEC(ZSTD(3)),
                    attributes String CODEC(ZSTD(3)),
                    org_id LowCardinality(String)
                ) ENGINE = MergeTree
                PARTITION BY toYYYYMM(started_at)
                ORDER BY (run_id, started_at, span_id)
                TTL started_at + INTERVAL 1 YEAR
            """)
        except ImportError:
            logger.warning("aioch not installed; ClickHouse mirror disabled")
        except Exception as e:
            logger.warning("ClickHouse schema setup failed: %s", e)

    async def _run(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                if self._stopped:
                    break
                try:
                    event = json.loads(msg.value)
                    await self._insert(event)
                except Exception as e:
                    logger.warning("mirror insert failed: %s", e)
        except KafkaError as e:
            logger.warning("kafka consumer error: %s", e)

    async def _insert(self, event: dict) -> None:
        try:
            from aioch import Client
            client = Client(self.clickhouse_url)
            span_id = (event.get("span_id") or "0" * 16).ljust(16, "0")[:16]
            parent = event.get("parent_span_id")
            await client.execute(
                "INSERT INTO events_ch (id, run_id, span_id, parent_span_id, type, agent, tool, llm_model, "
                "duration_ms, tokens_in, tokens_out, cost_usd, error_code, started_at, payload, attributes, org_id) VALUES",
                [[
                    event.get("id", 0),
                    event["run_id"],
                    span_id,
                    parent,
                    event.get("type", "step.start"),
                    event.get("agent") or "",
                    event.get("tool") or "",
                    event.get("llm_model") or "",
                    event.get("duration_ms") or 0,
                    event.get("tokens_in") or 0,
                    event.get("tokens_out") or 0,
                    event.get("cost_usd") or 0.0,
                    event.get("error_code") or "",
                    _parse_ts(event.get("started_at")),
                    json.dumps(event.get("payload", {})),
                    json.dumps(event.get("attributes", {})),
                    event.get("org_id", "default"),
                ]]
            )
        except Exception as e:
            logger.warning("ClickHouse insert failed: %s", e)

    async def stop(self) -> None:
        self._stopped = True
        if self._consumer is not None:
            await self._consumer.stop()


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()
    return datetime.utcnow()
