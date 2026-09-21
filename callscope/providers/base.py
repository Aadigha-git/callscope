"""Provider protocols and shared types (design §4.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


class ProviderError(Exception):
    """Base error for STT / TTS / Brain providers."""


class ProviderTimeout(ProviderError):
    """Provider exceeded an allowed latency budget."""


class ProviderUnavailable(ProviderError):
    """Provider is down or not reachable."""


@dataclass(frozen=True, slots=True)
class WordTiming:
    word: str
    start_ms: int
    end_ms: int
    conf: float | None = None


@dataclass(frozen=True, slots=True)
class STTEvent:
    """Streaming ASR event (partial or final)."""

    kind: Literal["partial", "final"]
    text: str
    words: tuple[WordTiming, ...] = ()
    avg_conf: float | None = None
    t_start_ms: int = 0
    t_end_ms: int = 0


@dataclass(frozen=True, slots=True)
class Transcript:
    """Non-streaming transcription result."""

    text: str
    words: tuple[WordTiming, ...] = ()
    avg_conf: float | None = None
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class Msg:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolEvent:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class BrainDelta:
    """Streaming brain output: text token, tool event, or terminal done."""

    kind: Literal["text", "tool_event", "done"]
    text: str | None = None
    tool_event: ToolEvent | None = None


@runtime_checkable
class STTProvider(Protocol):
    def stream(
        self,
        pcm: AsyncIterator[bytes],
        *,
        sample_rate: int,
        hotwords: list[str] | None,
    ) -> AsyncIterator[STTEvent]: ...

    async def transcribe(self, wav: bytes, *, sample_rate: int) -> Transcript: ...


@runtime_checkable
class TTSProvider(Protocol):
    sample_rate: int

    def stream(self, text: str, *, voice: str, speed: float) -> AsyncIterator[bytes]: ...


@runtime_checkable
class BrainBackend(Protocol):
    def stream_reply(
        self,
        messages: list[Msg],
        *,
        call_id: str,
        turn_id: str,
    ) -> AsyncIterator[BrainDelta]: ...

    async def cancel(self, turn_id: str) -> None: ...
