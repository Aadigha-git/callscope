"""Deterministic fake TTS backend for CI (no model weights)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from servers.tts.backends.base import pcm16_chunk_bytes, sine_pcm16
from servers.tts.models import CHUNK_MS, DEFAULT_SAMPLE_RATE


class FakeTTSBackend:
    """Sine-wave PCM stream sized from text length; cancellable between chunks."""

    name = "fake"
    native_sample_rate = DEFAULT_SAMPLE_RATE

    def __init__(
        self,
        *,
        ms_per_char: float = 40.0,
        chunk_delay_s: float = 0.0,
    ) -> None:
        self._ms_per_char = ms_per_char
        self._chunk_delay_s = chunk_delay_s
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def voices(self) -> list[tuple[str, str]]:
        return [
            ("default", "Fake sine voice"),
            ("alt", "Alternate fake sine voice"),
        ]

    async def warm_up(self) -> None:
        cancel = asyncio.Event()
        async for _ in self.synthesize(
            "ok", voice="default", speed=1.0, sample_rate=self.native_sample_rate, cancel=cancel
        ):
            break

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        sample_rate: int,
        cancel: asyncio.Event,
    ) -> AsyncIterator[bytes]:
        _ = voice
        if not self._loaded:
            self.load()
        duration_ms = max(int(len(text) * self._ms_per_char / max(speed, 0.1)), CHUNK_MS)
        samples_total = int(sample_rate * duration_ms / 1000)
        chunk_samples = pcm16_chunk_bytes(sample_rate, CHUNK_MS) // 2
        produced = 0
        phase = 0.0
        freq = 440.0 if voice != "alt" else 523.25
        while produced < samples_total:
            if cancel.is_set():
                return
            if self._chunk_delay_s > 0:
                await asyncio.sleep(self._chunk_delay_s)
                if cancel.is_set():
                    return
            n = min(chunk_samples, samples_total - produced)
            chunk, phase = sine_pcm16(n, sample_rate, freq, phase)
            produced += n
            yield chunk
