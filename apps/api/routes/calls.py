"""GET /v1/calls list, detail, and signed audio URL."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.deps import StateDep, require_service_token
from apps.api.schemas import AudioUrlOut, CallDetailOut, CallListOut, CallSummaryOut, LabelOut

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.get("/v1/calls", response_model=CallListOut)
async def list_calls(
    state: StateDep,
    flagged: bool | None = None,
    root_cause: str | None = None,
    stack_version_id: UUID | None = None,
    channel: Annotated[str | None, Query()] = None,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> CallListOut:
    items, next_cursor = state.review.list_calls(
        flagged=flagged,
        root_cause=root_cause,
        channel=channel,
        stack_version_id=str(stack_version_id) if stack_version_id else None,
        from_ts=from_ts,
        limit=limit,
        cursor=cursor,
    )
    return CallListOut(
        items=[CallSummaryOut.model_validate(x) for x in items],
        next_cursor=next_cursor,
    )


@router.get("/v1/calls/{call_id}", response_model=CallDetailOut)
async def call_detail(call_id: UUID, state: StateDep) -> CallDetailOut:
    detail = state.review.call_detail(call_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="unknown call_id")
    labels = [LabelOut.model_validate(x) for x in detail.pop("labels", [])]
    return CallDetailOut.model_validate({**detail, "labels": labels})


@router.get("/v1/calls/{call_id}/audio", response_model=AudioUrlOut)
async def call_audio(call_id: UUID, state: StateDep) -> AudioUrlOut:
    signed = state.review.sign_audio_url(call_id, ttl_s=300)
    if signed is None:
        raise HTTPException(status_code=404, detail="no recording for call")
    url, expires = signed
    return AudioUrlOut(url=url, expires_at=expires)
