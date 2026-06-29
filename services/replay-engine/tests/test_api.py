"""Tests for replay-engine API (in-process)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import TokenStore
from app.main import create_app
from app.store.memory import InMemorySessionStore
from app.engine import ReplayEngine


@pytest.fixture
def token_store():
    return TokenStore(secret=b"test-secret")


@pytest.fixture
def auth_token(token_store):
    return token_store.issue("org_test", ["runs.replay"])


@pytest.fixture
def client(token_store):
    app = create_app(token_store=token_store)
    engine = ReplayEngine()
    engine.load("019065a1-7c8e-7abc-9def-1234567890ab", [
        {"span_id": "e1", "type": "x", "duration_ms": 0,
         "started_at": "2026-06-29T12:00:00Z", "ended_at": None,
         "payload": {}, "attributes": {}},
        {"span_id": "e2", "type": "x", "duration_ms": 0,
         "started_at": "2026-06-29T12:00:01Z", "ended_at": None,
         "payload": {}, "attributes": {}},
    ], [])
    app.state.session_store.save(engine._sessions[list(engine._sessions.keys())[0]])
    app.state.engine = engine
    return TestClient(app)


def test_healthz(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200


def test_replay_requires_auth(client):
    r = client.post("/v1/runs/abc/replay")
    assert r.status_code == 401


def test_replay_invalid_token(client):
    r = client.post("/v1/runs/abc/replay", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 403


def test_step_requires_session(client, auth_token):
    r = client.post("/v1/replay/nonexistent/step?n=1", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 404


def test_status_requires_session(client, auth_token):
    r = client.get("/v1/replay/nonexistent/status", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 404
