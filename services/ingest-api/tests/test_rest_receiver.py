from __future__ import annotations

from . import make_event


def test_healthz(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz(client):
    r = client.get("/v1/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_post_events_requires_auth(client):
    r = client.post("/v1/events", json=[make_event()])
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_MISSING"


def test_post_events_rejects_bad_token(client):
    r = client.post(
        "/v1/events",
        json=[make_event()],
        headers={"Authorization": "Bearer invalid"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "AUTH_FORBIDDEN"


def test_post_events_accepts_valid_batch(client, auth_headers, store):
    events = [make_event(span_id=f"0aaa1bb0c0ffee0{i}") for i in range(3)]
    r = client.post("/v1/events", json=events, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 3
    assert body["rejected"] == 0
    assert len(store) == 3


def test_post_events_partial_rejection(client, auth_headers, store, bus):
    good = make_event(span_id="0aaa1bb0c0ffeeaa")
    bad = {"run_id": "x", "span_id": "y", "type": "llm.call", "started_at": "2026-06-29T12:00:00Z", "payload": {}}
    r = client.post("/v1/events", json=[good, bad], headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert len(store) == 1
    assert len(bus.dlq) == 1


def test_post_events_idempotent(client, auth_headers, store):
    event = make_event()
    r1 = client.post("/v1/events", json=[event], headers=auth_headers)
    r2 = client.post("/v1/events", json=[event], headers=auth_headers)
    assert r1.json()["accepted"] == 1
    assert r2.json()["accepted"] == 0
    assert r2.json()["rejected"] == 1
    assert len(store) == 1


def test_post_events_emits_request_id_header(client, auth_headers):
    r = client.post("/v1/events", json=[make_event()], headers=auth_headers)
    assert "x-request-id" in r.headers


def test_post_events_emits_canonical_error_format(client, auth_headers):
    r = client.post("/v1/events", json=[{"bogus": "data"}], headers=auth_headers)
    body = r.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 1
    assert body["rejected_details"][0]["code"] == "SCHEMA_INVALID"
    assert "message" in body["rejected_details"][0]


def test_post_events_empty_body_returns_canonical_error(client, auth_headers):
    r = client.post("/v1/events", json=[], headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 0


def test_post_events_publishes_to_bus(client, auth_headers, bus):
    r = client.post("/v1/events", json=[make_event()], headers=auth_headers)
    assert r.json()["accepted"] == 1
    assert len(bus.by_topic("events.raw")) == 1


def test_post_traces_translates_otlp(client, auth_headers, store, bus):
    otlp = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "00112233445566778899aabbccddeeff",
                                "spanId": "0aaa1bb0c0ffee01",
                                "name": "llm.call",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000001000000000",
                                "attributes": [
                                    {"key": "genai.run.id", "value": {"stringValue": "019065a1-7c8e-7abc-9def-1234567890ab"}},
                                    {"key": "genai.agent.name", "value": {"stringValue": "planner"}},
                                    {"key": "genai.llm.model", "value": {"stringValue": "openai/gpt-4o-mini"}},
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    r = client.post("/v1/traces", json=otlp, headers=auth_headers)
    body = r.json()
    assert body["accepted"] == 1, f"details: {body}"
    assert len(store) == 1
    stored = store.all()[0]
    assert stored["type"] == "llm.call"
    assert stored["agent"] == "planner"
    assert stored["payload"]["model"] == "openai/gpt-4o-mini"


def test_pii_strict_mode_rejects(strict_client, auth_headers):
    event = make_event(
        payload={"model": "openai/gpt-4o-mini", "messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"},
        attributes={"pii.note": "contact user@example.com"},
    )
    r = strict_client.post("/v1/events", json=[event], headers=auth_headers)
    body = r.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 1
    assert "PII" in body["rejected_details"][0]["code"]


def test_pii_redact_mode_keeps_event(client, auth_headers, store):
    event = make_event(
        payload={"model": "openai/gpt-4o-mini", "messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"},
        attributes={"pii.note": "contact user@example.com"},
    )
    r = client.post("/v1/events", json=[event], headers=auth_headers)
    body = r.json()
    assert body["accepted"] == 1, f"details: {body}"
    stored = store.all()[0]
    assert "user@example.com" not in str(stored["attributes"])
    assert "[REDACTED:email]" in str(stored["attributes"])


def test_pii_redact_handles_nested(client, auth_headers, store):
    event = make_event(
        payload={"model": "openai/gpt-4o-mini", "messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"},
        attributes={"pii.email": "leak@example.com", "genai.run.id": "019065a1-7c8e-7abc-9def-1234567890ab"},
    )
    r = client.post("/v1/events", json=[event], headers=auth_headers)
    stored = store.all()[0]
    assert "leak@example.com" not in str(stored["attributes"])


def test_payload_validation_failure(client, auth_headers, bus):
    event = make_event(payload={"missing": "model"})
    r = client.post("/v1/events", json=[event], headers=auth_headers)
    body = r.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 1
    assert "SCHEMA_INVALID" in body["rejected_details"][0]["code"]


def test_size_limit_constant():
    from app.schemas import IngestRequest
    assert IngestRequest.model_fields["events"].metadata


def test_empty_batch(client, auth_headers):
    r = client.post("/v1/events", json=[], headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"accepted": 0, "rejected": 0, "rejected_details": []}
