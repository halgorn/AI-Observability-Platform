from __future__ import annotations

import time

import pytest

from app.auth import ServiceToken, TokenError, TokenStore, require_scope


def test_issue_and_verify_roundtrip():
    store = TokenStore(secret=b"s1")
    token = store.issue("org_1", ["ingest.write", "runs.read"], ttl_s=60)
    verified = store.verify(token)
    assert verified.org_id == "org_1"
    assert "ingest.write" in verified.scopes
    assert "runs.read" in verified.scopes


def test_verify_rejects_bad_signature():
    store = TokenStore(secret=b"s1")
    token = store.issue("org_1", ["ingest.write"], ttl_s=60)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(TokenError, match="signature|malformed"):
        store.verify(tampered)


def test_verify_rejects_expired():
    class FakeClock:
        def __init__(self): self.t = 1000.0
        def now(self): return self.t
    clock = FakeClock()
    store = TokenStore(secret=b"s1", clock=clock)
    token = store.issue("org_1", ["ingest.write"], ttl_s=1)
    clock.t = 2000.0
    with pytest.raises(TokenError, match="expired"):
        store.verify(token)


def test_verify_rejects_wrong_format():
    store = TokenStore(secret=b"s1")
    with pytest.raises(TokenError):
        store.verify("not-a-token")


def test_verify_rejects_empty():
    store = TokenStore(secret=b"s1")
    with pytest.raises(TokenError):
        store.verify("")


def test_require_scope_passes():
    token = ServiceToken("org_1", frozenset({"ingest.write"}), time.time() + 60, "t")
    require_scope(token, "ingest.write")


def test_require_scope_fails():
    token = ServiceToken("org_1", frozenset({"runs.read"}), time.time() + 60, "t")
    with pytest.raises(TokenError, match="missing scope"):
        require_scope(token, "ingest.write")
