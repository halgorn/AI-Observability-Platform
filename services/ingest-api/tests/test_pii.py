from __future__ import annotations

import pytest

from app.pii import redact, scan, walk


def test_scan_email():
    assert "email" in scan("contact user@example.com please")


def test_scan_cpf():
    assert "cpf" in scan("cpf 123.456.789-09")
    assert "cpf" in scan("12345678909")


def test_scan_credit_card():
    assert "credit_card" in scan("card 4111 1111 1111 1111")


def test_scan_no_pii():
    assert scan("hello world") == []


def test_walk_nested_dict():
    obj = {
        "payload": {"input": "user@example.com", "tool_args": "4111111111111111"},
        "attributes": {"env": "prod"},
    }
    hits = walk(obj)
    assert "email" in hits
    assert "credit_card" in hits


def test_walk_ignores_safe_keys():
    obj = {"agent": "planner", "tool": "browser.fetch", "version": "1.2.3"}
    assert walk(obj) == []


def test_walk_passes_through_generic_keys():
    obj = {"random_key": "user@example.com"}
    assert "email" in walk(obj)


def test_redact_replaces_email():
    out = redact_str_safe("contact user@example.com")
    assert "user@example.com" not in out
    assert "[REDACTED:email]" in out


def test_redact_preserves_structure():
    obj = {"payload": {"input": "user@example.com"}, "status": "ok"}
    out = redact(obj)
    assert out["status"] == "ok"
    assert "[REDACTED:email]" in out["payload"]["input"]


def test_redact_list():
    obj = {"items": ["a@b.com", "safe"]}
    out = redact(obj)
    assert "[REDACTED:email]" in out["items"][0]
    assert out["items"][1] == "safe"


def test_redact_idempotent():
    once = redact_str_safe("user@example.com")
    twice = redact_str_safe(once)
    assert once == twice


def redact_str_safe(s: str) -> str:
    from app.pii import redact_str
    return redact_str(s)
