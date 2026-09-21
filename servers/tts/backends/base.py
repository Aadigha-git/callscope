"""TTS backend protocol and PCM helpers."""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TTSBackend(Protocol):
    name: str
    native_sample_rate: int

    def load(self) -> None:
        """Eager load weights (no-op for fake). Must not run at import time."""

    def voices(self) -> list[tuple[str, str]]:
        """Return (voice_id, description) pairs."""

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        sample_rate: int,
        cancel: asyncio.Event,
    ) -> AsyncIterator[bytes]:
        """Yield PCM16LE chunks; stop promptly when ``cancel`` is set."""

    async def warm_up(self) -> None:
        """Short synth so the first real request is not cold."""


def pcm16_chunk_bytes(sample_rate: int, chunk_ms: int = 20) -> int:
    return max(int(sample_rate * chunk_ms / 1000), 1) * 2


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear resample mono PCM16LE (adequate for M1 demo rates)."""
    if src_rate == dst_rate or not pcm:
        return pcm
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError("sample rates must be positive")
    n_src = len(pcm) // 2
    if n_src == 0:
        return b""
    samples = struct.unpack(f"<{n_src}h", pcm[: n_src * 2])
    n_dst = max(int(n_src * dst_rate / src_rate), 1)
    out = bytearray()
    for i in range(n_dst):
        pos = i * (n_src - 1) / max(n_dst - 1, 1)
        i0 = int(pos)
        i1 = min(i0 + 1, n_src - 1)
        frac = pos - i0
        val = int(samples[i0] * (1.0 - frac) + samples[i1] * frac)
        out.extend(struct.pack("<h", max(-32768, min(32767, val))))
    return bytes(out)


def float_to_pcm16(samples: Any) -> bytes:
    """Convert float samples in [-1, 1] (or array-like) to PCM16LE."""
    out = bytearray()
    for s in samples:
        val = int(max(-1.0, min(1.0, float(s))) * 32767.0)
        out.extend(struct.pack("<h", val))
    return bytes(out)


def sine_pcm16(
    n_samples: int, sample_rate: int, frequency_hz: float = 440.0, phase: float = 0.0
) -> tuple[bytes, float]:
    out = bytearray()
    two_pi_f = 2.0 * math.pi * frequency_hz / sample_rate
    for i in range(n_samples):
        sample = int(16000 * math.sin(phase + i * two_pi_f))
        out.extend(struct.pack("<h", max(-32768, min(32767, sample))))
    return bytes(out), phase + n_samples * two_pi_f


async def chunk_pcm(
    pcm: bytes,
    *,
    sample_rate: int,
    chunk_ms: int,
    cancel: asyncio.Event,
) -> AsyncIterator[bytes]:
    """Yield fixed-duration PCM frames; honour cancel between chunks."""
    frame = pcm16_chunk_bytes(sample_rate, chunk_ms)
    offset = 0
    while offset < len(pcm):
        if cancel.is_set():
            return
        end = min(offset + frame, len(pcm))
        # Pad odd last byte — should not happen for PCM16.
        piece = pcm[offset:end]
        if len(piece) % 2:
            piece += b"\x00"
        yield piece
        offset = end
