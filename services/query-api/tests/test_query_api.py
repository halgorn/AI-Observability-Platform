"""Tests for query API (FastAPI in-process)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import TokenStore
from app.db.store import QueryStore
from app.main import create_app


class FakeQueryStore(QueryStore):
    def __init__(self):
        self._runs = [
            {
                "run_id": "019065a1-7c8e-7abc-9def-111111111111",
                "thread_id": "thr_1", "agent": "planner", "status": "failed",
                "started_at": "2026-06-29T12:00:00Z", "ended_at": "2026-06-29T12:00:05Z",
                "duration_ms": 5000, "total_steps": 12, "total_tokens": 1234,
                "total_cost_usd": 0.023, "input_hash": "sha256:abc", "output_hash": "sha256:def",
                "prompt_version": "v3.1.0", "parent_run_id": None, "tags": {},
            },
        ]
        self._events = {
            "019065a1-7c8e-7abc-9def-111111111111": [
                {"run_id": "019065a1-7c8e-7abc-9def-111111111111", "span_id": "aaa",
                 "parent_span_id": None, "type": "llm.call", "agent": "planner",
                 "llm_model": "openai/gpt-4o-mini",
                 "started_at": "2026-06-29T12:00:00Z", "ended_at": "2026-06-29T12:00:01Z",
                 "duration_ms": 1000, "tokens_in": 100, "tokens_out": 50,
                 "cost_usd": 0.001, "error_code": None, "payload": {"model": "openai/gpt-4o-mini"},
                 "attributes": {}},
                {"run_id": "019065a1-7c8e-7abc-9def-111111111111", "span_id": "bbb",
                 "parent_span_id": "aaa", "type": "tool.invoke", "agent": None,
                 "tool": "browser.fetch",
                 "started_at": "2026-06-29T12:00:01Z", "ended_at": "2026-06-29T12:00:02Z",
                 "duration_ms": 1000, "tokens_in": None, "tokens_out": None,
                 "cost_usd": None, "error_code": "TOOL_TIMEOUT", "payload": {},
                 "attributes": {}},
            ],
        }
        self._checkpoints = {
            "019065a1-7c8e-7abc-9def-111111111111": [
                {"step": 0, "state_hash": "sha256:abc", "thread_id": "thr_1", "saved_at": "2026-06-29T12:00:00Z"},
            ],
        }
        self._similar: list[dict] = []

    async def list_runs(self, org_id, **kwargs):
        agent = kwargs.get("agent")
        items = [r for r in self._runs if not agent or r["agent"] == agent]
        return items, None

    async def fetch_run_events(self, run_id, org_id):
        return self._events.get(run_id, [])

    async def fetch_checkpoints(self, run_id, org_id):
        return self._checkpoints.get(run_id, [])

    async def fetch_run_summary(self, run_id, org_id):
        for r in self._runs:
            if r["run_id"] == run_id:
                return r
        return None

    async def similar_runs(self, run_id, org_id, *, limit=10):
        return self._similar[:limit]

    async def fetch_handoffs(self, *, org_id, days, agent=None):
        events = self._events.get("019065a1-7c8e-7abc-9def-111111111111", [])
        return [e for e in events if e.get("type") == "handoff"]

    async def query_raw(self, sql):
        return [{"cost_usd_total": 0.5, "agent": "planner"}]

    async def connect(self): pass
    async def close(self): pass


@pytest.fixture
def fake_store():
    return FakeQueryStore()


@pytest.fixture
def token_store():
    return TokenStore(secret=b"test-secret")


@pytest.fixture
def auth_token(token_store):
    return token_store.issue("org_test", ["runs.read", "runs.replay"])


@pytest.fixture
def client(fake_store, token_store):
    app = create_app(store=fake_store, token_store=token_store)
    return TestClient(app)


def test_healthz(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200


def test_list_runs_requires_auth(client):
    r = client.get("/v1/runs")
    assert r.status_code == 401


def test_list_runs_returns_items(client, auth_token):
    r = client.get("/v1/runs", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["agent"] == "planner"
    assert body["items"][0]["status"] == "failed"


def test_list_runs_filter_by_agent(client, auth_token):
    r = client.get("/v1/runs?agent=planner", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_runs_filter_no_match(client, auth_token):
    r = client.get("/v1/runs?agent=nonexistent", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_get_run_returns_summary(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-111111111111",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["agent"] == "planner"


def test_get_run_404(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-999999999999",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 404


def test_get_trace_builds_tree(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-111111111111/trace",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total_events"] == 2
    assert len(body["roots"]) == 1
    assert len(body["roots"][0]["children"]) == 1


def test_get_events_returns_items(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-111111111111/events",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_get_checkpoints_returns_items(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-111111111111/checkpoints",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_get_similar_empty(client, auth_token):
    r = client.get("/v1/runs/019065a1-7c8e-7abc-9def-111111111111/similar",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_compare_runs(client, auth_token):
    r = client.post("/v1/compare",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    json={"run_a": "019065a1-7c8e-7abc-9def-111111111111",
                          "run_b": "019065a1-7c8e-7abc-9def-111111111111",
                          "dimension": "factuality"})
    assert r.status_code == 200
    body = r.json()
    assert "diff" in body
    assert body["diff"]["cost_usd"]["a"] >= 0
    assert "events_count" in body["diff"]


def test_compare_runs_requires_both(client, auth_token):
    r = client.post("/v1/compare",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    json={"run_a": "x"})
    assert r.status_code == 400


def test_handoffs_endpoint(client, auth_token):
    r = client.get("/v1/agents/handoffs?since=7d",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["since"] == "7d"


def test_cost_by_agent(client, auth_token):
    r = client.get("/v1/cost/by_agent?since=24h",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200


def test_cost_by_tool(client, auth_token):
    r = client.get("/v1/cost/by_tool?since=7d",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200


def test_cost_by_prompt(client, auth_token):
    r = client.get("/v1/cost/by_prompt?since=7d",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200


def test_cost_by_day(client, auth_token):
    r = client.get("/v1/cost/by_day?since=30d",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
