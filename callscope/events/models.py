"""Event envelope (design §6.6) matching docs/api/openapi.yaml Event."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventSource(StrEnum):
    WORKER = "worker"
    PLUGIN = "plugin"
    CLIENT = "client"
    SIM = "sim"


# Catalogue from design §6.6 (const list for workers/plugins; OpenAPI keeps type: string).
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "call.start",
        "call.end",
        "call.consent",
        "vad.speech_start",
        "vad.speech_end",
        "endpoint.decided",
        "stt.partial",
        "stt.final",
        "brain.request",
        "brain.first_token",
        "brain.done",
        "tool.call",
        "tool.result",
        "policy.denied",
        "tts.request",
        "tts.first_audio",
        "playback.start",
        "playback.stop",
        "barge_in.detected",
        "barge_in.applied",
        "filler.played",
        "provider.error",
    }
)


class Event(BaseModel):
    """Pydantic v2 event envelope aligned with OpenAPI `Event`."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    call_id: UUID
    turn_id: UUID | None = None
    t_ms: int
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: EventSource
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
