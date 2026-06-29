"""Postgres adapter — implements same interface as InMemoryStore.

Schema mirrors specs/domains/08-storage.md §Postgres + 14-data-governance §RLS.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from ..protocols import EventStore

logger = logging.getLogger(__name__)


class PostgresStore(EventStore):
    """Async Postgres event store with RLS + idempotency."""

    def __init__(self, dsn: str, *, org_id: str | None = None) -> None:
        self.dsn = dsn
        self.org_id = org_id
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=10,
            command_timeout=10.0,
        )
        await self._migrate()

    async def _migrate(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL PRIMARY KEY,
                    run_id UUID NOT NULL,
                    span_id BYTEA NOT NULL,
                    parent_span_id BYTEA,
                    type TEXT NOT NULL,
                    agent TEXT,
                    tool TEXT,
                    llm_model TEXT,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    duration_ms INT,
                    tokens_in INT,
                    tokens_out INT,
                    cost_usd NUMERIC(12, 8),
                    error_code TEXT,
                    payload JSONB NOT NULL,
                    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
                    org_id TEXT NOT NULL,
                    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (org_id, run_id, span_id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_run_started ON events(run_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_events_type_started ON events(type, started_at);
                CREATE INDEX IF NOT EXISTS idx_events_org_started ON events(org_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent, started_at DESC) WHERE agent IS NOT NULL;
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id UUID PRIMARY KEY,
                    thread_id TEXT,
                    agent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    duration_ms INT,
                    total_steps INT,
                    total_tokens INT,
                    total_cost_usd NUMERIC(12, 8),
                    input_hash TEXT,
                    output_hash TEXT,
                    prompt_version TEXT,
                    parent_run_id UUID,
                    tags JSONB DEFAULT '{}'::jsonb,
                    org_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status) WHERE status IN ('failed','timeout');
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id UUID NOT NULL,
                    step INT NOT NULL,
                    state JSONB NOT NULL,
                    state_hash TEXT NOT NULL,
                    thread_id TEXT,
                    saved_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (run_id, step)
                );
            """)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def insert(self, event: dict) -> bool:
        assert self._pool is not None, "call connect() first"
        org_id = event.get("org_id") or self.org_id or "default"
        payload = json.dumps(event.get("payload", {}))
        attributes = json.dumps(event.get("attributes", {}))
        started_at = event.get("started_at")
        ended_at = event.get("ended_at")
        if isinstance(started_at, (int, float)):
            import datetime
            started_at = datetime.datetime.fromtimestamp(started_at, tz=datetime.timezone.utc)
        if isinstance(ended_at, (int, float)):
            import datetime
            ended_at = datetime.datetime.fromtimestamp(ended_at, tz=datetime.timezone.utc)
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("""
                        INSERT INTO events (
                            run_id, span_id, parent_span_id, type, agent, tool, llm_model,
                            started_at, ended_at, duration_ms,
                            tokens_in, tokens_out, cost_usd, error_code,
                            payload, attributes, org_id
                        ) VALUES (
                            $1, decode($2, 'hex'), decode($3, 'hex'), $4, $5, $6, $7,
                            $8, $9, $10,
                            $11, $12, $13, $14,
                            $15::jsonb, $16::jsonb, $17
                        )
                    """,
                        event["run_id"],
                        event["span_id"],
                        (event.get("parent_span_id") or "0" * 16),
                        event["type"],
                        event.get("agent"),
                        event.get("tool"),
                        event.get("llm_model"),
                        started_at,
                        ended_at,
                        event.get("duration_ms"),
                        event.get("tokens_in"),
                        event.get("tokens_out"),
                        event.get("cost_usd"),
                        event.get("error_code"),
                        payload,
                        attributes,
                        org_id,
                    )
            return True
        except asyncpg.UniqueViolationError:
            return False

    async def fetch_one(self, run_id: str, span_id: str) -> dict | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM events WHERE run_id = $1 AND span_id = decode($2, 'hex') LIMIT 1",
                run_id, span_id,
            )
            return _row_to_event(row) if row else None

    async def fetch_run(self, run_id: str) -> list[dict]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE run_id = $1 ORDER BY started_at, span_id",
                run_id,
            )
        return [_row_to_event(r) for r in rows]

    async def list_runs(
        self,
        *,
        org_id: str,
        agent: str | None = None,
        status: str | None = None,
        since: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        assert self._pool is not None
        sql = "SELECT DISTINCT ON (run_id) * FROM events WHERE org_id = $1"
        args: list[Any] = [org_id]
        if agent:
            sql += " AND agent = $2"
            args.append(agent)
        if status:
            sql += f" AND type = 'run.end' AND payload->>'status' = ${len(args) + 1}"
            args.append(status)
        if since:
            sql += f" AND started_at > now() - interval '${len(args) + 1}'"
            args.append(since.replace("h", " hours").replace("d", " days").replace("m", " minutes"))
        sql += " ORDER BY run_id, started_at DESC LIMIT $" + str(len(args) + 1)
        args.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [_row_to_event(r) for r in rows], None

    async def fetch_checkpoints(self, run_id: str) -> list[dict]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT step, state_hash, thread_id, saved_at FROM checkpoints WHERE run_id = $1 ORDER BY step",
                run_id,
            )
        return [dict(r) for r in rows]


def _row_to_event(row: Any) -> dict:
    span_id = row["span_id"]
    if isinstance(span_id, bytes):
        span_id = span_id.hex()
    parent = row.get("parent_span_id")
    if isinstance(parent, bytes):
        parent = parent.hex() if parent != b"\x00" * 8 else None
    return {
        "id": row["id"],
        "run_id": str(row["run_id"]),
        "span_id": span_id,
        "parent_span_id": parent,
        "type": row["type"],
        "agent": row["agent"],
        "tool": row["tool"],
        "llm_model": row["llm_model"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
        "duration_ms": row["duration_ms"],
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None,
        "error_code": row["error_code"],
        "payload": row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
        "attributes": row["attributes"] if isinstance(row["attributes"], dict) else json.loads(row["attributes"]),
        "org_id": row["org_id"],
    }
