from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ServiceToken:
    org_id: str
    scopes: frozenset[str]
    expires_at: float
    name: str


class TokenError(Exception):
    pass


class _Clock(Protocol):
    def now(self) -> float: ...


class _WallClock:
    def now(self) -> float:
        return time.time()


class TokenStore:
    """Service token store. Production: backed by Postgres `service_tokens` (PRD §11-auth).

    Format: `ai_obs_v1.<b64(payload)>.<sig>` where:
      payload = JSON {org_id, scopes[], exp, name}
      sig = HMAC-SHA256(secret, b64_payload)[:32]
    """

    def __init__(self, secret: bytes | None = None, clock: _Clock | None = None) -> None:
        self.secret = secret or os.environ.get("INGEST_API_SECRET", "dev-secret-do-not-use-in-prod").encode()
        self.clock = clock or _WallClock()
        self._issued: dict[str, ServiceToken] = {}

    def __bool__(self) -> bool:
        return True

    def issue(self, org_id: str, scopes: list[str], ttl_s: int = 3600, name: str = "default") -> str:
        expires_at = self.clock.now() + ttl_s
        payload = json.dumps(
            {"org_id": org_id, "scopes": sorted(scopes), "exp": int(expires_at), "name": name},
            separators=(",", ":"),
        ).encode()
        b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        sig = hmac.new(self.secret, b64.encode(), hashlib.sha256).hexdigest()[:32]
        token = f"ai_obs_v1.{b64}.{sig}"
        self._issued[token] = ServiceToken(org_id, frozenset(scopes), float(expires_at), name)
        return token

    def verify(self, token: str) -> ServiceToken:
        if not token or not token.startswith("ai_obs_v1."):
            raise TokenError("invalid token format")
        try:
            _, b64, sig = token.split(".", 2)
        except ValueError as e:
            raise TokenError(f"malformed token: {e}") from e
        expected = hmac.new(self.secret, b64.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            raise TokenError("invalid signature")
        try:
            padded = b64 + "=" * (-len(b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
        except Exception as e:
            raise TokenError(f"invalid payload: {e}") from e
        if self.clock.now() > payload["exp"]:
            raise TokenError("token expired")
        return ServiceToken(
            org_id=payload["org_id"],
            scopes=frozenset(payload["scopes"]),
            expires_at=float(payload["exp"]),
            name=payload.get("name", "verified"),
        )


def require_scope(token: ServiceToken, scope: str) -> None:
    if scope not in token.scopes:
        raise TokenError(f"missing scope: {scope}")
