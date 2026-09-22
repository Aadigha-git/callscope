"""FastAPI dependencies and application state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from apps.api.livekit_tokens import LiveKitTokenMinter, TokenMinter
from apps.api.ratelimit import SessionCapLimiter
from apps.api.review_store import ReviewStore
from apps.api.store import CallStore, MemoryCallStore
from callscope.config import Settings, get_settings


@dataclass
class WorkerStatus:
    """Reflects whether the local voice worker / Mac stack is ready for calls."""

    online: bool = True
    warming_up: bool = False
    stack_label: str = "local-mac-dev"


@dataclass
class ApiState:
    settings: Settings
    store: CallStore
    review: ReviewStore
    limiter: SessionCapLimiter
    tokens: TokenMinter
    worker: WorkerStatus
    service_token: str
    policy_version: str
    max_duration_s: int = 240
    token_ttl_s: int = 300


def build_api_state(
    *,
    settings: Settings | None = None,
    store: CallStore | None = None,
    review: ReviewStore | None = None,
    limiter: SessionCapLimiter | None = None,
    tokens: TokenMinter | None = None,
    worker: WorkerStatus | None = None,
) -> ApiState:
    s = settings or get_settings()
    max_c = int(os.environ.get("CALLSCOPE_MAX_CONCURRENT_SESSIONS", "2"))
    policy = os.environ.get("CALLSCOPE_POLICY_VERSION", "2026-09-20")
    service = os.environ.get("CALLSCOPE_SERVICE_TOKEN", "changeme-service-token")
    online_env = os.environ.get("CALLSCOPE_WORKER_ONLINE", "true").lower()
    online = online_env in {"1", "true", "yes"}
    call_store = store or MemoryCallStore()
    secret = os.environ.get("CALLSCOPE_AUDIO_SIGNING_SECRET", "callscope-audio-sign-dev")
    return ApiState(
        settings=s,
        store=call_store,
        review=review or ReviewStore(calls=call_store, audio_hmac_key=secret),
        limiter=limiter or SessionCapLimiter(max_concurrent=max_c),
        tokens=tokens
        or LiveKitTokenMinter(s.livekit_api_key, s.livekit_api_secret.get_secret_value()),
        worker=worker or WorkerStatus(online=online, stack_label="local-mac-dev"),
        service_token=service,
        policy_version=policy,
    )


def get_state(request: Request) -> ApiState:
    return request.app.state.api  # type: ignore[no-any-return]


StateDep = Annotated[ApiState, Depends(get_state)]


def require_service_token(
    state: StateDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="service bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if token != state.service_token:
        raise HTTPException(
            status_code=401,
            detail="invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )
