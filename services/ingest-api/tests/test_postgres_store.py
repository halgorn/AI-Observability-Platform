"""Tests for Postgres adapter (mocked asyncpg pool)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.persistence.postgres.store import PostgresStore, _row_to_event


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock()
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def test_postgres_store_creates_schema_on_connect(monkeypatch, mock_pool):
    pool, conn = mock_pool
    fake_pg = MagicMock()
    fake_pg.create_pool = AsyncMock(return_value=pool)
    monkeypatch.setattr("asyncpg.create_pool", fake_pg.create_pool)
    store = PostgresStore("postgres://localhost/test")
    store._pool = pool
    asyncio_run(store._migrate())
    assert conn.execute.await_count >= 3
    all_sql = " ".join(c.args[0] for c in conn.execute.await_args_list)
    assert "CREATE TABLE IF NOT EXISTS events" in all_sql
    assert "CREATE TABLE IF NOT EXISTS runs" in all_sql
    assert "CREATE TABLE IF NOT EXISTS checkpoints" in all_sql


def test_postgres_store_insert_idempotent(monkeypatch, mock_pool):
    import asyncpg
    pool, conn = mock_pool

    async def _execute(*args, **kwargs):
        raise asyncpg.UniqueViolationError("dup")

    conn.execute.side_effect = _execute
    store = PostgresStore("postgres://localhost/test")
    store._pool = pool
    result = asyncio_run(store.insert({
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "started_at": "2026-06-29T12:00:00Z",
        "payload": {"model": "openai/gpt-4o-mini"},
    }))
    assert result is False


def test_postgres_store_insert_succeeds(monkeypatch, mock_pool):
    pool, conn = mock_pool
    conn.execute = AsyncMock(return_value=None)
    store = PostgresStore("postgres://localhost/test")
    store._pool = pool
    result = asyncio_run(store.insert({
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "started_at": "2026-06-29T12:00:00Z",
        "payload": {"model": "openai/gpt-4o-mini"},
        "org_id": "org_1",
    }))
    assert result is True


def test_row_to_event_handles_bytes():
    row = {
        "id": 1, "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": b"\x0a\xaa\x1b\xb0\xc0\xff\xee\x01\x00\x00\x00\x00\x00\x00\x00\x00",
        "parent_span_id": b"\x00" * 8,
        "type": "llm.call", "agent": "planner", "tool": None, "llm_model": "openai/gpt-4o-mini",
        "started_at": datetime(2026, 6, 29, 12, 0, 0),
        "ended_at": datetime(2026, 6, 29, 12, 0, 1),
        "duration_ms": 1000, "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001,
        "error_code": None, "payload": {"model": "x"}, "attributes": {},
        "org_id": "org_1",
    }
    e = _row_to_event(row)
    assert e["span_id"] == "0aaa1bb0c0ffee01" + "0000000000000000"
    assert e["parent_span_id"] is None
    assert e["cost_usd"] == 0.001


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
