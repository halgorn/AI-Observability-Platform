"""Auth — same service token model as ingest-api."""
from __future__ import annotations

import hashlib
import hmac
import json
import base64
import os
import time
from dataclasses import dataclass


@dataclass
class ServiceToken:
    org_id: str
    scopes: frozenset
    expires_at: float
    name: str


class TokenError(Exception):
    pass


class TokenStore:
    def __init__(self, secret: bytes | None = None) -> None:
        self.secret = secret or os.environ.get("INGEST_API_SECRET", "dev-secret-do-not-use-in-prod").encode()
        self._issued: dict[str, ServiceToken] = {}

    def __bool__(self) -> bool:
        return True

    def issue(self, org_id: str, scopes: list[str], ttl_s: int = 3600, name: str = "default") -> str:
        expires_at = time.time() + ttl_s
        payload = json.dumps(
            {"org_id": org_id, "scopes": sorted(scopes), "exp": int(expires_at), "name": name},
            separators=(",", ":"),
        ).encode()
        b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        sig = hmac.new(self.secret, b64.encode(), hashlib.sha256).hexdigest()[:32]
        return f"ai_obs_v1.{b64}.{sig}"

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
        if time.time() > payload["exp"]:
            raise TokenError("token expired")
        return ServiceToken(
            org_id=payload["org_id"],
            scopes=frozenset(payload["scopes"]),
            expires_at=float(payload["exp"]),
            name=payload.get("name", "verified"),
        )
