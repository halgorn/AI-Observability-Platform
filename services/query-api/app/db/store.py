"""Postgres-backed query store with RLS.

Implements list_runs, fetch_run (events), build_trace (tree), checkpoints,
similar_runs (pgvector), and compare_runs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)


class QueryStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=10, command_timeout=10.0,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def list_runs(
        self,
        org_id: str,
        *,
        agent: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        assert self._pool is not None
        sql = """
            SELECT r.* FROM runs r
            WHERE r.org_id = $1
        """
        args: list[Any] = [org_id]
        if agent:
            sql += f" AND r.agent = ${len(args) + 1}"
            args.append(agent)
        if status:
            sql += f" AND r.status = ${len(args) + 1}"
            args.append(status)
        if since:
            sql += f" AND r.started_at > now() - interval '${len(args) + 1}'"
            args.append(since)
        if cursor:
            try:
                from base64 import urlsafe_b64decode
                ts_str, run_id = urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
                sql += f" AND (r.started_at, r.run_id) < (${len(args) + 1}::timestamptz, ${len(args) + 2}::uuid)"
                args.extend([ts_str, run_id])
            except Exception as e:
                logger.warning("bad cursor: %s", e)
        sql += " ORDER BY r.started_at DESC, r.run_id DESC"
        sql += f" LIMIT {limit + 1}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        items = [dict(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            from base64 import urlsafe_b64encode
            next_cursor = urlsafe_b64encode(
                f"{last['started_at'].isoformat()}|{last['run_id']}".encode()
            ).rstrip(b"=").decode()
        return items, next_cursor

    async def fetch_run_events(self, run_id: str, org_id: str) -> list[dict]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE run_id = $1 AND org_id = $2 ORDER BY started_at, span_id",
                run_id, org_id,
            )
        return [_row_to_event(r) for r in rows]

    async def fetch_checkpoints(self, run_id: str, org_id: str) -> list[dict]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT step, state_hash, thread_id, saved_at FROM checkpoints WHERE run_id = $1 ORDER BY step",
                run_id,
            )
        return [dict(r) for r in rows]

    async def fetch_run_summary(self, run_id: str, org_id: str) -> Optional[dict]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM runs WHERE run_id = $1 AND org_id = $2", run_id, org_id,
            )
        return dict(row) if row else None

    async def similar_runs(
        self, run_id: str, org_id: str, *, limit: int = 10,
    ) -> list[dict]:
        """Requires pgvector extension + run_embeddings table.

        Falls back to empty list if extension not present.
        """
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT a.run_id, a.agent, a.started_at,
                           1 - (a.embedding <=> b.embedding) AS similarity
                    FROM run_embeddings a
                    JOIN run_embeddings b ON b.run_id = $1
                    WHERE a.run_id != $1 AND a.org_id = $2
                    ORDER BY a.embedding <=> b.embedding
                    LIMIT $3
                    """,
                    run_id, org_id, limit,
                )
                return [dict(r) for r in rows]
            except asyncpg.UndefinedTableError:
                return []
            except asyncpg.UndefinedFunctionError:
                return []

    async def fetch_handoffs(self, *, org_id: str, days: int, agent: Optional[str] = None) -> list[dict]:
        assert self._pool is not None
        sql = "SELECT * FROM events WHERE org_id = $1 AND type = 'handoff' AND started_at > now() - interval '%d days'" % days
        args: list = [org_id]
        if agent:
            sql += " AND agent = $2"
            args.append(agent)
        sql += " ORDER BY started_at DESC"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [_row_to_event(r) for r in rows]

    async def query_raw(self, sql: str) -> list[dict]:
        """Run a raw SQL against the configured backend.

        For Postgres: returns rows.
        For ClickHouse (via mirror): not implemented yet — use Postgres.
        """
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]


def _row_to_event(row: Any) -> dict:
    span_id = row["span_id"]
    if isinstance(span_id, (bytes, memoryview)):
        span_id = bytes(span_id).hex()
    parent = row.get("parent_span_id")
    if isinstance(parent, (bytes, memoryview)):
        parent = bytes(parent).hex() if bytes(parent) != b"\x00" * 8 else None
    return {
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
    }
