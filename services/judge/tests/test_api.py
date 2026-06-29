"""Tests for judge API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth_compat import TokenStore
from app.cache import InMemoryCache
from app.main import create_app
from app.service import JudgeService, StubJudgeClient


@pytest.fixture
def service():
    return JudgeService(client=StubJudgeClient(), cache=InMemoryCache(), n_judges=1)


@pytest.fixture
def client(service):
    app = create_app(judge=service, token_store=TokenStore(secret=b"test"))
    return TestClient(app)


@pytest.fixture
def auth_token():
    return TokenStore(secret=b"test").issue("org_test", ["judge.write"])


def test_healthz(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200


def test_score_requires_auth(client):
    r = client.post("/v1/score", json={"run_id": "r1", "input": "a", "output": "b"})
    assert r.status_code == 401


def test_score_requires_input_output(client, auth_token):
    r = client.post("/v1/score", json={"run_id": "r1", "input": "", "output": "b"},
                    headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 400


def test_score_creates_job(client, auth_token):
    r = client.post("/v1/score",
                    json={"run_id": "r1", "input": "hello", "output": "world",
                          "dimensions": ["factuality", "relevance"]},
                    headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("queued", "running", "done")
    assert body["dimensions"] == ["factuality", "relevance"]


def test_score_then_get_job(client, auth_token):
    r = client.post("/v1/score",
                    json={"run_id": "r1", "input": "hello", "output": "world",
                          "dimensions": ["factuality"]},
                    headers={"Authorization": f"Bearer {auth_token}"})
    job_id = r.json()["job_id"]
    r2 = client.get(f"/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {auth_token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id


def test_get_job_404(client, auth_token):
    r = client.get("/v1/jobs/nonexistent",
                   headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 404


def test_compare_runs(client, auth_token):
    r = client.post("/v1/compare",
                    json={"run_a": {"input": "a", "output": "x"}, "run_b": {"input": "a", "output": "y"}},
                    headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    body = r.json()
    assert "delta" in body
    assert "winner" in body
