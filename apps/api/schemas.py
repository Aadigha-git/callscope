"""API schemas aligned with docs/api/openapi.yaml (T-M1-07 subset)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StatusOut(BaseModel):
    state: Literal["online", "warming_up", "offline"]
    active_calls: int
    max_concurrent: int
    stack_label: str
    next_window: datetime | None = None


class SessionRequest(BaseModel):
    consent_recording: Literal[True]
    consent_donate: bool = False
    policy_version: str = Field(min_length=1)


class SessionResponse(BaseModel):
    call_id: UUID
    livekit_url: str
    room: str
    token: str
    expires_at: datetime
    max_duration_s: int


class EventIn(BaseModel):
    event_id: UUID
    call_id: UUID
    turn_id: UUID | None = None
    t_ms: int
    ts: datetime
    source: Literal["worker", "plugin", "client", "sim"]
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EventsBatchRequest(BaseModel):
    events: list[EventIn] = Field(max_length=500)


class EventsBatchResponse(BaseModel):
    accepted: int
    duplicates: int
