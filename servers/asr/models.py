"""Pydantic models for ASR HTTP/WebSocket messages (design §4.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StreamStart(BaseModel):
    type: Literal["start"] = "start"
    sample_rate: int
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    hotwords: list[str] | None = None


class StreamEnd(BaseModel):
    type: Literal["end"] = "end"


class WordTimingOut(BaseModel):
    w: str
    start_ms: int
    end_ms: int
    conf: float | None = None


class PartialOut(BaseModel):
    type: Literal["partial"] = "partial"
    text: str
    t_start_ms: int = 0


class FinalOut(BaseModel):
    type: Literal["final"] = "final"
    text: str
    words: list[WordTimingOut] = Field(default_factory=list)
    avg_conf: float | None = None


class ErrorOut(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


SUPPORTED_SAMPLE_RATES = frozenset({8_000, 16_000, 24_000})
# Max frame: 100 ms of PCM16 mono at 24 kHz = 4800 samples * 2 bytes
MAX_FRAME_BYTES = 24_000 * 2 // 10
MIN_FRAME_BYTES = 8_000 * 2 // 50  # ~20 ms at 8 kHz
DEFAULT_CONCURRENCY = 2
