"""Pydantic models for TTS HTTP messages (design §4.3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StreamRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)
    voice: str = "default"
    speed: float = Field(default=1.0, gt=0.1, le=3.0)
    sample_rate: int = 24_000


class VoiceInfo(BaseModel):
    id: str
    sample_rate: int
    description: str = ""


SUPPORTED_SAMPLE_RATES = frozenset({8_000, 16_000, 22_050, 24_000})
DEFAULT_CONCURRENCY = 2
DEFAULT_SAMPLE_RATE = 24_000
CHUNK_MS = 20
