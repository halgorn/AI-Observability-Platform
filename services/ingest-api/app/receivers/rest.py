from __future__ import annotations

from fastapi import APIRouter, Header, Request, status

from ..auth import ServiceToken, TokenError, TokenStore
from ..errors import AuthForbiddenError, AuthMissingError
from ..pipeline import process_batch
from ..schemas import IngestResponse

router = APIRouter()


def _get_ctx(request: Request):
    return request.app.state.ctx


def _get_token_store(request: Request) -> TokenStore:
    return request.app.state.ctx.token_store


def _auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> ServiceToken:
    store = _get_token_store(request)
    if not authorization:
        raise AuthMissingError()
    try:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise AuthForbiddenError("expected Bearer scheme")
        return store.verify(token)
    except TokenError as e:
        raise AuthForbiddenError(str(e)) from e


@router.post("/v1/events", status_code=status.HTTP_200_OK, response_model=IngestResponse)
async def post_events(
    request: Request,
    authorization: str | None = Header(default=None),
) -> IngestResponse:
    token = _auth(request, authorization)
    ctx = _get_ctx(request)
    body = await request.json()
    if not isinstance(body, list):
        body = body.get("events", []) if isinstance(body, dict) else []
    if not body:
        return IngestResponse(accepted=0, rejected=0)
    result = await process_batch(body, token.org_id, ctx.deps)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        rejected_details=result.details,
    )


@router.post("/v1/traces")
async def post_traces(
    request: Request,
    authorization: str | None = Header(default=None),
) -> IngestResponse:
    from .otlp import otlp_to_events

    token = _auth(request, authorization)
    ctx = _get_ctx(request)
    body = await request.json()
    events = otlp_to_events(body, token.org_id)
    if not events:
        return IngestResponse(accepted=0, rejected=0)
    result = await process_batch(events, token.org_id, ctx.deps)
    return IngestResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        rejected_details=result.details,
    )
