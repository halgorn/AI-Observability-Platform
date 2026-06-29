from __future__ import annotations

import pytest

from app.auth import TokenStore
from app.main import create_app
from app.persistence.memory_bus import InMemoryBus
from app.persistence.memory_store import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def bus() -> InMemoryBus:
    return InMemoryBus()


@pytest.fixture
def token_store() -> TokenStore:
    return TokenStore(secret=b"test-secret")


@pytest.fixture
def auth_token(token_store: TokenStore) -> str:
    return token_store.issue("org_test", ["ingest.write"], ttl_s=3600)


@pytest.fixture
def app(store, bus, token_store):
    return create_app(store=store, bus=bus, token_store=token_store, pii_mode="redact")


@pytest.fixture
def strict_app(store, bus, token_store):
    return create_app(store=store, bus=bus, token_store=token_store, pii_mode="strict")


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def strict_client(strict_app):
    from fastapi.testclient import TestClient
    return TestClient(strict_app)


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def make_event(**overrides) -> dict:
    base = {
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "agent": "planner",
        "llm_model": "openai/gpt-4o-mini",
        "started_at": "2026-06-29T12:00:00.000Z",
        "ended_at": "2026-06-29T12:00:01.234Z",
        "duration_ms": 1234,
        "tokens_in": 342,
        "tokens_out": 128,
        "cost_usd": 0.000128,
        "payload": {
            "model": "openai/gpt-4o-mini",
            "messages_hash": "sha256:" + "0" * 64,
            "messages_size": 8421,
            "finish_reason": "stop",
            "system_prompt_version": "v3.1.0",
            "cache_hit": False,
            "stream": False,
        },
        "attributes": {"genai.run.id": "019065a1-7c8e-7abc-9def-1234567890ab"},
    }
    base.update(overrides)
    return base
