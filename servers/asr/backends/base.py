"""ASR backend protocol and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class WordTiming:
    w: str
    start_ms: int
    end_ms: int
    conf: float | None = None


@dataclass(frozen=True, slots=True)
class ASRFinal:
    text: str
    words: tuple[WordTiming, ...] = ()
    avg_conf: float | None = None
    audio_ms: int = 0


@dataclass
class ASRSessionState:
    """Mutable per-stream decode state held by the backend."""

    sample_rate: int
    hotwords: list[str] = field(default_factory=list)
    pcm: bytearray = field(default_factory=bytearray)
    last_partial: str = ""


@runtime_checkable
class ASRBackend(Protocol):
    name: str

    def load(self) -> None:
        """Eager load weights (no-op for fake). Must not run at import time."""

    def begin(self, *, sample_rate: int, hotwords: list[str] | None) -> ASRSessionState: ...

    def transcribe_chunk(self, state: ASRSessionState, pcm: bytes) -> str | None:
        """Optional partial text (local-agreement); None if unchanged."""

    def finalize(self, state: ASRSessionState) -> ASRFinal: ...
