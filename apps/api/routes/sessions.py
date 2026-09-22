"""API routes: status, sessions, events batch."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from apps.api.deps import StateDep, require_service_token
from apps.api.errors import problem
from apps.api.ratelimit import SessionCapExceeded
from apps.api.schemas import (
    EventsBatchRequest,
    EventsBatchResponse,
    RecordingRegisterRequest,
    SessionRequest,
    SessionResponse,
    StatusOut,
)
from callscope.events.models import Event as EventModel
from callscope.events.models import EventSource

router = APIRouter()

SESSIONS_TOTAL = Counter("callscope_api_sessions_total", "Session create attempts", ["status"])
EVENTS_BATCH_TOTAL = Counter(
    "callscope_api_events_batch_total", "Event batch ingest results", ["result"]
)


@router.get("/v1/status", response_model=StatusOut)
async def status(state: StateDep) -> StatusOut:
    st: Literal["online", "warming_up", "offline"]
    if state.worker.warming_up:
        st = "warming_up"
    elif state.worker.online:
        st = "online"
    else:
        st = "offline"
    return StatusOut(
        state=st,
        active_calls=state.limiter.active_count,
        max_concurrent=state.limiter.max_concurrent,
        stack_label=state.worker.stack_label,
        next_window=None,
    )


@router.post("/v1/sessions", response_model=SessionResponse, status_code=201)
async def create_session(body: SessionRequest, state: StateDep) -> SessionResponse | JSONResponse:
    if not state.worker.online or state.worker.warming_up:
        SESSIONS_TOTAL.labels(status="offline").inc()
        return problem(
            status=503,
            title="Service Unavailable",
            detail="local worker offline",
            code="worker_offline",
        )
    if body.policy_version != state.policy_version:
        SESSIONS_TOTAL.labels(status="policy").inc()
        return problem(
            status=403,
            title="Forbidden",
            detail=f"policy_version must be {state.policy_version!r}",
            code="policy_mismatch",
        )

    rec = state.store.create_session(
        consent_recording=True,
        consent_donate=body.consent_donate,
        policy_version=body.policy_version,
    )
    try:
        state.limiter.try_acquire(rec.call_id)
    except SessionCapExceeded as exc:
        state.store.end_session(rec.call_id, reason="cap_exceeded")
        SESSIONS_TOTAL.labels(status="cap").inc()
        return problem(
            status=429,
            title="Too Many Requests",
            detail=str(exc),
            code="session_cap",
        )

    identity = f"caller-{rec.call_id}"
    token, expires = state.tokens.mint(
        call_id=rec.call_id,
        room=rec.room,
        identity=identity,
        ttl_s=state.token_ttl_s,
    )
    SESSIONS_TOTAL.labels(status="ok").inc()
    return SessionResponse(
        call_id=rec.call_id,
        livekit_url=state.settings.livekit_url,
        room=rec.room,
        token=token,
        expires_at=expires,
        max_duration_s=state.max_duration_s,
    )


@router.post("/v1/sessions/{call_id}/end", status_code=204)
async def end_session(call_id: UUID, state: StateDep) -> Response:
    state.store.end_session(call_id, reason="client_end")
    state.limiter.release(call_id)
    return Response(status_code=204)


@router.post(
    "/v1/events:batch",
    response_model=EventsBatchResponse,
    status_code=202,
    dependencies=[Depends(require_service_token)],
)
async def events_batch(body: EventsBatchRequest, state: StateDep) -> EventsBatchResponse:
    events = [
        EventModel(
            event_id=e.event_id,
            call_id=e.call_id,
            turn_id=e.turn_id,
            t_ms=e.t_ms,
            ts=e.ts,
            source=EventSource(e.source),
            type=e.type,
            payload=e.payload,
        )
        for e in body.events
    ]
    accepted, duplicates = state.store.insert_events(events)
    if accepted:
        EVENTS_BATCH_TOTAL.labels(result="accepted").inc(accepted)
    if duplicates:
        EVENTS_BATCH_TOTAL.labels(result="duplicates").inc(duplicates)
    return EventsBatchResponse(accepted=accepted, duplicates=duplicates)


@router.post(
    "/v1/calls/{call_id}/recording",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_service_token)],
)
async def register_recording(
    call_id: UUID,
    body: RecordingRegisterRequest,
    state: StateDep,
) -> Response:
    rec = state.store.get(call_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown call_id")
    if not rec.consent_recording:
        raise HTTPException(status_code=403, detail="recording requires consent")
    ok = state.store.register_recording(
        call_id,
        mixed_uri=body.mixed_uri,
        caller_uri=body.caller_uri,
        agent_uri=body.agent_uri,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="unknown call_id")
    return Response(status_code=204)


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/metrics/eval")
async def metrics_eval() -> Response:
    import os
    from pathlib import Path

    from callscope.observability.eval_exporter import render_metrics_text

    store = Path(os.environ.get("CALLSCOPE_EVAL_STORE", "artifacts/eval_runs"))
    return Response(render_metrics_text(store), media_type=CONTENT_TYPE_LATEST)
