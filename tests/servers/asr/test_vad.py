"""Energy VAD unit tests."""

from __future__ import annotations

import array
import math

import pytest

from servers.asr.vad import EnergyVAD

pytestmark = pytest.mark.unit


def _tone(samples: int, *, amplitude: int = 8000, freq: float = 440.0, sr: int = 16_000) -> bytes:
    buf = array.array("h")
    for i in range(samples):
        buf.append(int(amplitude * math.sin(2 * math.pi * freq * i / sr)))
    return buf.tobytes()


def _silence(samples: int) -> bytes:
    return b"\x00\x00" * samples


def test_vad_emits_segment_after_hangover() -> None:
    vad = EnergyVAD(sample_rate=16_000, frame_ms=20, speech_threshold=500.0, hangover_frames=5)
    # 100 ms speech + 120 ms silence (6 frames hangover)
    speech = _tone(1600)
    silence = _silence(1920)
    segs = vad.push(speech + silence)
    assert len(segs) == 1
    assert len(segs[0]) > 0


def test_vad_flush_returns_open_speech() -> None:
    vad = EnergyVAD(sample_rate=16_000, frame_ms=20, speech_threshold=500.0)
    vad.push(_tone(640))  # 40 ms — still in speech
    leftover = vad.flush()
    assert leftover is not None
    assert len(leftover) >= 640 * 2


def test_vad_silence_only_no_segment() -> None:
    vad = EnergyVAD(sample_rate=16_000)
    assert vad.push(_silence(3200)) == []
    assert vad.flush() is None
