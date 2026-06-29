"""Redpanda/Kafka bus — async producer with DLQ."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from .protocols import EventBus

logger = logging.getLogger(__name__)


class KafkaBus(EventBus):
    """Async producer that publishes to Redpanda/Kafka topics."""

    def __init__(self, *, bootstrap_servers: str, client_id: str = "ingest-api") -> None:
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self._producer: AIOKafkaProducer | None = None
        self._dlq_consumer: AIOKafkaConsumer | None = None
        self._stopped = False

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=self.client_id,
            enable_idempotence=True,
            acks="all",
        )
        await self._producer.start()

    async def close(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._producer is not None:
            await self._producer.stop()

    async def publish(self, topic: str, event: dict) -> None:
        if self._producer is None:
            await self.start()
        assert self._producer is not None
        try:
            await self._producer.send_and_wait(
                topic,
                json.dumps(event, default=str).encode(),
                key=event.get("run_id", "").encode() if event.get("run_id") else None,
            )
        except KafkaError as e:
            logger.warning("kafka publish failed: %s", e)

    async def publish_dlq(self, event: dict, error: dict) -> None:
        envelope = {"event": event, "error": error, "at": asyncio.get_event_loop().time()}
        await self.publish("events.dlq", envelope)
